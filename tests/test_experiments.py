"""Pruebas experimentales con servicios simulados y CLIPS real, sin API de pago."""
import copy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.backends import Backend
from experiments.campaign import initialize, load_campaign
from experiments.common import (INITIAL_STATE, ROOT, REPO, append_jsonl, digest,
                                new_record, read_jsonl, read_json, write_json, ExperimentError)
from experiments.evaluate import evaluate_campaign, summarize
from experiments.runner import run_campaign, Worker
from experiments.symbolic import SymbolicPlanner
from experiments.validation import validate_gpt
from experiments.verify_justina import verify

METADATA={'effective_config_sha256':'test-server-config','base_model':'fixture-qwen',
          'base_model_revision':None,'adapter_path':'fixture-only',
          'adapter_inventory':{'sha256':'fixture-adapter'},'normalizer_sha256':'fixture-normalizer',
          'catalogs_inventory':{'sha256':'fixture-catalog'},
          'generation':{'do_sample':False,'max_new_tokens':128}}


@contextmanager
def mock_qwen(mode='ok'):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps(METADATA).encode())
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(data)
            if mode=='timeout':time.sleep(.8)
            if mode=='invalid':body='NOT JSON';code=200
            elif mode=='http_error':body=json.dumps({'ok':False,'error':'Invalid JSON','raw':'{"goals":['});code=422
            else:
                body=json.dumps({'ok':True,'result':{'normalized_input':'go to the kitchen',
                     'prediction':{'goals':['go(kitchen)']}},'elapsed_ms':12.3,
                     'resource_usage':{'status':'available','scope':'fixture_server','cpu_seconds':.25,'rss_peak_sampled_bytes':4096},
                     'effective_config_sha256':METADATA['effective_config_sha256']});code=200
            self.send_response(code);self.end_headers()
            try:self.wfile.write(body.encode())
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with patch.dict(os.environ,{'QWEN_SERVER_URL':f'http://127.0.0.1:{server.server_port}','QWEN_API_KEY':'test-secret'}):
        try:yield requests
        finally:server.shutdown();server.server_close();thread.join()


def blocked_worker(connection,directory,config,state):
    connection.send(('ready',{'initialization_ms':0,'clips_load_ms':0,'model_load_ms':None}))
    record,_=connection.recv()
    record['goals_pred']=['go(kitchen)']
    record['qwen_clips']={'clips_facts':['known partial fact']}
    connection.send(('stage','planning',time.perf_counter(),record))
    time.sleep(10)


class CampaignFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.inputs=self.base/'inputs.jsonl';self.refs=self.base/'refs.jsonl'
        append_jsonl(self.inputs,{'id':'CASE-1','input':'Go to the kitchen.','intent_id':'INT-1'})
        append_jsonl(self.refs,{'id':'CASE-1','input':'Go to the kitchen.','intent_id':'INT-1',
                              'reference_status':'approved','goals_ref':['go(kitchen)'],
                              'expected_status':'executable','example_only':False})
        self.campaign=self.base/'campaign'
    def tearDown(self):self.temp.cleanup()
    def init_control(self):
        return initialize(self.campaign,self.inputs,['reference_clips'],references=self.refs)



class CampaignTests(CampaignFixture):
    def test_real_clips_control_resume_and_offline_evaluation(self):
        self.init_control()
        count,failures=run_campaign(self.campaign)
        self.assertEqual((count,failures),(1,0))
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertIsNone(row['goals_pred'])
        self.assertTrue(row['reference_clips']['planning_done'])
        self.assertEqual(row['reference_clips']['remaining_goals'],[])
        self.assertTrue(row['validation']['plan_contract_valid'])
        self.assertIsNone(row['timing']['model_request_ms'])
        before=(self.campaign/'resultados.jsonl').read_bytes()
        self.assertEqual(run_campaign(self.campaign),(0,0))
        self.assertEqual(evaluate_campaign(self.campaign),1)
        evaluation=read_jsonl(self.campaign/'evaluaciones.jsonl')[0]
        self.assertIsNone(evaluation['semantic_correct'])
        self.assertIsNone(evaluation['goals_exact_match'])
        self.assertEqual(evaluation['evaluation_status'],'pending')
        self.assertEqual((self.campaign/'resultados.jsonl').read_bytes(),before)
        self.assertEqual(evaluate_campaign(self.campaign),0)

    def test_qwen_only_sends_order_and_matches_control(self):
        with mock_qwen() as requests:
            initialize(self.campaign,self.inputs,['qwen_clips','reference_clips'],references=self.refs)
            self.assertEqual(run_campaign(self.campaign),(2,0))
        rows=read_jsonl(self.campaign/'resultados.jsonl')
        qwen=next(r for r in rows if r['architecture']=='qwen_clips')
        control=next(r for r in rows if r['architecture']=='reference_clips')
        self.assertEqual(requests,[{'command':'Go to the kitchen.'}])
        self.assertEqual(qwen['plan'],control['plan'])
        self.assertEqual(qwen['qwen_clips']['clips_facts'],control['reference_clips']['clips_facts'])
        self.assertEqual(json.loads(qwen['raw_output'])['elapsed_ms'],12.3)
        self.assertEqual(qwen['qwen_clips']['server_elapsed_ms'],12.3)
        self.assertIsNone(qwen['reference_clips'])

    def test_qwen_invalid_output_and_http_error_recorded_without_retries(self):
        for mode in ('invalid','http_error'):
            with self.subTest(mode=mode),mock_qwen(mode) as requests:
                directory=self.base/mode
                initialize(directory,self.inputs,['qwen_clips'])
                self.assertEqual(run_campaign(directory),(1,1))
                row=read_jsonl(directory/'resultados.jsonl')[0]
                self.assertEqual(row['execution_status'],'error')
                self.assertIsNone(row['response_kind'])
                self.assertIsNone(row['plan'])
                self.assertIsNotNone(row['raw_output'])
                self.assertEqual(run_campaign(directory),(0,0))
                self.assertEqual(len(requests),1)
                self.assertEqual(run_campaign(directory,retry_failed=True),(1,1))
                rows=read_jsonl(directory/'resultados.jsonl')
                self.assertEqual([r['attempt'] for r in rows],[1,2])
                self.assertNotEqual(rows[0]['run_id'],rows[1]['run_id'])

    def test_request_timeout_is_terminal_and_has_duration(self):
        with mock_qwen('timeout'):
            initialize(self.campaign,self.inputs,['qwen_clips'],request_timeout=.1,total_timeout=1)
            with self.assertRaisesRegex(ExperimentError,'Campaña detenida'):
                run_campaign(self.campaign)
            with self.assertRaisesRegex(ExperimentError,'Campaña detenida'):
                run_campaign(self.campaign)
            self.assertEqual(len(read_jsonl(self.campaign/'resultados.jsonl')),1)
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertEqual(row['execution_status'],'timeout')
        self.assertGreater(row['timing']['model_request_ms'],0)
        self.assertIsNone(row['validation']['plan_contract_valid'])
        self.assertLess(row['timing']['total_ms'],1500)

    def test_planning_hard_deadline_retains_partial_evidence(self):
        manifest=self.init_control();config=manifest['configs'][0]
        record=new_record(manifest,config,{'id':'1','input':'x'},1,1)
        worker=Worker(self.campaign,config,INITIAL_STATE,target=blocked_worker)
        try:
            row=worker.run(record,None,{'planning':.05,'total':1},lambda *a:None)
            self.assertEqual(row['execution_status'],'timeout')
            self.assertEqual(row['goals_pred'],['go(kitchen)'])
            self.assertEqual(row['qwen_clips']['clips_facts'],['known partial fact'])
            self.assertFalse(worker.process.is_alive())
            self.assertLess(row['timing']['total_ms'],300)
        finally:worker.close()

    def test_incomplete_attempt_gets_new_id_not_fabricated_result(self):
        manifest=self.init_control()
        record=new_record(manifest,manifest['configs'][0],{'id':'CASE-1','input':'Go to the kitchen.'},1,1)
        append_jsonl(self.campaign/'journal.jsonl',{'event':'started','run_id':record['run_id'],'record':record})
        run_campaign(self.campaign)
        rows=read_jsonl(self.campaign/'resultados.jsonl')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['attempt'],2)
        self.assertNotEqual(rows[0]['run_id'],record['run_id'])
        self.assertTrue(any(e['event']=='interrupted_unknown' for e in read_jsonl(self.campaign/'journal.jsonl')))

    def test_pending_reference_is_not_used_as_gold(self):
        self.refs.write_text(json.dumps({'id':'CASE-1','input':'Go to the kitchen.',
                         'reference_status':'pending','goals_ref':['go(kitchen)']})+'\n')
        self.init_control();run_campaign(self.campaign)
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertEqual(row['error']['type'],'ReferenceNotApproved')
        self.assertIsNone(row['plan'])

    def test_manifest_and_input_tampering_rejected(self):
        self.init_control()
        path=self.campaign/'assets/entradas.jsonl'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'Artefacto modificado'):load_campaign(self.campaign)

    def test_changed_server_configuration_is_rejected_before_order(self):
        with mock_qwen() as requests:
            initialize(self.campaign,self.inputs,['qwen_clips'])
            with patch.dict(METADATA,{'effective_config_sha256':'other'}):
                run_campaign(self.campaign)
            self.assertEqual(requests,[])
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertEqual(row['error']['type'],'ServerConfigurationChanged')


class GPTTests(unittest.TestCase):
    def setUp(self):
        self.schema=read_json(REPO/'chatgpt_planner/response_schema.json')
        self.example=read_jsonl(REPO/'chatgpt_planner/example_outputs.jsonl')[0]['response']
    def run_response(self,text,status='completed',refusal=False,reason=None):
        provider={'id':'fixture-response','model':'fixture-model','status':status,
                  'usage':{'input_tokens':10,'output_tokens':20,'total_tokens':30,
                           'input_tokens_details':{'cached_tokens':3},'output_tokens_details':{'reasoning_tokens':4}},
                  'output':[{'content':[{'type':'refusal','refusal':'fixture'}]}] if refusal else [],
                  'incomplete_details':{'reason':reason} if reason else None}
        response=SimpleNamespace(output_text=text,model_dump=lambda **kwargs:provider)
        calls=[]
        def create(**kwargs):calls.append(kwargs);return response
        backend=Backend.__new__(Backend)
        backend.architecture='gpt_direct';backend.prompt='fixed prompt';backend.schema=self.schema
        backend.config={'model':'fixture-model','generation':{'store':False,'max_output_tokens':1024}}
        backend.client=SimpleNamespace(responses=SimpleNamespace(create=create))
        row=new_record({'campaign_id':'x'},{'architecture':'gpt_direct','config_id':'x'},
                       {'id':'case','input':'original instruction'},1,1)
        return backend.execute(row,None,lambda *a:None),calls
    def test_executable_preserves_order_and_provider(self):
        row,calls=self.run_response(json.dumps(self.example))
        self.assertEqual(row['execution_status'],'completed')
        self.assertEqual(row['plan'],self.example['plan'])
        self.assertEqual(row['resources']['model_internal']['status'],'unavailable')
        self.assertIsNone(row['resources']['model_internal']['cpu_seconds'])
        self.assertEqual(row['resources']['client']['status'],'available')
        self.assertEqual(row['gpt']['usage']['total_tokens'],30)
        self.assertEqual(row['gpt']['usage']['reasoning_tokens'],4)
        self.assertEqual(calls[0]['input'],[{'role':'system','content':'fixed prompt'},
                                         {'role':'user','content':'original instruction'}])
        self.assertNotIn('previous_response_id',calls[0])
        self.assertIsNotNone(row['gpt']['provider_response'])
    def test_clarification_and_rejection_not_scored_as_empty_plan(self):
        for status in ('clarification','rejected'):
            result={'status':status,'message':'fixture reason','goals':[],'plan':[],'start_note':'','end_note':''}
            row,_=self.run_response(json.dumps(result))
            self.assertEqual(row['response_kind'],status)
            self.assertEqual(row['goals_pred'],[])
            self.assertTrue(row['validation']['response_schema_valid'])
            self.assertIsNone(row['validation']['plan_contract_valid'])
            self.assertIsNone(row['validation']['goals_schema_valid'])
    def test_invalid_json_completed_but_invalid(self):
        row,_=self.run_response('not json')
        self.assertEqual(row['execution_status'],'completed')
        self.assertFalse(row['validation']['response_schema_valid'])
        self.assertIsNone(row['response_kind'])
        self.assertEqual(row['raw_output'],'not json')
    def test_provider_refusal_and_truncation_not_domain_rejections(self):
        for status,refusal,reason in [('completed',True,None),('incomplete',False,'max_output_tokens')]:
            row,_=self.run_response('partial',status,refusal,reason)
            self.assertEqual(row['execution_status'],'error')
            self.assertIsNone(row['response_kind'])
            self.assertEqual(row['raw_output'],'partial')
            self.assertIsNotNone(row['gpt']['provider_response'])
    def test_invalid_numbering_preserved(self):
        result=copy.deepcopy(self.example);result['plan'][0]['step']=42
        row,_=self.run_response(json.dumps(result))
        self.assertFalse(row['validation']['plan_contract_valid'])
        self.assertEqual(row['plan'][0]['step'],42)
    def test_missing_and_invalid_types_not_fabricated(self):
        row,_=self.run_response(json.dumps({'status':'executable','goals':12,'plan':None}))
        self.assertIsNone(row['goals_pred']);self.assertIsNone(row['plan'])
        self.assertFalse(row['validation']['response_schema_valid'])


class SymbolicTests(unittest.TestCase):
    def test_reset_no_state_or_held_object_leak(self):
        planner=SymbolicPlanner([ROOT/'vendor/goals_planning.clp'])
        try:
            _,facts=planner.adapt(['go(kitchen)']);fired=planner.plan(facts,INITIAL_STATE)
            first=planner.extract(fired)[0]
            _,other=planner.adapt(['go(bed)','find(apple, kind=object)','take(apple)'])
            planner.plan(other,INITIAL_STATE)
            fired=planner.plan(facts,INITIAL_STATE)
            self.assertEqual(first,planner.extract(fired)[0])
        finally:planner.close()
    def test_current_justina_equivalence(self):
        workspace=Path(os.environ.get('JUSTINA_WS',Path.home()/'Justina'))
        if not (workspace/'src/Planning/clips/clips_node').exists():self.skipTest('Justina no disponible')
        self.assertTrue(verify(workspace)['equivalent'])


class RobustnessTests(CampaignFixture):
    """Escenarios adicionales sin repetir las pruebas de CampaignTests."""
    def test_initialization_failure_does_not_leave_partial_campaign(self):
        with self.assertRaises(ValueError):
            initialize(self.campaign,self.inputs,['gpt_direct'],model='fixture',gpt_parameters={'store':True})
        self.assertFalse(self.campaign.exists())

    def test_reference_review_versioned_and_results_untouched(self):
        self.init_control();run_campaign(self.campaign)
        evaluate_campaign(self.campaign)
        result=read_jsonl(self.campaign/'resultados.jsonl')[0]
        original=(self.campaign/'resultados.jsonl').read_bytes()
        reviews=self.base/'reviews.jsonl'
        append_jsonl(reviews,{'run_id':result['run_id'],'reference_version':digest(self.campaign/'assets/referencias.jsonl'),
                             'task_fulfillment':'pass','semantic_correct':None,'reviewer':'test reviewer',
                             'reviewed_at_utc':'2026-09-24T00:00:00Z'})
        with self.assertRaisesRegex(ValueError,'evaluator_version'):
            evaluate_campaign(self.campaign,reviews=reviews)
        self.assertEqual(evaluate_campaign(self.campaign,evaluator_version='review-2',reviews=reviews),1)
        self.assertEqual((self.campaign/'resultados.jsonl').read_bytes(),original)

    def test_campaign_lock_excludes_concurrent_writer(self):
        from experiments.common import campaign_lock
        self.init_control()
        with campaign_lock(self.campaign):
            with self.assertRaisesRegex(ValueError,'otro proceso'):
                run_campaign(self.campaign)

    def test_no_applicable_reference_is_not_empty_goal_success(self):
        self.refs.write_text(json.dumps({'id':'CASE-1','input':'Go to the kitchen.',
                         'reference_status':'approved','goals_ref':None})+'\n')
        self.init_control();run_campaign(self.campaign)
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertEqual(row['error']['type'],'ReferenceNotApplicable')
        self.assertIsNone(row['goals_pred'])
        self.assertIsNone(row['validation']['goals_schema_valid'])
        evaluate_campaign(self.campaign)
        self.assertEqual(read_jsonl(self.campaign/'evaluaciones.jsonl')[0]['task_fulfillment'],'not_applicable')

    def test_truncated_jsonl_is_not_overwritten(self):
        self.init_control()
        output=self.campaign/'resultados.jsonl'
        output.write_text('{"run_id":')
        with self.assertRaises(ValueError):run_campaign(self.campaign)
        self.assertEqual(output.read_text(),'{"run_id":')

    def test_explicit_total_deadline_overrides_stage(self):
        manifest=self.init_control();config=manifest['configs'][0]
        worker=Worker(self.campaign,config,INITIAL_STATE,target=blocked_worker)
        try:
            row=worker.run(new_record(manifest,config,{'id':'1','input':'x'},1,1),None,
                           {'planning':10,'total':.05},lambda *a:None)
            self.assertEqual(row['error']['deadline_kind'],'total')
            self.assertFalse(worker.process.is_alive())
        finally:worker.close()


class SDKBoundaryTests(unittest.TestCase):
    def test_actual_sdk_request_shape_and_error_capture(self):
        import httpx
        from openai import OpenAI
        example=read_jsonl(REPO/'chatgpt_planner/example_outputs.jsonl')[0]['response']
        calls=[]
        def respond(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':1,
                'model':'fixture-model','status':'completed','output':[{'id':'msg_test','type':'message',
                'role':'assistant','status':'completed','content':[{'type':'output_text',
                'text':json.dumps(example),'annotations':[]}]}],
                'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}})
        client=OpenAI(api_key='fixture-key',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        backend=Backend.__new__(Backend)
        backend.architecture='gpt_direct';backend.prompt='fixed';backend.schema=read_json(REPO/'chatgpt_planner/response_schema.json')
        backend.config={'model':'fixture-model','generation':{'store':False,'max_output_tokens':1000},'timeouts_seconds':{'model_request':1}}
        backend.client=client
        try:
            row=backend.execute(new_record({'campaign_id':'x'},{'architecture':'gpt_direct','config_id':'x'},
                               {'id':'x','input':'go kitchen'},1,1),None,lambda *a:None)
            self.assertEqual(row['execution_status'],'completed')
            self.assertFalse(calls[0]['store'])
            self.assertEqual(calls[0]['text']['format']['type'],'json_schema')
            self.assertTrue(calls[0]['text']['format']['strict'])
            self.assertNotIn('temperature',calls[0])
            self.assertEqual(row['gpt']['response_id'],'resp_test')
        finally:client.close()

    def test_transport_failure_retains_elapsed_time_and_redacts_credentials(self):
        from experiments.runner import redact_record
        import httpx
        backend=Backend.__new__(Backend);backend.architecture='gpt_direct';backend.prompt='fixed'
        backend.schema=read_json(REPO/'chatgpt_planner/response_schema.json')
        backend.config={'model':'fixture','generation':{'store':False},'timeouts_seconds':{'model_request':1}}
        def fail(**kwargs):raise httpx.ConnectError('secret-in-exception')
        backend.client=SimpleNamespace(responses=SimpleNamespace(create=fail))
        row=backend.execute(new_record({'campaign_id':'x'},{'architecture':'gpt_direct','config_id':'x'},
                            {'id':'x','input':'instruction'},1,1),None,lambda *a:None)
        self.assertEqual(row['execution_status'],'error')
        self.assertIsNotNone(row['timing']['model_request_ms'])
        self.assertNotIn('secret-in-exception',json.dumps(row))
        row['raw_output']='provider echoed secret-value'
        with patch.dict(os.environ,{'OPENAI_API_KEY':'secret-value'}):
            scrubbed=redact_record(row,[{'api_key_env':'OPENAI_API_KEY'}])
        self.assertNotIn('secret-value',json.dumps(scrubbed))
        self.assertTrue(scrubbed['credential_redaction_applied'])

if __name__ == '__main__':
    unittest.main()


class SummaryPolicyTests(CampaignFixture):
    def test_first_failure_remains_after_successful_retry(self):
        manifest=self.init_control();config=manifest['configs'][0]
        case={'id':'CASE-1','input':'Go to the kitchen.'}
        first=new_record(manifest,config,case,1,1)
        first.update(execution_status='error', error={'type':'PlanningIncomplete'})
        second=new_record(manifest,config,case,1,2)
        second.update(execution_status='completed')
        # Deliberately reversed file order: attempt number defines the views.
        for row in (second,first):append_jsonl(self.campaign/'resultados.jsonl',row)
        evaluate_campaign(self.campaign)
        summary=summarize(self.campaign)
        main=summary['primary_first_attempt_per_repetition']['reference_clips']
        recovery=summary['recovery_latest_attempt_per_repetition']['reference_clips']
        self.assertEqual(main['execution_error'],1)
        self.assertEqual(main['fulfillment_fail'],1)
        self.assertEqual(recovery['execution_completed'],1)
        self.assertNotIn('execution_error',recovery)

    def test_excluded_controls_are_not_planning_failures(self):
        manifest=self.init_control();config=manifest['configs'][0]
        for attempt,kind in enumerate(('ReferenceNotApproved','ReferenceNotApplicable'),1):
            row=new_record(manifest,config,{'id':'CASE-1','input':'Go to the kitchen.'},1,attempt)
            row.update(execution_status='error',error={'type':kind})
            append_jsonl(self.campaign/'resultados.jsonl',row)
        evaluate_campaign(self.campaign)
        for e in read_jsonl(self.campaign/'evaluaciones.jsonl'):
            self.assertEqual(e['task_fulfillment'],'not_applicable')
            self.assertEqual(e['error_categories'],[])
        summary=summarize(self.campaign)
        self.assertEqual(summary['architectures']['reference_clips']['control_not_submitted'],2)
        self.assertNotIn('execution_error',summary['architectures']['reference_clips'])

    def test_interrupted_first_attempt_stays_in_primary(self):
        manifest=self.init_control()
        row=new_record(manifest,manifest['configs'][0],{'id':'CASE-1','input':'Go to the kitchen.'},1,1)
        append_jsonl(self.campaign/'journal.jsonl',{'event':'started','run_id':row['run_id'],'record':row})
        run_campaign(self.campaign)
        self.assertEqual(summarize(self.campaign)['primary_first_attempt_per_repetition']
                         ['reference_clips']['execution_interrupted_unknown'],1)

class IdleGateTests(CampaignFixture):
    def test_resume_requires_idle_finished_request_and_same_config(self):
        with mock_qwen():
            manifest=initialize(self.campaign,self.inputs,['qwen_clips'])
        config=manifest['configs'][0]
        row=new_record(manifest,config,{'id':'CASE-1','input':'Go to the kitchen.'},1,1)
        row.update(execution_status='timeout',error={'type':'ReadTimeout'})
        append_jsonl(self.campaign/'resultados.jsonl',row)
        before=(self.campaign/'resultados.jsonl').read_bytes()
        good={'idle':True,'pending_requests':0,'request_finished':True,
              'effective_config_sha256':METADATA['effective_config_sha256']}
        with patch.dict(os.environ,{'QWEN_SERVER_URL':'http://fixture.invalid'}):
            for changes in ({'idle':False,'pending_requests':1}, {'request_finished':False},
                            {'effective_config_sha256':'changed'}):
                response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{**good,**changes})
                with patch('experiments.runner.httpx.get',return_value=response), \
                     self.assertRaisesRegex(ExperimentError,'Campaña detenida'):
                    run_campaign(self.campaign)
            response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:good)
            with patch('experiments.runner.httpx.get',return_value=response) as get:
                self.assertEqual(run_campaign(self.campaign),(0,0))
                self.assertEqual(get.call_args.kwargs['params'],{'run_id':row['run_id']})
        self.assertEqual((self.campaign/'resultados.jsonl').read_bytes(),before)
        self.assertEqual(read_jsonl(self.campaign/'journal.jsonl')[-1]['event'],'qwen_idle_verified')

class ResourceAndVariantTests(CampaignFixture):
    def test_two_qwen_variants_stay_separate_in_summary(self):
        variants=[]
        for size in ('3B','7B'):
            path=self.base/(size+'.json')
            write_json(path,{**METADATA,'base_model':'Qwen/Qwen2.5-'+size,'effective_config_sha256':size})
            variants.append({'label':'qwen'+size,'url_env':'QWEN_'+size+'_URL',
                             'api_key_env':'QWEN_API_KEY','metadata_file':str(path)})
        manifest=initialize(self.campaign,self.inputs,['qwen_clips','gpt_direct'],model='fixture',qwen_variants=variants)
        self.assertEqual(len(manifest['configs']),3)
        self.assertEqual(len({c['config_id'] for c in manifest['configs']}),3)
        for config in manifest['configs']:
            row=new_record(manifest,config,{'id':'CASE-1','input':'Go to the kitchen.'},1,1)
            row.update(execution_status='error',error={'type':'fixture'})
            append_jsonl(self.campaign/'resultados.jsonl',row)
        result=summarize(self.campaign)
        self.assertEqual(set(result['primary_first_attempt_per_repetition']),{'qwen3B','qwen7B','gpt_direct'})
        for label in ('qwen3B','qwen7B','gpt_direct'):
            metric=result['primary_first_attempt_per_repetition'][label]['resources']['model_internal']['cpu_seconds']
            self.assertIsNone(metric['mean']);self.assertEqual(metric['unavailable_count'],1)
        self.assertEqual(run_campaign(self.campaign,condition_labels=['qwen3B']),(0,0))

    def test_gpt_internal_resources_cannot_be_zero_or_client_metrics(self):
        from jsonschema import Draft202012Validator, ValidationError
        manifest=self.init_control()
        row=new_record(manifest,{'architecture':'gpt_direct','config_id':'fixture'},
                       {'id':'CASE-1','input':'Go to the kitchen.'},1,1)
        row.update(execution_status='error',finished_at_utc='2026-10-02T00:00:00Z',
                   error={'stage':'initialization','type':'fixture','message':'fixture','limit_ms':None})
        schema=Draft202012Validator(read_json(ROOT/'schemas/result.schema.json'))
        schema.validate(row)
        self.assertEqual(row['resources']['model_internal']['display'],'no disponibles')
        row['resources']['model_internal']['cpu_seconds']=0
        with self.assertRaises(ValidationError):schema.validate(row)

    def test_process_measurement_has_scope_and_nullable_gpu(self):
        from qwen_gpsr.runtime.resources import ProcessResources
        with ProcessResources('test_client') as monitor:
            work=bytearray(1024*1024)
        result=monitor.result
        self.assertEqual(result['scope'],'test_client')
        self.assertGreater(result['rss_peak_sampled_bytes'],0)
        self.assertGreaterEqual(result['cpu_seconds'],0)
        self.assertEqual(result['gpu']['status'],'unavailable')
        self.assertIsNone(result['gpu']['devices'])


class ServerResourcePropagationTests(CampaignFixture):
    def test_server_measurement_is_distinct_from_client(self):
        with mock_qwen():
            initialize(self.campaign,self.inputs,['qwen_clips'])
            self.assertEqual(run_campaign(self.campaign),(1,0))
        row=read_jsonl(self.campaign/'resultados.jsonl')[0]
        self.assertEqual(row['resources']['model_internal']['scope'],'fixture_server')
        self.assertEqual(row['resources']['model_internal']['cpu_seconds'],.25)
        self.assertNotEqual(row['resources']['client']['scope'],'fixture_server')
        metric=summarize(self.campaign)['primary_first_attempt_per_repetition']['qwen_clips']['resources']['model_internal']['cpu_seconds']
        self.assertEqual(metric['mean'],.25)
        self.assertEqual(metric['measured_count'],1)
