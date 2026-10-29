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
from kira_ows import OwsStore
import server
ADDRESS='0x'+'1'*40

class JobsHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[{'address':ADDRESS,'address_key':ADDRESS,'tags':['Synthetic']}],'research_runs':[]})
        self.root_patch=patch.object(server,'ROOT',self.root);self.root_patch.start()
        from kira_config import default_config,provider_config
        config=provider_config(default_config(),'alchemy','KIRA_HTTP_FIXTURE_KEY');config['secret_env_file']=str(self.root/'fixture.env')
        atomic(self.root/'.kira.local.json',config);(self.root/'fixture.env').write_text('KIRA_HTTP_FIXTURE_KEY=fixture-only-key\n')
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.http.controls=True;self.http.session_token=secrets.token_urlsafe(32);self.http.jobs=JobStore(self.root)
        self.http.ows=OwsStore(self.root,vault=self.root/"synthetic-vault",runner=lambda request:{"wallets":[]})
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
    def test_ows_asset_and_local_only_endpoints(self):
        with urllib.request.urlopen(self.url+'/ows.js') as response:
            self.assertEqual(response.status,200);self.assertIn(b'function submitOws',response.read())
        self.assertEqual(self.request('/api/ows',method='GET')[0],200)
        self.assertEqual(self.request('/api/ows',headers={'X-Kira-Session':''},method='GET')[0],403)
        for path in ('/api/ows/create','/api/ows/connect','/api/ows/disconnect'):
            self.assertEqual(self.request(path,body=b'{}',headers={'Origin':'https://foreign.test'})[0],403)
            self.assertEqual(self.request(path,body=b'{}',headers={'X-Kira-Session':''})[0],403)
        registry=json.loads((self.root/'wallets.json').read_text());registry['demo']=True;atomic(self.root/'wallets.json',registry)
        self.assertEqual(self.request('/api/ows/create',body=b'{}')[0],400)



    def test_valid_submission_duplicate_and_private_state(self):
        code,first=self.request();self.assertEqual(code,202);_,duplicate=self.request();self.assertEqual(first['job_id'],duplicate['job_id'])
        self.assertEqual(self.request('/api/jobs',method='GET')[0],200)
        self.assertEqual(self.request('/api/jobs',headers={'X-Kira-Session':''},method='GET')[0],403)

    def test_h402_preference_uses_existing_local_operation_boundary(self):
        body=json.dumps({'schema_version':1,'operation':'settings.h402','input':{'enabled':True},'idempotency_key':'h402-http-fixture'}).encode()
        for headers in ({'X-Kira-Session':''},{'Origin':'https://foreign.test'}):
            self.assertEqual(self.request(body=body,headers=headers)[0],403)
        self.assertEqual(self.http.jobs.list(),[])
        code,receipt=self.request(body=body)
        self.assertEqual(code,202);self.assertEqual(receipt['input'],{'enabled':True})
        self.assertEqual(self.request(body=body)[1]['job_id'],receipt['job_id'])
        self.assertEqual(self.request(body=body.replace(b'true',b'"yes"'))[0],400)
        with urllib.request.urlopen(self.url+'/integrations.js') as response:
            self.assertEqual(response.status,200);self.assertIn(b'saveH402Preference',response.read())
        self.http.controls=False
        self.assertEqual(self.request(body=body)[0],501)

    def test_embedded_agent_endpoints_are_removed(self):
        for path in ('/api/agent','/api/agent/models','/api/chat','/api/chat/history','/agent.js','/chat-workspace.js'):
            self.assertEqual(self.request(path,method='GET')[0],404)
        for path in ('/api/chat/send','/api/chat/respond','/api/agent/test'):
            self.assertEqual(self.request(path,body=b'{}')[0],404)

    def test_lazy_records_work_in_read_only_mode_and_reject_foreign_origins(self):
        from kira_cli import sample
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[]});sample(self.root)
        self.http.controls=False
        paths=('/api/state','/api/status','/api/wallet?wallet=Demo%20wallet','/api/token?chain_id=8453&address=0x'+'0'*39+'2','/api/network?chain_id=8453','/api/holdings?limit=1')
        for path in paths:
            self.assertEqual(self.request(path,method='GET')[0],200)
            self.assertEqual(self.request(path,method='GET',headers={'Origin':'https://foreign.test'})[0],403)
        self.assertEqual(self.request('/api/state',method='GET')[1]['wallets'][0]['assets'],[])
        self.assertEqual(len(self.request('/api/wallet?wallet=Demo%20wallet',method='GET')[1]['assets']),1)
        for path in ('/api/holdings?limit=101','/api/wallet?wallet=Demo%20wallet&offset=-1','/api/token?chain_id=true&address=native'):
            self.assertEqual(self.request(path,method='GET')[0],400)

    def test_selection_uses_protected_local_transport(self):
        body=json.dumps({'view':'wallet','wallet':ADDRESS,'token':None,'chain_id':None}).encode()
        self.assertEqual(self.request('/api/ui-context',body=body,headers={'X-Kira-Session':''})[0],403)
        self.assertEqual(self.request('/api/ui-context',body=body)[0],200)
        self.assertEqual(self.http.application.call('ui_context')['wallet'],ADDRESS)
        self.assertEqual(self.request('/api/ui-context',body=b'{"unexpected":true}')[0],400)

    def test_history_is_bounded_and_filters_before_pagination(self):
        for index in range(4):
            job=self.http.jobs.submit({'schema_version':1,'operation':'wallet.setTags','input':{'wallet':ADDRESS,'tags':['Name '+str(index)]},'idempotency_key':'history-page-'+str(index)})
            if index==2:job['state']='failed';self.http.jobs.save(job)
        code,result=self.request('/api/job-history?limit=2',method='GET')
        self.assertEqual(code,200);self.assertEqual(len(result['jobs']),2);self.assertEqual(result['next_offset'],2)
        code,result=self.request('/api/job-history?state=attention&limit=1',method='GET')
        self.assertEqual(code,200);self.assertEqual(result['total'],1);self.assertIsNone(result['next_offset'])
        self.assertEqual(self.request('/api/job-history',method='GET',headers={'X-Kira-Session':''})[0],403)

    def test_deep_scan_requires_protected_transport_and_an_explicit_request(self):
        parent=self.http.jobs.submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':ADDRESS},'idempotency_key':'basic-http-scan'})
        parent.update(state='partial',result={'snapshot_id':parent['checkpoint'],'status':'completed_with_coverage_gaps'});self.http.jobs.save(parent)
        body=json.dumps({'schema_version':1,'operation':'job.deepen','input':{'job_id':parent['job_id']},'idempotency_key':'deep-http-scan'}).encode()
        for headers in ({'X-Kira-Session':''},{'Origin':'https://foreign.test'},{'Host':'foreign.test:'+str(self.http.server_port)}):
            self.assertEqual(self.request(body=body,headers=headers)[0],403)
        self.assertEqual(len(self.http.jobs.list()),1)
        code,child=self.request(body=body);self.assertEqual(code,202)
        self.assertEqual(self.request(body=body)[1]['job_id'],child['job_id'])
        self.assertEqual(child['analysis_phase'],'enrichment')
        self.http.controls=False
        self.assertEqual(self.request(body=body)[0],501)

    def test_session_origin_rebinding_and_cross_site_rejected(self):
        for headers in [{'X-Kira-Session':''},{'X-Kira-Session':'wrong-session'},{'Origin':'https://foreign.test'},
                        {'Host':'foreign.test:'+str(self.http.server_port)},{'Sec-Fetch-Site':'cross-site'},{'Origin':''}]:
            self.assertEqual(self.request(headers=headers)[0],403)
        self.assertEqual(len(self.http.jobs.list()),0)

    def test_external_link_can_open_shell_without_access_to_data(self):
        navigation={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Dest':'document','Sec-Fetch-Mode':'navigate'}
        for path in ('/?setup=1','/index.html'):
            with urllib.request.urlopen(urllib.request.Request(self.url+path,headers=navigation)) as response:
                self.assertEqual(response.status,200)
                self.assertIn(b'Kira Wallet',response.read())
        for path in ('/api/session','/api/state','/api/agent','/api/ows','/app.js'):
            self.assertEqual(self.request(path,method='GET',headers=navigation)[0],403)
        self.assertEqual(self.request(headers=navigation)[0],403)
        for headers in ({**navigation,'Origin':'https://foreign.test'},
                        {**navigation,'Host':'foreign.test:'+str(self.http.server_port)},
                        {**navigation,'Sec-Fetch-Dest':'iframe'},
                        {**navigation,'Sec-Fetch-Mode':'cors'}):
            self.assertEqual(self.request('/',method='GET',headers=headers)[0],403)
    def test_setup_readiness_requires_controls_session_and_local_origin(self):
        expected={'rpc_mode':'public','discovery_provider':'none','discovery_configured':False,'discovery_key_available':False}
        with patch('onboarding.readiness',return_value=expected):
            self.assertEqual(self.request('/api/onboarding',method='GET'),(200,expected))
            for headers in [{'X-Kira-Session':''},{'Origin':'https://foreign.test'},{'Sec-Fetch-Site':'cross-site'}]:
                self.assertEqual(self.request('/api/onboarding',headers=headers,method='GET')[0],403)
            self.http.controls=False
            self.assertEqual(self.request('/api/onboarding',method='GET')[0],403)
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
        body=json.dumps({'schema_version':1,'operation':'wallet.add','input':{'address':'0x'+'2'*40,'tag':'Synthetic new wallet'},'idempotency_key':'demo-add'}).encode()
        self.assertEqual(self.request(body=body)[0],400);self.assertEqual(len(self.http.jobs.list()),0)
        self.http.jobs.launch.assert_not_called()
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
    def test_watching_registration_keeps_origin_session_and_idempotency_boundary(self):
        before=(self.root/'wallets.json').read_bytes()
        body=json.dumps({'schema_version':1,'operation':'wallet.add','input':{'address':'0x'+'2'*40,'tag':'  Synthetic exact name  '},'idempotency_key':'watching-add'}).encode()
        for headers in [{'X-Kira-Session':'expired'},{'Origin':'https://foreign.test'}]:
            self.assertEqual(self.request(headers=headers,body=body)[0],403)
        self.assertEqual(self.http.jobs.list(),[])
        code,first=self.request(body=body);self.assertEqual(code,202)
        _,retry=self.request(body=body);self.assertEqual(first['job_id'],retry['job_id'])
        self.assertEqual(len(self.http.jobs.list()),1)
        self.assertEqual(first['input']['tag'],'  Synthetic exact name  ')
        registry=json.loads((self.root/'wallets.json').read_text())
        self.assertEqual(len(registry['wallets']),2)
        self.assertEqual(registry['wallets'][-1]['tags'],['  Synthetic exact name  '])
        self.assertNotIn('latest_snapshot',registry['wallets'][-1])

if __name__=='__main__':unittest.main()
