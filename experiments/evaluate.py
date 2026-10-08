"""Evaluación posterior sobre evidencia guardada, sin consultar modelos."""
from collections import Counter, defaultdict
from pathlib import Path

from .common import (append_jsonl, campaign_lock, digest, read_jsonl, utc,
                     object_digest, ROOT, read_json)
from .campaign import load_campaign
from .validation import plan_issues

REVIEW_FIELDS = {'semantic_correct','task_fulfillment','domain_response_correct',
                 'failed_checks','error_categories','review_notes','reviewer','reviewed_at_utc'}
CATEGORIES = {'interpretation','adaptation','planning','infrastructure','output_truncation'}


def control_exclusion(row):
    if row['architecture'] == 'reference_clips':
        kind = (row.get('error') or {}).get('type')
        if kind in ('ReferenceNotApproved', 'ReferenceNotApplicable'):
            return kind
    return None


def evaluate_campaign(directory, references=None, evaluator_version='1.0', reviews=None):
    directory=Path(directory).resolve()
    with campaign_lock(directory):
        manifest=load_campaign(directory)
        ref_path=Path(references) if references else (
            directory/manifest['references']['path'] if manifest['references'] else None)
        if not ref_path or not ref_path.is_file():raise ValueError('Se requiere un archivo de referencias')
        ref_rows=read_jsonl(ref_path)
        refs={r['id']:r for r in ref_rows}
        if len(refs)!=len(ref_rows):raise ValueError('IDs duplicados en referencias')
        ref_version=digest(ref_path)
        results=read_jsonl(directory/manifest['output_path'])
        result_ids={r['run_id'] for r in results}
        review_rows=read_jsonl(reviews) if reviews else []
        review_by_id={r['run_id']:r for r in review_rows}
        if len(review_by_id)!=len(review_rows):raise ValueError('Revisiones duplicadas')
        if set(review_by_id)-result_ids:raise ValueError('Revisión con run_id desconocido')
        output=directory/'evaluaciones.jsonl'
        old={(r['run_id'],r['reference_version'],r['evaluator_version']):r for r in read_jsonl(output)}
        pending=[]
        for result in results:
            ref=refs.get(result['case_id'])
            if ref and ref.get('input')!=result['input_original']:
                raise ValueError('Referencia con entrada diferente al resultado')
            row={'schema_version':'1.0','example_only':False,'run_id':result['run_id'],
                 'reference_version':ref_version,'evaluator_version':evaluator_version,
                 'evaluation_status':'pending','goals_exact_match':None,'semantic_correct':None,
                 'plan_contract_valid':None,'task_fulfillment':'pending','domain_response_correct':None,
                 'failed_checks':[],'error_categories':[],'review_notes':'','reviewer':None,'reviewed_at_utc':None,
                 'result_sha256':object_digest(result),'review_sha256':None}
            is_control=result['architecture']=='reference_clips'
            if result['response_kind']=='plan' and result['plan'] is not None:
                row['plan_contract_valid']=not plan_issues(result['plan'])
            approved=ref and ref.get('reference_status')=='approved' and ref.get('example_only') is not True
            applicable=approved and ref.get('goals_ref') is not None
            if applicable and not is_control:
                row['goals_exact_match']=result['goals_pred']==ref['goals_ref']
            if approved and ref.get('goals_ref') is None:
                row['task_fulfillment']='not_applicable'
            if control_exclusion(result):
                row['task_fulfillment']='not_applicable'
                row['review_notes']='Control no sometido: '+control_exclusion(result)
            if applicable and not control_exclusion(result) and result['execution_status'] in ('error','timeout'):
                row['task_fulfillment']='fail'
                kind=(result.get('error') or {}).get('type')
                if kind in ('OutputTruncation',):row['error_categories']=['output_truncation']
                elif result['execution_status']=='timeout' or kind in ('ConnectError','APIConnectionError','WorkerExited'):
                    row['error_categories']=['infrastructure']
                row['failed_checks']=['No se obtuvo un recorrido completo; consultar error y evidencia parcial']
            review=review_by_id.get(result['run_id'])
            if review:
                if control_exclusion(result):
                    raise ValueError('Un control no sometido no admite un dictamen de planificación; ejecutar un nuevo control con referencias revisadas')
                if not approved:raise ValueError('La revisión final requiere referencias approved')
                if not review.get('reviewer') or not review.get('reviewed_at_utc'):
                    raise ValueError('La revisión requiere reviewer y reviewed_at_utc')
                if review.get('reference_version')!=ref_version:
                    raise ValueError('La revisión debe identificar el SHA-256 del archivo de referencias')
                if review.get('task_fulfillment') not in ('pass','fail','not_verifiable','not_applicable'):
                    raise ValueError('Falta un dictamen de cumplimiento válido')
                if not set(review.get('error_categories',[]))<=CATEGORIES:
                    raise ValueError('Categoría de error desconocida')
                if not applicable and review['task_fulfillment']!='not_applicable':
                    raise ValueError('Sin tarea de referencia, task_fulfillment debe ser not_applicable')
                if applicable and review['task_fulfillment']=='not_applicable':
                    raise ValueError('La referencia contiene una tarea ejecutable')
                if is_control and review.get('semantic_correct') is not None:
                    raise ValueError('El control no tiene interpretación lingüística que calificar')
                for k in ('semantic_correct','domain_response_correct'):
                    if review.get(k) is not None and type(review[k]) is not bool:
                        raise ValueError(f'{k} debe ser booleano o null')
                row.update({k:v for k,v in review.items() if k in REVIEW_FIELDS})
                row['evaluation_status']='completed'
                row['review_sha256']=object_digest(review)
            key=(row['run_id'],ref_version,evaluator_version)
            if key in old:
                if old[key]!=row:raise ValueError('Evaluación existente diferente; usar un evaluator_version nuevo')
                continue
            from jsonschema import Draft202012Validator
            Draft202012Validator(read_json(ROOT/'schemas/evaluation.schema.json')).validate(row)
            pending.append(row)
        for row in pending:append_jsonl(output,row)
        return len(pending)


def summarize(directory, evaluator_version=None):
    directory=Path(directory)
    manifest=load_campaign(directory)
    rows=read_jsonl(directory/manifest['output_path'])
    labels={c['config_id']:c.get('label',c['architecture']) for c in manifest['configs']}
    counts=defaultdict(Counter)
    for r in rows:
        c=counts[labels[r['config_id']]]
        c['attempts']+=1
        exclusion=control_exclusion(r)
        if exclusion:
            c['control_not_submitted']+=1;c[exclusion]+=1
        else:c['execution_'+r['execution_status']]+=1
        c['response_'+str(r['response_kind'])]+=1
        for name in ('response_schema_valid','goals_schema_valid','plan_contract_valid'):
            value=r['validation'][name]
            c[name+'_'+('not_evaluated' if value is None else str(value).lower())]+=1
    # An interrupted first attempt must not be replaced by a successful retry.
    known_ids={r['run_id'] for r in rows}
    interrupted=[]
    for event in read_jsonl(directory/'journal.jsonl'):
        if event['event']=='started' and event['run_id'] not in known_ids:
            row=dict(event['record'])
            row['execution_status']='interrupted_unknown'
            interrupted.append(row)
    first_attempts={}
    latest_attempts={}
    for row in rows+interrupted:
        key=(row['case_id'],row['config_id'],row['repetition'])
        if key not in first_attempts or row['attempt']<first_attempts[key]['attempt']:
            first_attempts[key]=row
        if key not in latest_attempts or row['attempt']>latest_attempts[key]['attempt']:
            latest_attempts[key]=row
    all_evaluations=read_jsonl(directory/'evaluaciones.jsonl')
    versions=sorted({e['evaluator_version'] for e in all_evaluations})
    if evaluator_version is None and len(versions)==1:
        evaluator_version=versions[0]
    evaluations=[e for e in all_evaluations if e['evaluator_version']==evaluator_version]
    if len({e['reference_version'] for e in evaluations})>1:
        raise ValueError('La versión del evaluador contiene referencias diferentes; usar versiones separadas')
    by_run={e['run_id']:e for e in evaluations}
    def assess(selected):
        assessment=defaultdict(Counter)
        for row in selected.values():
            c=assessment[labels[row['config_id']]]
            c['scheduled_repetitions_observed']+=1
            exclusion=control_exclusion(row)
            if exclusion:
                c['control_not_submitted']+=1;c[exclusion]+=1
                continue
            c['execution_'+row['execution_status']]+=1
            e=by_run.get(row['run_id'])
            if e is None:
                c['evaluation_missing']+=1
                continue
            c['evaluation_'+e['evaluation_status']]+=1
            c['fulfillment_'+e['task_fulfillment']]+=1
            for key in ('goals_exact_match','semantic_correct','domain_response_correct'):
                value=e.get(key)
                c[key+'_'+('not_evaluated' if value is None else str(value).lower())]+=1
        semantic_summary={}
        for arch,c in assessment.items():
            summary=dict(c)
            for metric in ('goals_exact_match','semantic_correct','domain_response_correct'):
                numerator=c[metric+'_true']
                denominator=numerator+c[metric+'_false']
                summary[metric+'_rate']={'numerator':numerator,'denominator':denominator,
                                        'value':numerator/denominator if denominator else None}
            semantic_summary[arch]=summary
        for label,summary in semantic_summary.items():
            selected_rows=[r for r in selected.values() if labels[r['config_id']]==label]
            resources={}
            for scope in ('client','model_internal'):
                observations=[r.get('resources',{}).get(scope,{}) for r in selected_rows]
                resources[scope]={}
                for metric in ('cpu_seconds','rss_peak_sampled_bytes'):
                    values=[o[metric] for o in observations if o.get('status')=='available'
                            and isinstance(o.get(metric),(int,float)) and not isinstance(o.get(metric),bool)]
                    resources[scope][metric]={'measured_count':len(values),'unavailable_count':len(observations)-len(values),
                        'mean':sum(values)/len(values) if values else None,'max':max(values) if values else None,
                        'display':'available' if values else 'no disponibles'}
            summary['resources']=resources
        return semantic_summary
    return {'campaign_id':manifest['campaign_id'],'unit':'attempt; repeated intentions are not independent',
            'evaluator_version':evaluator_version,'available_evaluator_versions':versions,
            'primary_first_attempt_per_repetition':assess(first_attempts),
            'recovery_latest_attempt_per_repetition':assess(latest_attempts),
            'conditions':{c.get('label',c['architecture']):{'config_id':c['config_id'],'architecture':c['architecture'],
                          'model':c.get('model') or c.get('qwen',{}).get('base_model')} for c in manifest['configs']},
            'architectures':{k:dict(v) for k,v in counts.items()},
            'note':'Estos conteos de ejecución/formato no son exactitud semántica ni éxito físico.'}
