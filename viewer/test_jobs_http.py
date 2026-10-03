"""Local transport boundary tests using an isolated synthetic portfolio."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kira_jobs import JobStore, atomic
import server
ADDRESS='0x'+'1'*40

class JobsHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[{'address':ADDRESS,'address_key':ADDRESS,'tags':['Synthetic']}],'research_runs':[]})
        self.root_patch=patch.object(server,'ROOT',self.root);self.root_patch.start()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.http.controls=True;self.http.session_token=secrets.token_urlsafe(32);self.http.jobs=JobStore(self.root)
        self.launch_patch=patch.object(self.http.jobs,'launch');self.launch_patch.start()
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.launch_patch.stop();self.root_patch.stop();self.temp.cleanup()
    def request(self,path='/api/operations',headers=None,body=None,method='POST'):
        headers={'Content-Type':'application/json','Origin':self.url,'X-Kira-Session':self.http.session_token,**(headers or {})}
        body=body if body is not None else json.dumps({'schema_version':1,'operation':'wallet.setTags','input':{'wallet':ADDRESS,'tags':['New name']},'idempotency_key':'http-synthetic'}).encode()
        request=urllib.request.Request(self.url+path,data=body if method=='POST' else None,headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:return error.code,error.read().decode()
    def test_valid_submission_duplicate_and_private_state(self):
        code,first=self.request();self.assertEqual(code,202);_,duplicate=self.request();self.assertEqual(first['job_id'],duplicate['job_id'])
        self.assertEqual(self.request('/api/jobs',method='GET')[0],200)
        self.assertEqual(self.request('/api/jobs',headers={'X-Kira-Session':''},method='GET')[0],403)
    def test_session_origin_rebinding_and_cross_site_rejected(self):
        for headers in [{'X-Kira-Session':''},{'X-Kira-Session':'wrong-session'},{'Origin':'https://foreign.test'},
                        {'Host':'foreign.test:'+str(self.http.server_port)},{'Sec-Fetch-Site':'cross-site'},{'Origin':''}]:
            self.assertEqual(self.request(headers=headers)[0],403)
        self.assertEqual(len(self.http.jobs.list()),0)
    def test_json_shape_size_content_type_and_version(self):
        self.assertEqual(self.request(headers={'Content-Type':'text/plain'})[0],415)
        for body in [b'not json',b'[]',b'{"schema_version":NaN}',b'{"schema_version":2}']:
            self.assertEqual(self.request(body=body)[0],400)
        self.assertEqual(self.request(body=b'x'*65537)[0],413)
    def test_read_only_and_session_rotation(self):
        self.http.controls=False;self.assertEqual(self.request()[0],501)
        code,value=self.request('/api/session',method='GET');self.assertEqual(code,200);self.assertIsNone(value['token'])
        self.http.controls=True;token=self.http.session_token;self.http.session_token=secrets.token_urlsafe(32)
        self.assertEqual(self.request(headers={'X-Kira-Session':token})[0],403)
    def test_demo_provider_writes_blocked_and_paths_denied(self):
        registry=json.loads((self.root/'wallets.json').read_text());registry['demo']=True;atomic(self.root/'wallets.json',registry)
        body=json.dumps({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':ADDRESS},'idempotency_key':'demo-request'}).encode()
        self.assertEqual(self.request(body=body)[0],400);self.assertEqual(len(self.http.jobs.list()),0)
        for path in ['/wallets.json','/.kira.local.json','/jobs/private.json','/snapshots/private/results.json']:
            self.assertEqual(self.request(path,method='GET')[0],404)
    def test_demo_cannot_resume_a_provider_job(self):
        registry=json.loads((self.root/'wallets.json').read_text());registry['demo']=True;atomic(self.root/'wallets.json',registry)
        job=self.http.jobs.submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':ADDRESS},'idempotency_key':'demo-persisted'})
        job['state']='interrupted';self.http.jobs.save(job)
        body=json.dumps({'schema_version':1,'operation':'job.resume','input':{'job_id':job['job_id']},'idempotency_key':'demo-resume'}).encode()
        self.assertEqual(self.request(body=body)[0],400)
        self.assertEqual(self.http.jobs.get(job['job_id'])['state'],'interrupted')
        self.http.jobs.launch.assert_not_called()
    def test_origin_cannot_read_session(self):
        self.assertEqual(self.request('/api/session',headers={'Origin':'https://foreign.test'},method='GET')[0],403)

if __name__=='__main__':unittest.main()
