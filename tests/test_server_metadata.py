"""Contrato HTTP real con backend simulado, sin cargar Qwen."""
from http.server import ThreadingHTTPServer
import json
import threading
import time
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request

from qwen_gpsr.runtime.server import QwenRequestHandler, QwenHTTPServer


class ServerMetadataTests(unittest.TestCase):
    def test_metadata_authentication_and_response_fingerprint(self):
        class Handler(QwenRequestHandler):
            api_key='fixture-secret'
            max_body_bytes=8192
            backend=SimpleNamespace(
                metadata={'effective_config_sha256':'fixture-digest','generation':{'do_sample':False}},
                adapter_path='fixture',started_at=time.time(),
                translate=lambda command:{'normalized_input':command,'prediction':{'goals':['go(kitchen)']}})
            def log_message(self,*args):pass
        server=QwenHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(url+'/metadata')
            self.assertEqual(caught.exception.code,401)
            request=urllib.request.Request(url+'/metadata',headers={'Authorization':'Bearer fixture-secret'})
            with urllib.request.urlopen(request) as response:
                metadata=json.load(response)
            request=urllib.request.Request(url+'/translate',data=b'{"command":"go kitchen"}',
                headers={'Authorization':'Bearer fixture-secret','Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                payload=json.load(response)
            self.assertEqual(metadata['effective_config_sha256'],payload['effective_config_sha256'])
            self.assertEqual(payload['result']['prediction']['goals'],['go(kitchen)'])
            self.assertNotIn('fixture-secret',json.dumps(metadata))
        finally:server.shutdown();server.server_close();thread.join()

    def test_status_tracks_active_requests_and_finished_identity(self):
        release=threading.Event()
        entered=threading.Event()
        def translate(command):
            entered.set()
            release.wait(5)
            return {'prediction':{'goals':['go(kitchen)']}}
        class Handler(QwenRequestHandler):
            api_key='fixture-secret'
            max_body_bytes=8192
            backend=SimpleNamespace(metadata={'effective_config_sha256':'fixture'},translate=translate)
            def log_message(self,*args):pass
        server=QwenHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        headers={'Authorization':'Bearer fixture-secret'}
        def status(rid):
            req=urllib.request.Request(url+'/status?run_id='+rid,headers=headers)
            with urllib.request.urlopen(req) as response:return json.load(response)
        def request():
            req=urllib.request.Request(url+'/translate',data=b'{"command":"go kitchen"}',
                headers={**headers,'X-Experiment-Run-ID':'run-1'})
            with urllib.request.urlopen(req) as response:response.read()
        client=threading.Thread(target=request)
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(url+'/status?run_id=run-1')
            self.assertEqual(caught.exception.code,401)
            self.assertFalse(status('unknown')['request_finished'])
            client.start();self.assertTrue(entered.wait(2))
            busy=status('run-1')
            self.assertFalse(busy['idle']);self.assertEqual(busy['pending_requests'],1)
            self.assertFalse(busy['request_finished'])
            release.set();client.join(3)
            # Wait for handler finally, which follows writing the response.
            for _ in range(20):
                idle=status('run-1')
                if idle['request_finished']:break
                time.sleep(.01)
            self.assertTrue(idle['idle']);self.assertTrue(idle['request_finished'])
            self.assertEqual(idle['pending_requests'],0)
        finally:
            release.set()
            if client.ident:client.join(3)
            server.shutdown();server.server_close();thread.join()
