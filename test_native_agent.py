"""Native protocol, consent and scoped transport regressions, without model calls."""
import io
import json
import os
import signal
import subprocess
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
from kira_jobs import JobError,atomic
from kira_cli import sample
from kira_native import NativeSession,ToolBridge,artifacts,read_artifact,workspace_path,tool_descriptors
from kira_agent import AgentStore,config_input


def config(**extra):
    return {'provider':'codex','model':'','scope':'none','wallet':None,'wallet_tools':False,'retain_history':True,'trust_native_cli':True,'native_agent':True,**extra}

class NativeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.root.mkdir()
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]});sample(self.root)
    def tearDown(self):self.temp.cleanup()

    def test_native_mode_requires_explicit_boolean_and_supported_provider(self):
        self.assertTrue(config_input(config(),self.root)['native_agent'])
        for value in ('yes',1):
            with self.assertRaises(JobError):config_input(config(native_agent=value),self.root)
        with self.assertRaises(JobError):config_input(config(provider='claude'),self.root)
        old=config();old.pop('native_agent');self.assertNotIn('native_agent',config_input(old,self.root))

    def test_native_tools_reuse_existing_scoped_research(self):
        from kira_research_tools import ResearchTools
        bridge=ToolBridge()
        try:
            def call(token,origin=None):
                headers={'Authorization':'Bearer '+token}
                if origin:headers['Origin']=origin
                req=urllib.request.Request('http://127.0.0.1:'+str(bridge.server.server_port)+'/',data=b'{"name":"holdings_query","arguments":{"mode":"rank"}}',headers=headers)
                with urllib.request.urlopen(req) as response:return json.load(response)
            with self.assertRaises(urllib.error.HTTPError):call('wrong')
            with self.assertRaises(urllib.error.HTTPError):call(bridge.token,'http://evil.example')
            self.assertEqual(call(bridge.token)['error']['code'],'inactive_turn')
            bridge.set(ResearchTools(self.root,config(scope='portfolio',wallet_tools=True)),str(uuid.uuid4()))
            result=call(bridge.token)['result'];self.assertTrue(result['query_scope']['full_inventory_scanned'])
            bridge.set(ResearchTools(self.root,config()),str(uuid.uuid4()))
            self.assertEqual(call(bridge.token)['error']['code'],'wallet_access_off')
            bridge.set(None);self.assertEqual(call(bridge.token)['error']['code'],'inactive_turn')
        finally:bridge.close()

    def test_descriptors_expose_shared_tools_without_forced_plan(self):
        rows={r['name']:r for r in tool_descriptors()}
        self.assertNotIn('records_read',rows);self.assertIn('holdings_query',rows)
        self.assertFalse(rows['holdings_refresh']['annotations']['readOnlyHint'])
        self.assertEqual(rows['token_read']['inputSchema']['properties']['chain_id']['type'],'integer')

    def test_approval_responses_do_not_grant_session_or_unknown_permissions(self):
        cancel=threading.Event()
        for requested in ('accept','decline','acceptForSession','anything'):
            result=NativeSession.approval('item/commandExecution/requestApproval',{},lambda p,c:{'decision':requested},cancel)
            self.assertEqual(result,{'decision':requested if requested in ('accept','decline') else 'decline'})
        result=NativeSession.approval('item/permissions/requestApproval',{'permissions':{'network':{'enabled':True}}},lambda p,c:{'decision':'decline'},cancel)
        self.assertEqual(result,{'permissions':{},'scope':'turn'})
        with self.assertRaises(JobError):NativeSession.approval('unknown',{},lambda p,c:{'decision':'accept'},cancel)
        with self.assertRaises(JobError):NativeSession.approval('item/tool/requestUserInput',{'questions':[{'id':'secret','isSecret':True}]},lambda p,c:{},cancel)

    def test_user_answers_keep_question_ids(self):
        result=NativeSession.approval('item/tool/requestUserInput',{'questions':[{'id':'network'},{'id':'amount'}]},lambda p,c:{'answers':{'network':'Base','amount':'5'}},threading.Event())
        self.assertEqual(result,{'answers':{'network':{'answers':['Base']},'amount':{'answers':['5']}}})

    def test_download_rejects_escape_links_and_nonregular_files(self):
        conversation=str(uuid.uuid4());folder=workspace_path(self.root,conversation);folder.mkdir(parents=True)
        (folder/'report.csv').write_text('token,value\nDEMO,125\n')
        outside=Path(self.temp.name)/'secret';outside.write_text('SECRET')
        (folder/'linked').symlink_to(outside)
        (folder/'dirlink').symlink_to(outside.parent,target_is_directory=True)
        os.mkfifo(folder/'pipe')
        self.assertEqual([r['path'] for r in artifacts(self.root,conversation)],['report.csv'])
        self.assertIn(b'DEMO',read_artifact(self.root,conversation,'report.csv'))
        for name in ('../secret',str(outside),'linked','dirlink/secret','pipe'):
            with self.subTest(name=name),self.assertRaises(JobError):read_artifact(self.root,conversation,name)

    def test_download_rejects_replaced_workspace_and_parent(self):
        conversation=str(uuid.uuid4());folder=workspace_path(self.root,conversation)
        outside=Path(self.temp.name)/'outside';outside.mkdir();(outside/'secret').write_text('PRIVATE')
        folder.parent.mkdir(parents=True);folder.symlink_to(outside,target_is_directory=True)
        self.assertEqual(artifacts(self.root,conversation),[])
        with self.assertRaises(JobError):read_artifact(self.root,conversation,'secret')
        folder.unlink();folder.parent.rmdir();folder.parent.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(JobError):read_artifact(self.root,conversation,'secret')

    def test_notifications_cannot_extend_an_unacknowledged_request(self):
        session=NativeSession(self.root,str(uuid.uuid4()),config())
        try:
            with patch.object(session,'send'),patch.object(session,'next',return_value={'method':'progress'}):
                with self.assertRaises(JobError) as caught:session.rpc('thread/start',{},threading.Event(),timeout=.03)
            self.assertEqual(caught.exception.code,'native_timeout')
        finally:session.close()

    def test_cancel_during_a_blocked_protocol_write(self):
        session=NativeSession(self.root,str(uuid.uuid4()),config());cancel=threading.Event()
        session.child=subprocess.Popen([os.sys.executable,'-c','import time;time.sleep(30)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0,start_new_session=True)
        os.set_blocking(session.child.stdin.fileno(),False)
        timer=threading.Timer(.15,cancel.set);timer.start();started=time.monotonic()
        try:
            with self.assertRaises(JobError) as caught:session.send({'text':'x'*2_000_000},cancel)
            self.assertEqual(caught.exception.code,'cancelled')
            self.assertLess(time.monotonic()-started,2)
        finally:session.close();timer.cancel();timer.join()

    def test_cancel_reaps_descendant_after_protocol_leader_exits(self):
        executable=Path(self.temp.name)/'fake-exited-codex';pidfile=Path(self.temp.name)/'descendant'
        executable.write_text('#!'+os.sys.executable+'\n'+'''import sys,json,os,signal,time
for line in sys.stdin:
 e=json.loads(line);m=e.get('method')
 if m=='initialize':out={'id':e['id'],'result':{}}
 elif m=='thread/start':out={'id':e['id'],'result':{'thread':{'id':'00000000-0000-4000-8000-000000000001'}}}
 elif m=='turn/start':
  if os.fork()==0:
   signal.signal(signal.SIGTERM,signal.SIG_IGN)
   open('''+repr(str(pidfile))+''','w').write(str(os.getpid()))
   time.sleep(30);os._exit(0)
  os._exit(0)
 else:continue
 print(json.dumps(out),flush=True)
''');executable.chmod(0o700)
        session=NativeSession(self.root,str(uuid.uuid4()),config());cancel=threading.Event()
        def stop():
            for _ in range(100):
                if pidfile.exists():break
                time.sleep(.01)
            cancel.set()
        stopper=threading.Thread(target=stop);stopper.start();started=time.monotonic()
        try:
            with patch('kira_native.shutil.which',return_value=str(executable)):
                with self.assertRaises(JobError) as caught:session.run('Wait',cancel,None,str(uuid.uuid4()),lambda _:None,lambda *_:{},'')
            self.assertEqual(caught.exception.code,'cancelled')
            self.assertLess(time.monotonic()-started,4)
            self.assertFalse(session.reader.is_alive())
            pid=pidfile.read_text()
            for _ in range(50):
                state=subprocess.run(['ps','-p',pid,'-o','state='],capture_output=True,text=True).stdout.strip()
                if not state or state.startswith('Z'):break
                time.sleep(.02)
            self.assertTrue(not state or state.startswith('Z'),state)
        finally:
            cancel.set();session.close();stopper.join(timeout=2)
            if pidfile.exists():
                try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
                except ProcessLookupError:pass

    def test_app_server_protocol_approval_and_two_turn_session(self):
        executable=Path(self.temp.name)/'fake-codex'
        transcript=Path(self.temp.name)/'events.jsonl'
        executable.write_text('#!'+os.sys.executable+'\n'+'''import sys,json
thread="00000000-0000-4000-8000-000000000001"
turn=0
for line in sys.stdin:
 e=json.loads(line)
 with open('''+repr(str(transcript))+''','a') as f:f.write(json.dumps(e)+'\\n')
 m=e.get('method')
 if m=='initialize':out={'id':e['id'],'result':{}}
 elif m in ('thread/start','thread/resume'):out={'id':e['id'],'result':{'thread':{'id':thread}}}
 elif m=='turn/start':
  turn+=1
  print(json.dumps({'id':e['id'],'result':{'turn':{'id':str(turn)}}}),flush=True)
  out={'id':'approve-'+str(turn),'method':'item/commandExecution/requestApproval','params':{'threadId':thread,'turnId':str(turn),'command':'echo hello','availableDecisions':['accept','decline']}}
 elif str(e.get('id','')).startswith('approve-'):
  print(json.dumps({'method':'item/completed','params':{'turnId':str(turn),'item':{'id':'message','type':'agentMessage','phase':'final_answer','text':'Decision: '+e['result']['decision']}}}),flush=True)
  out={'method':'turn/completed','params':{'turn':{'id':str(turn),'status':'completed'}}}
 else:continue
 print(json.dumps(out),flush=True)
''')
        executable.chmod(0o700)
        session=NativeSession(self.root,str(uuid.uuid4()),config())
        with patch('kira_native.shutil.which',return_value=str(executable)):
            try:
                for decision in ('decline','accept'):
                    answer=session.run('Work',threading.Event(),None,str(uuid.uuid4()),lambda t:None,lambda p,c:{'decision':decision},'Kira wallet context')
                    self.assertEqual(answer,'Decision: '+decision)
            finally:session.close()
            resumed=NativeSession(self.root,session.workspace.name,config(),thread_id=session.thread_id)
            try:
                answer=resumed.run('Continue',threading.Event(),None,str(uuid.uuid4()),lambda _:None,lambda *_:{'decision':'decline'},'')
                self.assertEqual(answer,'Decision: decline')
            finally:resumed.close()
        events=[json.loads(line) for line in transcript.read_text().splitlines()]
        self.assertEqual(sum(e.get('method')=='thread/start' for e in events),1)
        self.assertEqual(sum(e.get('method')=='thread/resume' for e in events),1)
        start=next(e for e in events if e.get('method')=='thread/start')['params']
        self.assertEqual(start['sandbox'],'workspace-write');self.assertEqual(start['approvalPolicy'],'on-request')
        self.assertNotIn('baseInstructions',start)
        self.assertEqual([e['id'] for e in events if str(e.get('id','')).startswith('approve-')],['approve-1','approve-2','approve-1'])

    def test_stale_duplicate_and_cancelled_responses_are_rejected(self):
        store=AgentStore(self.root,detector=lambda:[]);key=str(uuid.uuid4());request=str(uuid.uuid4())
        store.turns[key]={'state':'running','cancel':threading.Event()}
        store.pending_inputs[key]={'public':{'id':request},'event':threading.Event()}
        value={'id':key,'request_id':request,'response':{'decision':'decline'}}
        with self.assertRaises(JobError):store.respond({**value,'request_id':str(uuid.uuid4())})
        self.assertTrue(store.respond(value)['accepted'])
        with self.assertRaises(JobError):store.respond(value)
        store.pending_inputs[key]['event'].clear();store.turns[key]['cancel'].set()
        with self.assertRaises(JobError):store.respond(value)

    def test_saved_session_preserves_native_thread_id(self):
        store=AgentStore(self.root,detector=lambda:[]);store.config=config();key=str(uuid.uuid4())
        store.native_threads[store.conversation]=key
        store.messages=[{'role':'user','text':'hello'},{'role':'assistant','text':'hi'}]
        store._remember()
        saved=store.history(store.conversation)
        self.assertEqual(saved['native_thread_id'],key)
        store.config={**store.config,'retain_history':False}
        self.assertIsNone(store._session()['native_thread_id'])

if __name__=='__main__':unittest.main()
