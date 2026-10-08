"""Supervisión de procesos, límites efectivos, diario y reanudación."""
import multiprocessing as mp
import os
from pathlib import Path
import random
import signal
import time

from .backends import Backend, qwen_headers, qwen_url
from .evaluate import control_exclusion
from .common import ExperimentError
import httpx
from .campaign import load_campaign
from .common import (append_jsonl, read_jsonl, load_inputs, new_record, utc,
                     campaign_lock, error_info)


def worker_main(connection, directory, config, initial_state):
    backend = None
    try:
        backend = Backend(directory, config, initial_state)
        connection.send(('ready',backend.startup))
        while True:
            request = connection.recv()
            if request is None:
                break
            record, reference = request
            def emit(event, stage, tick, row):
                connection.send((event, stage, tick, row))
            result = backend.execute(record,reference,emit)
            connection.send(('result',result,time.perf_counter()))
    except (EOFError, KeyboardInterrupt):
        pass
    except Exception as exc:
        connection.send(('setup_error',error_info(exc,'initialization')))
    finally:
        if backend:
            backend.close()
        connection.close()


class Worker:
    def __init__(self,directory,config,state,target=worker_main):
        context=mp.get_context('spawn')
        self.connection,child=context.Pipe()
        self.process=context.Process(target=target,args=(child,directory,config,state),daemon=True)
        self.process.start()
        child.close()
        self.startup=None
        self.setup_error=None
        if not self.connection.poll(30):
            self.setup_error={'stage':'initialization','type':'InitializationTimeout',
                              'message':'No se pudo inicializar el proceso en 30 s','limit_ms':30000}
            self.close()
        else:
            try:
                event=self.connection.recv()
            except EOFError:
                event=('setup_error',{'stage':'initialization','type':'WorkerExited',
                                     'message':'El proceso terminó durante la carga','limit_ms':None})
            if event[0]=='ready':self.startup=event[1]
            else:self.setup_error=event[1]

    def close(self):
        if self.process.is_alive():
            try:self.connection.send(None)
            except (BrokenPipeError,OSError):pass
            self.process.join(.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(1)
        self.connection.close()

    def run(self,record,reference,limits,on_progress):
        if self.setup_error:
            record.update(execution_status='error',error=self.setup_error,finished_at_utc=utc())
            return record
        start=time.perf_counter()
        record['started_at_utc']=utc()
        try:
            self.connection.send((record,reference))
        except (BrokenPipeError, OSError):
            record.update(execution_status='error', finished_at_utc=utc(),
                          error={'stage':'dispatch','type':'WorkerExited',
                                 'message':'El proceso terminó antes de recibir la solicitud','limit_ms':None})
            record['timing']['total_ms']=(time.perf_counter()-start)*1000
            return record
        stage='dispatch'
        stage_start=start
        terminal_tick=None
        while True:
            now=time.perf_counter()
            deadlines=[(start+limits['total'],'total',limits['total'])]
            if stage in limits:
                deadlines.append((stage_start+limits[stage],stage,limits[stage]))
            end,limiting_stage,limit=min(deadlines)
            if now>=end:
                record['execution_status']='timeout'
                record['error']={'stage':stage,'type':'DeadlineExceeded',
                                 'message':f'Límite {limiting_stage} agotado; proceso aislado terminado',
                                 'limit_ms':limit*1000,'deadline_kind':limiting_stage}
                if stage+'_ms' in record['timing']:
                    record['timing'][stage+'_ms']=(now-stage_start)*1000
                terminal_tick=now
                record['error']['request_isolated'] = True
                if record['architecture'] != 'reference_clips':
                    record['error']['remote_cancellation_confirmed'] = False
                self.close()
                break
            if self.connection.poll(min(.05,end-now)):
                try:event=self.connection.recv()
                except EOFError:
                    record['execution_status']='error'
                    record['error']={'stage':stage,'type':'WorkerExited','message':'El proceso terminó sin resultado','limit_ms':None}
                    break
                if event[0]=='result':
                    record=event[1]
                    # Reception delay is client overhead; preserve measured total rather than summing stages.
                    break
                if event[0] in ('stage','progress'):
                    _,current,tick,record=event
                    if event[0]=='stage':stage,stage_start=current,tick
                    on_progress(record,stage)
                elif event[0]=='setup_error':
                    record.update(execution_status='error',error=event[1])
                    break
        record['timing']['total_ms']=((terminal_tick or time.perf_counter())-start)*1000
        record['finished_at_utc']=utc()
        return record


def redact_record(row, configs):
    secrets={os.environ.get(c.get('api_key_env',''),'') for c in configs}
    secrets.update(os.environ.get(c.get('qwen',{}).get('api_key_env',''),'') for c in configs)
    secrets.discard('')
    changed=False
    def scrub(value):
        nonlocal changed
        if isinstance(value,str):
            for secret in secrets:
                if secret in value:
                    value=value.replace(secret,'[REDACTED_CREDENTIAL]');changed=True
            return value
        if isinstance(value,list):return [scrub(v) for v in value]
        if isinstance(value,dict):return {k:scrub(v) for k,v in value.items()}
        return value
    result=scrub(row)
    if changed:result['credential_redaction_applied']=True
    return result


def task_key(row):
    return row['case_id'],row['config_id'],row['repetition']


def require_qwen_idle(config, run_id, journal_path):
    """Fail closed: a live server must acknowledge this request and have no queue."""
    try:
        response=httpx.get(qwen_url(config['qwen'])+'/status',
                           params={'run_id':run_id}, headers=qwen_headers(config['qwen']), timeout=5)
        response.raise_for_status()
        status=response.json()
        verified=(status.get('idle') is True and status.get('pending_requests') == 0
                  and status.get('request_finished') is True
                  and status.get('effective_config_sha256') == config['qwen']['effective_config_sha256'])
    except Exception:
        verified=False
    append_jsonl(journal_path,{'event':'qwen_idle_verified' if verified else 'qwen_idle_unverified',
                              'run_id':run_id,'at':utc()})
    if not verified:
        raise ExperimentError('QwenIdleUnverified',
            'Campaña detenida: no se confirmó la finalización de la solicitud Qwen y servidor libre. '
            'El fallo se conserva. Reanudar con run cuando /status pueda confirmarlo.')


def run_campaign(directory, architectures=None, retry_failed=False, case_ids=None, max_runs=None,
                 worker_factory=Worker, condition_labels=None):
    directory=Path(directory).resolve()
    with campaign_lock(directory):
        manifest=load_campaign(directory)
        configs=[c for c in manifest['configs'] if not architectures or c['architecture'] in architectures]
        if condition_labels:
            known={c.get('label',c['architecture']) for c in configs}
            if set(condition_labels)-known:raise ValueError('Condición desconocida')
            configs=[c for c in configs if c.get('label',c['architecture']) in condition_labels]
        if not configs:raise ValueError('La campaña no contiene las condiciones seleccionadas')
        cases=load_inputs(directory/manifest['inputs']['path'])
        if case_ids:
            if set(case_ids)-{c['id'] for c in cases}:raise ValueError('ID de caso desconocido')
            cases=[c for c in cases if c['id'] in case_ids]
        for c in cases:c['intent_id']=c.get('intent_id') or manifest['intent_index'].get(c['id'])
        references={}
        if any(c['architecture']=='reference_clips' for c in configs):
            references={r['id']:r for r in read_jsonl(directory/manifest['references']['path'])}
        results_path=directory/manifest['output_path']
        journal_path=directory/'journal.jsonl'
        results=read_jsonl(results_path)
        journal=read_jsonl(journal_path)
        completed_ids={r['run_id'] for r in results}
        if len(completed_ids)!=len(results):raise ValueError('run_id duplicado en resultados')
        attempts={}
        latest={}
        for row in results:
            if row['campaign_id']!=manifest['campaign_id']:raise ValueError('Resultados de otra campaña')
            key=task_key(row);latest[key]=row
            attempts[key]=max(attempts.get(key,0),row['attempt'])
        starts={j['run_id']:j for j in journal if j['event']=='started'}
        recovered={j['run_id'] for j in journal if j['event']=='interrupted_unknown'}
        for rid,j in starts.items():
            row=j['record'];key=task_key(row)
            attempts[key]=max(attempts.get(key,0),row['attempt'])
            if rid not in completed_ids and rid not in recovered:
                append_jsonl(journal_path,{'event':'interrupted_unknown','run_id':rid,'at':utc()})
        verified={j['run_id'] for j in journal if j['event']=='qwen_idle_verified'}
        all_configs={c['config_id']:c for c in manifest['configs']}
        uncertain=[r for r in results if r['architecture']=='qwen_clips' and
                   (r['execution_status']=='timeout' or (r.get('error') or {}).get('type')=='WorkerExited')]
        uncertain.extend(j['record'] for rid,j in starts.items()
                         if rid not in completed_ids and j['record']['architecture']=='qwen_clips')
        for row in uncertain:
            if row['run_id'] not in verified:
                require_qwen_idle(all_configs[row['config_id']],row['run_id'],journal_path)
        # Paired blocks: all conditions for one case/repetition, shuffled reproducibly.
        rng=random.Random(manifest['schedule']['order_seed'])
        blocks=[(case,rep) for rep in range(1,manifest['schedule']['repetitions']+1) for case in cases]
        rng.shuffle(blocks)
        workers={}
        count=0
        failures=0
        old_handler=signal.getsignal(signal.SIGTERM)
        def interrupted(signum,frame):raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,interrupted)
        try:
            for case,rep in blocks:
                ordered=list(configs);rng.shuffle(ordered)
                for config in ordered:
                    key=(case['id'],config['config_id'],rep)
                    existing=latest.get(key)
                    if existing and (not retry_failed or existing['execution_status']=='completed'):
                        continue
                    if max_runs is not None and count>=max_runs:return count,failures
                    record=new_record(manifest,config,case,rep,attempts.get(key,0)+1)
                    record['manual_retry']=bool(existing)
                    record['manifest_sha256']=(directory/'manifest.sha256').read_text().strip()
                    append_jsonl(journal_path,{'event':'started','run_id':record['run_id'],'record':redact_record(record,configs)})
                    cid=config['config_id']
                    if cid not in workers:
                        workers[cid]=worker_factory(directory,config,manifest['initial_state'])
                        append_jsonl(directory/'startup.jsonl',{'at':utc(),'config_id':cid,
                                     'startup':workers[cid].startup,'error':workers[cid].setup_error})
                    def progress(row,stage):
                        append_jsonl(journal_path,{'event':'checkpoint','run_id':row['run_id'],
                                     'stage':stage,'at':utc(),'record':redact_record(row,configs)})
                    ref=references.get(case['id']) if config['architecture']=='reference_clips' else None
                    row=workers[cid].run(record,ref,config['timeouts_seconds'],progress)
                    row=redact_record(row,configs)
                    from jsonschema import Draft202012Validator
                    from .common import ROOT, read_json
                    Draft202012Validator(read_json(ROOT/'schemas/result.schema.json')).validate(row)
                    append_jsonl(results_path,row)
                    append_jsonl(journal_path,{'event':'finished','run_id':row['run_id'],'at':utc()})
                    count+=1;failures+=row['execution_status']!='completed' and not control_exclusion(row)
                    display_status="control_not_submitted ("+control_exclusion(row)+")" if control_exclusion(row) else row["execution_status"]
                    print(f"{case['id']} {config.get('label',config['architecture'])} R{rep} A{row['attempt']}: {display_status}",flush=True)
                    if row['execution_status']=='timeout' or row['error'] and row['error']['type']=='WorkerExited':
                        workers[cid].close();del workers[cid]
                        if config['architecture']=='qwen_clips':
                            require_qwen_idle(config,row['run_id'],journal_path)
        finally:
            for worker in workers.values():worker.close()
            signal.signal(signal.SIGTERM,old_handler)
        return count,failures
