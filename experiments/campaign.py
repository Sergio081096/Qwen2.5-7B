"""Creación de campañas inmutables y comprobación de sus artefactos."""
import importlib.metadata
import json
import platform
import shutil
import subprocess
import tempfile
import math
import uuid
from pathlib import Path

from .common import ROOT, REPO, INITIAL_STATE, digest, object_digest, load_inputs, read_json, write_json, read_jsonl
from .backends import fetch_metadata


def source_inventory():
    paths = sorted(list(ROOT.rglob('*.py')) + list(ROOT.glob('schemas/*.json')) +
                   [REPO/'qwen_gpsr/runtime/resources.py', REPO/'qwen_gpsr/domain/goal_schema.py', REPO/'chatgpt_planner/response_schema.json'])
    return [{'path':str(p.relative_to(REPO)), 'sha256':digest(p)} for p in paths]


def packages():
    return {name: importlib.metadata.version(name) for name in ('httpx','jsonschema','clipspy','openai')}


def snapshot(directory, source, name):
    target = directory/'assets'/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {'path':str(target.relative_to(directory)), 'sha256':digest(target)}


def _initialize(directory, inputs, conditions, model=None, references=None,
               repetitions=1, order_seed=42, request_timeout=60, planning_timeout=10,
               total_timeout=75, prompt=None, response_schema=None, metadata_file=None,
               split='development', gpt_parameters=None, qwen_variants=None):
    directory = Path(directory).resolve()
    if directory.exists():
        raise ValueError('La carpeta de campaña ya existe; usar run para reanudar o elegir otra')
    rows = load_inputs(inputs)
    if not conditions or len(set(conditions)) != len(conditions) or not set(conditions) <= {'qwen_clips','gpt_direct','reference_clips'}:
        raise ValueError('Condiciones inválidas')
    if 'gpt_direct' in conditions and (not model or not model.strip()):
        raise ValueError('Elegir explícitamente --model para GPT')
    if 'reference_clips' in conditions and not references:
        raise ValueError('El control requiere --references')
    if repetitions < 1 or any(not math.isfinite(t) or t <= 0 for t in (request_timeout, planning_timeout, total_timeout)):
        raise ValueError('Repeticiones y límites deben ser positivos')
    if split not in ('development','test'):
        raise ValueError('split debe ser development o test')
    if any(r.get('example_only') is True for r in rows):
        raise ValueError('No usar entradas marcadas example_only como campaña real')
    if gpt_parameters is not None and not isinstance(gpt_parameters, dict):
        raise ValueError('gpt-parameters debe ser un objeto JSON')
    params = {'max_output_tokens':8192, 'store':False, **(gpt_parameters or {})}
    if set(params)-{'max_output_tokens','store','temperature','top_p','reasoning'} or params['store'] is not False:
        raise ValueError('Parámetros GPT no permitidos; store debe ser false')
    if type(params['max_output_tokens']) is not int or params['max_output_tokens'] < 1:
        raise ValueError('max_output_tokens inválido')
    variants=qwen_variants or [{'label':'qwen_clips','url_env':'QWEN_SERVER_URL','api_key_env':'QWEN_API_KEY',
                                'metadata_file':str(metadata_file) if metadata_file else None}]
    if qwen_variants is not None:
        if 'qwen_clips' not in conditions or metadata_file:
            raise ValueError('qwen-variants requiere qwen_clips y sustituye qwen-metadata')
        if not isinstance(qwen_variants,list) or not qwen_variants:
            raise ValueError('qwen-variants debe ser una lista no vacía')
        import re
        labels=[]
        for v in variants:
            if not isinstance(v,dict) or set(v)-{'label','url_env','api_key_env','metadata_file'}:
                raise ValueError('Variante Qwen inválida')
            if not isinstance(v.get('label'),str) or not re.fullmatch(r'[A-Za-z0-9_-]+',v['label']):
                raise ValueError('Cada variante requiere label alfanumérico')
            for name in ('url_env','api_key_env'):
                if not isinstance(v.get(name),str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',v[name]):
                    raise ValueError('Cada variante requiere nombres de variables de entorno válidos')
            labels.append(v['label'])
        if len(set(labels))!=len(labels) or set(labels)&{'gpt_direct','reference_clips'}:
            raise ValueError('Etiquetas de variantes duplicadas o reservadas')
    observations=[]
    if 'qwen_clips' in conditions:
        for variant in variants:
            qwen={'mode':'http','url_env':variant['url_env'],'api_key_env':variant['api_key_env']}
            observed=read_json(variant['metadata_file']) if variant.get('metadata_file') else fetch_metadata(qwen)
            for key in ('effective_config_sha256','base_model','adapter_inventory','normalizer_sha256','catalogs_inventory','generation'):
                if key not in observed:raise ValueError(f'Metadatos efectivos sin {key}')
            observations.append((variant,qwen,observed))
    refs = None
    if references:
        refs = read_jsonl(references)
        ids = [r.get('id') for r in refs]
        if len(ids) != len(set(ids)):
            raise ValueError('Referencias duplicadas')
    directory.mkdir(parents=True)
    input_artifact = snapshot(directory, inputs, 'entradas.jsonl')
    ref_artifact = snapshot(directory, references, 'referencias.jsonl') if references else None
    if ref_artifact:
        ref_artifact['version'] = ref_artifact['sha256']
    # Capture only an index for grouping. Model workers never receive reference rubrics.
    intent_index = {r['id']:r.get('intent_id') for r in rows}
    if refs:
        lookup = {r['id']:r for r in refs}
        for row in rows:
            if row['id'] in lookup:
                ref = lookup[row['id']]
                if ref.get('input') != row['input']:
                    raise ValueError(f'Referencia con texto distinto: {row["id"]}')
                if not intent_index[row['id']]:
                    intent_index[row['id']] = ref.get('intent_id')
    schema = snapshot(directory, response_schema or REPO/'chatgpt_planner/response_schema.json', 'response_schema.json')
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(read_json(directory/schema['path']))
    contract = snapshot(directory, REPO/'chatgpt_planner/response_schema.json', 'plan_contract_schema.json')
    symbolic = None
    if set(conditions) & {'qwen_clips','reference_clips'}:
        symbolic = {'goal_adapter_sha256':digest(ROOT/'vendor/goal_adapter.py'),
                    'goal_adapter_provenance':snapshot(directory, ROOT/'vendor/provenance.json', 'provenance.json'),
                    'clips_rules':[snapshot(directory,ROOT/'vendor/goals_planning.clp','goals_planning.clp')]}
    configs = []
    expanded=[(arch,item) for arch in conditions for item in (observations if arch=='qwen_clips' else [None])]
    for arch,item in expanded:
        config = {'architecture':arch,'timeouts_seconds':{'total':total_timeout}}
        if arch == 'gpt_direct':
            config.update(model=model, api_key_env='OPENAI_API_KEY',
                          prompt=snapshot(directory,prompt or REPO/'chatgpt_planner/system_prompt.md','system_prompt.md'),
                          response_schema=schema,generation=params)
            config['timeouts_seconds']['model_request'] = request_timeout
        else:
            config.update(symbolic)
            config['timeouts_seconds']['planning'] = planning_timeout
            if arch == 'qwen_clips':
                variant,qwen,observed=item
                config['label']=variant['label']
                name='qwen_metadata_'+variant['label']+'.json'
                write_json(directory/'assets'/name,observed)
                metadata_artifact={'path':'assets/'+name,'sha256':digest(directory/'assets'/name)}
                qwen.update(base_model=observed['base_model'],base_model_revision=observed.get('base_model_revision'),
                            adapter_path=observed.get('adapter_path'), adapter_sha256=observed['adapter_inventory']['sha256'],
                            generation=observed['generation'],effective_config_sha256=observed['effective_config_sha256'],
                            metadata=metadata_artifact)
                config.update(qwen=qwen,normalizer_sha256=observed['normalizer_sha256'],
                              catalogs_sha256=observed['catalogs_inventory']['sha256'])
                config['timeouts_seconds']['model_request'] = request_timeout
            else:
                config['reference_version'] = ref_artifact['version']
        if arch == 'gpt_direct' and not (directory/config['prompt']['path']).read_text(encoding='utf-8').strip():
            raise ValueError('El prompt GPT está vacío')
        config['config_id'] = arch+'-'+object_digest(config)[:16]
        configs.append(config)
    source = next((c['config_id'] for c in configs if c['architecture']=='qwen_clips'),None)
    for c in configs:
        if c['architecture']=='reference_clips':
            c['symbolic_config_source'] = source
            c['config_id'] = c['architecture']+'-'+object_digest({k:v for k,v in c.items() if k!='config_id'})[:16]
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError):
        revision = None
    write_json(directory/'assets/versiones_python.json',packages())
    manifest = {'schema_version':'1.0','example_only':False,'campaign_id':str(uuid.uuid4()),'split':split,
                'inputs':input_artifact,'references':ref_artifact,'intent_index':intent_index,
                'schedule':{'repetitions':repetitions,'order_seed':order_seed,'concurrency':1,'automatic_retries':0},
                'initial_state':INITIAL_STATE,'configs':configs,'plan_contract_schema':contract,
                'software':{'python':platform.python_version(),'packages_file':'assets/versiones_python.json',
                            'packages_sha256':digest(directory/'assets/versiones_python.json'),
                            'code_revision':revision,'source_inventory':source_inventory()},
                'timeouts_implementation':'worker process termination for request, planning and total deadlines',
                'output_path':'resultados.jsonl'}
    write_json(directory/'manifest.json',manifest)
    (directory/'manifest.sha256').write_text(digest(directory/'manifest.json')+'\n')
    return manifest


def initialize(directory, *args, **kwargs):
    """Publica la campaña completa de forma atómica; no deja manifiestos parciales."""
    directory = Path(directory).resolve()
    if directory.exists():
        raise ValueError('La carpeta de campaña ya existe; usar run para reanudar o elegir otra')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.campaign-', dir=directory.parent) as temporary:
        prepared = Path(temporary)/'campaign'
        manifest = _initialize(prepared, *args, **kwargs)
        prepared.rename(directory)
    return manifest


def load_campaign(directory):
    directory = Path(directory).resolve()
    if digest(directory/'manifest.json') != (directory/'manifest.sha256').read_text().strip():
        raise ValueError('El manifiesto cambió; crear una campaña con configuración nueva')
    manifest = read_json(directory/'manifest.json')
    if manifest['example_only'] or manifest['initial_state'] != INITIAL_STATE:
        raise ValueError('Campaña ilustrativa o estado inicial no soportado')
    if manifest['schedule']['concurrency'] != 1 or manifest['schedule']['automatic_retries'] != 0:
        raise ValueError('Esta versión requiere concurrencia 1 y reintentos automáticos 0')
    def verify(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value:
                path=(directory/value['path']).resolve()
                if not path.is_relative_to(directory) or digest(path) != value['sha256']:
                    raise ValueError(f'Artefacto modificado: {value["path"]}')
            for k,v in value.items():
                if k != 'software': verify(v)
        elif isinstance(value,list):
            for v in value: verify(v)
    verify(manifest)
    if manifest['software']['source_inventory'] != source_inventory():
        raise ValueError('El código o contrato cambió; crear otra campaña')
    if digest(directory/manifest['software']['packages_file']) != manifest['software']['packages_sha256']:
        raise ValueError('Inventario de paquetes modificado')
    if read_json(directory/manifest['software']['packages_file']) != packages() or manifest['software']['python'] != platform.python_version():
        raise ValueError('El entorno Python cambió; crear otra campaña')
    for c in manifest['configs']:
        if c['architecture']!='gpt_direct' and c['goal_adapter_sha256'] != digest(ROOT/'vendor/goal_adapter.py'):
            raise ValueError('El adaptador simbólico cambió')
    return manifest
