"""Entradas de consola para campañas GPT y Qwen–CLIPS."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from .campaign import initialize, load_campaign
from .common import append_jsonl
from .runner import run_campaign
from .evaluate import evaluate_campaign, summarize


def main(default_architecture=None):
    parser=argparse.ArgumentParser(description='Campañas experimentales GPT directo y Qwen–CLIPS sin ROS')
    sub=parser.add_subparsers(dest='operation',required=True)
    init=sub.add_parser('init',help='Crear campaña con configuración y artefactos fijos')
    init.add_argument('--campaign',type=Path,required=True)
    inputs=init.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--inputs',type=Path)
    inputs.add_argument('--command')
    init.add_argument('--case-id',default='CASE-001')
    init.add_argument('--intent-id')
    init.add_argument('--conditions',nargs='+',choices=['gpt_direct','qwen_clips','reference_clips'],
                      default=[default_architecture] if default_architecture else ['qwen_clips','gpt_direct'])
    init.add_argument('--with-reference-control',action='store_true')
    init.add_argument('--references',type=Path)
    init.add_argument('--model',help='Modelo/snapshot GPT elegido para el experimento; sin valor predeterminado')
    init.add_argument('--repetitions',type=int,default=1)
    init.add_argument('--order-seed',type=int,default=42)
    init.add_argument('--request-timeout',type=float,default=60)
    init.add_argument('--planning-timeout',type=float,default=10)
    init.add_argument('--total-timeout',type=float,default=75)
    init.add_argument('--split',choices=['development','test'],default='development')
    init.add_argument('--prompt',type=Path)
    init.add_argument('--response-schema',type=Path)
    init.add_argument('--gpt-parameters',type=json.loads,help='Objeto JSON de parámetros explícitos')
    init.add_argument('--qwen-metadata',type=Path,help='Metadatos capturados de /metadata para preparar sin conexión')
    init.add_argument('--qwen-variants',type=Path,help='JSON con variantes label/url_env/api_key_env/metadata_file opcional')
    run=sub.add_parser('run',help='Ejecutar o reanudar sin sobrescribir resultados')
    run.add_argument('--campaign',type=Path,required=True)
    run.add_argument('--architectures',nargs='+',choices=['gpt_direct','qwen_clips','reference_clips'])
    run.add_argument('--condition',action='append',dest='condition_labels',help='Seleccionar etiqueta de variante o condición; repetible')
    run.add_argument('--case-id',action='append',dest='case_ids')
    run.add_argument('--max-runs',type=int,help='Máximo de intentos nuevos, no de órdenes distintas; use --case-id para seleccionar órdenes')
    run.add_argument('--retry-failed',action='store_true',help='Crear un nuevo intento manual de las ejecuciones fallidas')
    check=sub.add_parser('check',help='Comprobar integridad de manifiesto, artefactos y entorno sin consultas')
    check.add_argument('--campaign',type=Path,required=True)
    evaluate=sub.add_parser('evaluate',help='Evaluar resultados guardados y preparar o importar revisión')
    evaluate.add_argument('--campaign',type=Path,required=True)
    evaluate.add_argument('--references',type=Path)
    evaluate.add_argument('--reviews',type=Path)
    evaluate.add_argument('--evaluator-version',default='1.0')
    summary=sub.add_parser('summary',help='Conteos de todos los intentos, incluidos fallos')
    summary.add_argument('--campaign',type=Path,required=True)
    summary.add_argument('--evaluator-version')
    verify=sub.add_parser('verify-justina',help='Comprobar equivalencia con adaptador, reglas y extractor integrados')
    verify.add_argument('--workspace',type=Path,default=Path(os.environ.get('JUSTINA_WS',Path.home()/'Justina')))
    verify.add_argument('--cases',type=Path)
    args=parser.parse_args()
    try:
        if args.operation=='init':
            conditions=list(args.conditions)
            if args.with_reference_control and 'reference_clips' not in conditions:conditions.append('reference_clips')
            with tempfile.TemporaryDirectory() as temp:
                inputs=args.inputs
                if args.command is not None:
                    inputs=Path(temp)/'entradas.jsonl'
                    append_jsonl(inputs,{'id':args.case_id,'intent_id':args.intent_id,'input':args.command})
                m=initialize(args.campaign,inputs,conditions,args.model,args.references,
                             args.repetitions,args.order_seed,args.request_timeout,args.planning_timeout,
                             args.total_timeout,args.prompt,args.response_schema,args.qwen_metadata,
                             args.split,args.gpt_parameters,
                             json.loads(args.qwen_variants.read_text()) if args.qwen_variants else None)
            print(f"Campaña creada: {args.campaign}\nID: {m['campaign_id']}")
        elif args.operation=='run':
            if args.max_runs is not None and args.max_runs<1:raise ValueError('max-runs debe ser positivo')
            architectures=args.architectures
            if architectures is None and default_architecture:
                architectures=[default_architecture]
                if default_architecture=='qwen_clips':architectures.append('reference_clips')
            count,failures=run_campaign(args.campaign,architectures,args.retry_failed,args.case_ids,args.max_runs,condition_labels=args.condition_labels)
            print(f'Intentos registrados: {count}; errores/timeouts: {failures}')
            return 1 if failures else 0
        elif args.operation=='check':
            load_campaign(args.campaign);print('Configuración, artefactos y entorno: OK')
        elif args.operation=='evaluate':
            count=evaluate_campaign(args.campaign,args.references,args.evaluator_version,args.reviews)
            print(f'Evaluaciones añadidas: {count}; la revisión semántica pendiente permanece sin calificar')
        elif args.operation=='summary':
            print(json.dumps(summarize(args.campaign,args.evaluator_version),ensure_ascii=False,indent=2))
        else:
            from .verify_justina import verify as verify_sources
            result=verify_sources(args.workspace,args.cases)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['equivalent'] else 1
    except KeyboardInterrupt:
        print('Interrumpido. El diario conserva los intentos iniciados; run permite reanudar.')
        return 130
    except Exception as exc:
        # Local validation exceptions are explanatory; transport exceptions may contain credentials.
        from .common import ExperimentError
        print(f'Error: {str(exc) if isinstance(exc,(ValueError,ExperimentError)) else type(exc).__name__}')
        return 2
    return 0
