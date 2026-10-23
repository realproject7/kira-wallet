"""Claude host transport and native-provider routing regressions, without a model."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from kira_claude import ClaudeSession
from kira_agent import AgentStore
from kira_jobs import JobError,atomic
from test_native_agent import config

class ClaudeTransportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.root.mkdir()
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]})
    def tearDown(self):self.temp.cleanup()

    def test_sdk_host_roundtrip_approval_and_restart_resume(self):
        transcript=Path(self.temp.name)/'events.jsonl';executable=Path(self.temp.name)/'sdk-host'
        executable.write_text('#!'+os.sys.executable+'\n'+"""import json,sys,uuid
thread=str(uuid.uuid4());turn=None;request=None
def emit(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
 e=json.loads(line)
 with open("""+repr(str(transcript))+""",'a') as f:f.write(json.dumps(e)+'\\n')
 if e['type']=='initialize':
  thread=e.get('thread_id') or thread;emit({'type':'ready'})
 elif e['type']=='prompt':
  turn=e['turn_id'];request=str(uuid.uuid4())
  emit({'type':'session','turn_id':turn,'thread_id':thread})
  emit({'type':'completed','turn_id':str(uuid.uuid4()),'success':True,'answer':'FOREIGN'})
  emit({'type':'request','turn_id':turn,'request_id':request,'request':{'kind':'approval','details':{'tool':'Write','input':{'file_path':'report.csv','content':'DEMO,125'}}}})
 elif e['type']=='respond':
  assert e['turn_id']==turn and e['request_id']==request
  emit({'type':'completed','turn_id':turn,'success':True,'answer':'Decision: '+e['response']['decision']})
""");executable.chmod(0o700)
        native=ClaudeSession(self.root,str(uuid.uuid4()),config(provider='claude'))
        with patch('kira_claude.shutil.which',return_value=str(executable)):
            try:
                for decision in ('decline','accept'):
                    answer=native.run('Work',threading.Event(),None,str(uuid.uuid4()),lambda _:None,lambda request,c:{'decision':decision},'Kira')
                    self.assertEqual(answer,'Decision: '+decision)
                thread=native.thread_id
            finally:native.close()
            resumed=ClaudeSession(self.root,native.workspace.name,config(provider='claude'),thread_id=thread)
            try:
                self.assertEqual(resumed.run('Continue',threading.Event(),None,str(uuid.uuid4()),lambda _:None,lambda *_:{'decision':'decline'},''),'Decision: decline')
                self.assertEqual(resumed.thread_id,thread)
            finally:resumed.close()
        events=[json.loads(line) for line in transcript.read_text().splitlines()]
        init=[e for e in events if e['type']=='initialize']
        self.assertEqual(len(init),2);self.assertIsNone(init[0]['thread_id']);self.assertEqual(init[1]['thread_id'],thread)
        self.assertEqual(len([e for e in events if e['type']=='respond']),3)
        self.assertFalse(native.reader.is_alive());self.assertFalse(resumed.reader.is_alive())

    def test_aborted_sdk_input_wakes_pending_host_and_old_cancellation_is_cleared(self):
        native=ClaudeSession(self.root,str(uuid.uuid4()),config(provider='claude'))
        try:
            cancel=threading.Event();native.active_cancel=cancel;native.pending_request='pending'
            native.receive_event({'type':'input_cancelled','request_id':'other'})
            self.assertFalse(cancel.is_set())
            native.receive_event({'type':'input_cancelled','request_id':'pending'})
            self.assertTrue(cancel.is_set())
            with patch.object(native,'start',side_effect=JobError('synthetic','Stop')):
                with self.assertRaises(JobError):native.run('Work',threading.Event(),None,str(uuid.uuid4()),lambda _:None,lambda *_:{},'')
            self.assertEqual(native.cancelled_requests,set())
            self.assertIsNone(native.active_cancel)
        finally:native.close()

    def test_store_selects_claude_adapter_for_native_connection(self):
        store=AgentStore(self.root,detector=lambda:[]);cfg=config(provider='claude')
        store.config=cfg;key=str(uuid.uuid4());store.active=key
        store.turns[key]={'id':key,'test':True,'state':'running','cancel':threading.Event()}
        with patch('kira_claude.ClaudeSession') as native,patch('kira_native.NativeSession') as codex:
            native.return_value.closed=False;native.return_value.workspace=Path(self.temp.name)/'output'
            native.return_value.run.return_value='Kira connection ready.'
            store._run_native_session(key,cfg,'Hello',store.epoch)
            native.assert_called_once();codex.assert_not_called()
            native.return_value.close.assert_called_once()
            self.assertEqual(store.turns[key]['state'],'succeeded')

if __name__=='__main__':unittest.main()
