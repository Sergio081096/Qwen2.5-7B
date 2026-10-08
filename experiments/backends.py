"""Consultas sin ROS ni historial conversacional, con evidencia antes de validar."""
from contextlib import contextmanager
import json
import os
import time
import httpx

from .common import ExperimentError, read_json, error_info
from .symbolic import SymbolicPlanner
from qwen_gpsr.runtime.resources import ProcessResources
from .validation import goals_issues, plan_issues, validate_gpt


def qwen_headers(config):
    key = os.environ.get(config['api_key_env'], '')
    return {'Authorization': f'Bearer {key}'} if key else {}


def qwen_url(config):
    url = os.environ.get(config['url_env'], '').rstrip('/')
    if not url.startswith(('http://', 'https://')):
        raise ExperimentError('ConfigurationError', 'Falta una URL HTTP válida en QWEN_SERVER_URL')
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ExperimentError('ConfigurationError', 'La URL no debe contener credenciales, query ni fragmento')
    return url


def fetch_metadata(config, timeout=10):
    response = httpx.get(qwen_url(config)+'/metadata', headers=qwen_headers(config), timeout=timeout)
    if response.status_code != 200:
        raise ExperimentError('MetadataUnavailable', 'Se requiere /metadata del servidor experimental')
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get('effective_config_sha256'), str):
        raise ExperimentError('MetadataInvalid', 'Metadatos del servidor incompletos')
    return payload


class Backend:
    def __init__(self, directory, config, initial_state):
        self.directory, self.config, self.initial_state = directory, config, initial_state
        self.architecture = config['architecture']
        self.symbolic = None
        self.client = None
        start = time.perf_counter()
        if self.architecture == 'gpt_direct':
            from openai import OpenAI
            key = os.environ.get(config['api_key_env'], '')
            if not key:
                raise ExperimentError('ConfigurationError', 'Falta la variable de entorno de la clave GPT')
            self.client = OpenAI(api_key=key, base_url='https://api.openai.com/v1',
                                 timeout=config['timeouts_seconds']['model_request'], max_retries=0)
            self.prompt = (directory/config['prompt']['path']).read_text(encoding='utf-8')
            self.schema = read_json(directory/config['response_schema']['path'])
        else:
            self.symbolic = SymbolicPlanner([directory/r['path'] for r in config['clips_rules']])
            if self.architecture == 'qwen_clips':
                observed = fetch_metadata(config['qwen'])
                if observed['effective_config_sha256'] != config['qwen']['effective_config_sha256']:
                    raise ExperimentError('ServerConfigurationChanged', 'La configuración efectiva de Qwen difiere del manifiesto')
                self.client = httpx.Client(timeout=config['timeouts_seconds']['model_request'])
        self.startup = {'initialization_ms': (time.perf_counter()-start)*1000,
                        'clips_load_ms': self.symbolic.load_ms if self.symbolic else None,
                        'model_load_ms': None}

    @contextmanager
    def stage(self, name):
        self.current_stage = name
        started = time.perf_counter()
        self.emit('stage', name, started, self.record)
        try:
            yield
        finally:
            self.record['timing'][name+'_ms'] = (time.perf_counter()-started)*1000
            self.emit('progress', name, time.perf_counter(), self.record)

    def execute(self, record, reference, emit):
        self.record, self.emit = record, emit
        self.current_stage = 'preparation'
        monitor=ProcessResources('experiment_worker_including_HTTP_wait_and_local_processing_excluding_load')
        monitor.__enter__()
        try:
            if self.architecture == 'gpt_direct':
                self.gpt()
            else:
                self.clips(reference)
        except Exception as exc:
            is_timeout = isinstance(exc, (httpx.TimeoutException, TimeoutError)) or type(exc).__name__ == 'APITimeoutError'
            record['execution_status'] = 'timeout' if is_timeout else 'error'
            record['error'] = error_info(exc, self.current_stage)
            if is_timeout:
                limit = self.config['timeouts_seconds'].get(self.current_stage)
                record['error']['limit_ms'] = limit*1000 if limit else None
        finally:
            monitor.__exit__(None,None,None)
            record['resources']['client']=monitor.result
        return record

    def gpt(self):
        r = self.record
        r['gpt'] = {'requested_model': self.config['model'], 'returned_model': None,
                    'response_id': None, 'provider_status': None, 'domain_status': None,
                    'usage': dict.fromkeys(('input_tokens','output_tokens','total_tokens',
                                           'cached_input_tokens','reasoning_tokens')),
                    'provider_response_artifact': None, 'provider_response': None}
        with self.stage('model_request'):
            try:
                response = self.client.responses.create(
                    model=self.config['model'], **self.config['generation'],
                    input=[{'role':'system','content':self.prompt},
                           {'role':'user','content':r['input_original']}],
                    text={'format':{'type':'json_schema','name':'gpsr_direct_plan',
                                    'strict':True,'schema':self.schema}})
            except Exception as exc:
                response = getattr(exc, 'response', None)
                if response is not None:
                    r['gpt']['provider_error_body'] = response.text
                    r['gpt']['http_status'] = response.status_code
                raise
            provider = response.model_dump(mode='json')
            r['gpt']['provider_response'] = provider
            r['raw_output'] = response.output_text
            r['raw_output_kind'] = 'provider_output_text'
            r['gpt'].update(returned_model=provider.get('model'), response_id=provider.get('id'),
                            provider_status=provider.get('status'))
            usage = provider.get('usage') or {}
            r['gpt']['usage'] = {
                **{k: usage.get(k) for k in ('input_tokens','output_tokens','total_tokens')},
                'cached_input_tokens': (usage.get('input_tokens_details') or {}).get('cached_tokens'),
                'reasoning_tokens': (usage.get('output_tokens_details') or {}).get('reasoning_tokens')}
        invalid_json = False
        with self.stage('extraction'):
            if provider.get('status') != 'completed':
                reason = (provider.get('incomplete_details') or {}).get('reason')
                raise ExperimentError('OutputTruncation' if reason == 'max_output_tokens' else 'ProviderIncomplete',
                                      'El proveedor no completó la respuesta; consultar provider_response')
            if any(c.get('type') == 'refusal' for item in provider.get('output', [])
                   for c in item.get('content', [])):
                raise ExperimentError('ProviderRefusal', 'Negativa del proveedor, no rechazo del dominio')
            try:
                result = json.loads(r['raw_output'])
            except (ValueError, TypeError):
                invalid_json = True
                result = None
            r['gpt']['domain_status'] = result.get('status') if isinstance(result, dict) else None
            if isinstance(result, dict):
                status = result.get('status')
                r['response_kind'] = {'executable':'plan','clarification':'clarification','rejected':'rejected'}.get(status)
                # Invalid types stay in raw_output, never coerce them into empty lists.
                for source, target in [('goals','goals_pred'),('plan','plan')]:
                    if isinstance(result.get(source), list) and all(
                        isinstance(item, str if source == 'goals' else dict) for item in result[source]
                    ):
                        r[target] = result[source]
                if isinstance(result.get('message'), str):
                    r['message'] = result['message']
        with self.stage('validation'):
            if invalid_json:
                r['validation']['response_schema_valid'] = False
                r['validation']['issues'].append('response: invalid JSON')
            else:
                r['validation'] = validate_gpt(result, self.schema)
        r['execution_status'] = 'completed'

    def clips(self, reference):
        r = self.record
        block = {'input_normalized':None, 'goals_after_adapter':None, 'clips_facts':None,
                 'clips_plan_raw':None, 'rules_fired':None, 'planning_done':None,
                 'remaining_goals':None, 'diagnostics':[], 'server_elapsed_ms':None,
                 'transformations':None}
        key = 'qwen_clips' if self.architecture == 'qwen_clips' else 'reference_clips'
        r[key] = block
        if self.architecture == 'qwen_clips':
            with self.stage('model_request'):
                response = self.client.post(qwen_url(self.config['qwen'])+'/translate',
                                            headers={**qwen_headers(self.config['qwen']), 'X-Experiment-Run-ID':self.record['run_id']},
                                            json={'command':r['input_original']})
                r['raw_output'] = response.text
                r['raw_output_kind'] = 'http_body'
                block['http_status'] = response.status_code
            with self.stage('extraction'):
                try:
                    payload = json.loads(r['raw_output'])
                except ValueError:
                    r['validation']['response_schema_valid'] = False
                    raise ExperimentError('InvalidHTTPBody', 'Qwen no devolvió JSON')
                if not isinstance(payload, dict):
                    r['validation']['response_schema_valid'] = False
                    raise ExperimentError('InvalidHTTPBody', 'Qwen no devolvió un objeto')
                block['server_elapsed_ms'] = payload.get('elapsed_ms')
                usage=payload.get('resource_usage')
                if (isinstance(usage,dict) and usage.get('status')=='available'
                        and payload.get('effective_config_sha256') == self.config['qwen']['effective_config_sha256']):
                    r['resources']['model_internal']=usage
                result = payload.get('result')
                prediction = result.get('prediction') if isinstance(result, dict) else None
                goals = prediction.get('goals') if isinstance(prediction, dict) else None
                if isinstance(goals, list) and all(isinstance(g,str) for g in goals):
                    r['goals_pred'] = goals
                block['input_normalized'] = result.get('normalized_input') if isinstance(result, dict) else payload.get('normalized_input')
                shape_ok = payload.get('ok') is True and isinstance(goals, list) and all(isinstance(g,str) for g in goals)
                r['validation']['response_schema_valid'] = shape_ok
                if response.status_code != 200:
                    raise ExperimentError('QwenHTTPError', f'Qwen devolvió HTTP {response.status_code}; cuerpo conservado')
                if not shape_ok:
                    raise ExperimentError('InvalidQwenResponse', 'No se encontraron objetivos analizables en la respuesta')
                if payload.get('effective_config_sha256') != self.config['qwen']['effective_config_sha256']:
                    raise ExperimentError('ServerConfigurationChanged', 'La respuesta no corresponde a la configuración fijada')
        else:
            self.current_stage = 'reference'
            if reference is None or reference.get('reference_status') != 'approved' or reference.get('example_only') is True:
                raise ExperimentError('ReferenceNotApproved', 'El control requiere una referencia real revisada con status approved')
            if reference.get('input') != r['input_original']:
                raise ExperimentError('ReferenceMismatch', 'La referencia no corresponde al texto original')
            goals = reference.get('goals_ref')
            block['reference_version'] = reference.get('reference_version') or self.config['reference_version']
            block['goals_reference_input'] = goals
            if goals is None:
                raise ExperimentError('ReferenceNotApplicable', 'No hay objetivos ejecutables aplicables para el control')
        with self.stage('adaptation'):
            gi = goals_issues(goals)
            r['validation']['goals_schema_valid'] = not gi
            r['validation']['issues'].extend(gi)
            if not isinstance(goals,list) or not goals or not all(isinstance(g,str) for g in goals):
                raise ExperimentError('InvalidGoals', 'No hay una lista no vacía de objetivos analizables')
            adapted, facts = self.symbolic.adapt(goals)
            block['goals_after_adapter'], block['clips_facts'] = adapted, facts
            block['transformations'] = {'original_goals':goals, 'adapted_objects':adapted,
                                        'method':'Justina GoalParser.parse_many and ClipsGoalFactBuilder.build'}
        with self.stage('planning'):
            fired = self.symbolic.plan(facts, self.initial_state)
        previous_extraction = r['timing']['extraction_ms'] or 0
        with self.stage('extraction'):
            plan, details = self.symbolic.extract(fired)
            r['plan'] = plan
            r['response_kind'] = 'plan' if plan else None
            block.update(details)
        r['timing']['extraction_ms'] += previous_extraction
        with self.stage('validation'):
            pi = plan_issues(r['plan'])
            r['validation']['plan_contract_valid'] = not pi
            r['validation']['issues'].extend(pi)
            if not block['planning_done'] or block['remaining_goals'] or block['unsupported_goal']:
                raise ExperimentError('PlanningIncomplete', 'CLIPS no terminó o detectó objetivos sin soporte')
        r['execution_status'] = 'completed'

    def close(self):
        if self.client:
            self.client.close()
        if self.symbolic:
            self.symbolic.close()
