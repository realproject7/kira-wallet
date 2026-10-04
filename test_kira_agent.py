"""Synthetic privacy, lifecycle and native-process boundary acceptance."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import signal
import unittest
import uuid
from unittest.mock import patch
from kira_agent import AgentStore, config_input, native_env, projection, run_native, supported
from kira_jobs import JobError, atomic
from kira_cli import sample

def settings(**changes):
    return {'provider':'codex','model':'','scope':'none','wallet':None,'retain_history':False,'trust_native_cli':True,**changes}

def ready():
    return [{'id':p,'installed':True,'supported':True,'logged_in':True} for p in ('codex','claude')]

class AgentTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]});sample(self.root)
        self.prompts=[]
        def run(config,prompt,cancel):self.prompts.append(prompt);return 'Kira connection ready.' if 'Generic connection test' in prompt else 'Recorded facts only.'
        self.store=AgentStore(self.root,runner=run,detector=ready)
    def tearDown(self):self.temp.cleanup()
    def done(self,store,turn):
        deadline=time.monotonic()+3
        while store.read(turn['id'])['state']=='running' and time.monotonic()<deadline:time.sleep(.01)
        return store.read(turn['id'])
    def configure(self,config=None):
        config=config or settings()
        turn=self.store.start({'config':config,'idempotency_key':str(uuid.uuid4())},test=True)
        self.assertEqual(self.done(self.store,turn)['state'],'succeeded');self.store.configure(config);return config
    def send(self,message='Hello',**changes):
        return self.store.start({'message':message,'conversation_id':self.store.conversation,'idempotency_key':str(uuid.uuid4()),**changes})
    def test_verified_configuration_and_subscription_readiness_required(self):
        with self.assertRaises(JobError):self.store.configure(settings())
        with self.assertRaises(JobError):config_input(settings(trust_native_cli=False),self.root)
        with self.assertRaises(JobError):config_input(settings(model='bad model; command'),self.root)
        self.store.detector=lambda:[{'id':'codex','installed':True,'supported':True,'logged_in':False}]
        with self.assertRaisesRegex(JobError,'subscription account'):self.store.start({'config':settings(),'idempotency_key':str(uuid.uuid4())},test=True)
    def test_projection_preserves_unknowns_and_excludes_private_fields(self):
        registry=json.loads((self.root/'wallets.json').read_text());address='0x'+'2'*40
        registry['wallets'].append({'address':address,'address_key':address,'tags':['Second synthetic']});atomic(self.root/'wallets.json',registry)
        one=projection(self.root,settings(scope='wallet',wallet=registry['wallets'][0]['address_key']))
        self.assertEqual(len(one['wallets']),1);self.assertNotIn(address,json.dumps(one))
        self.assertNotIn('report_url',json.dumps(one));self.assertNotIn('image_url',json.dumps(one));self.assertNotIn('source',json.dumps(one))
        all_=projection(self.root,settings(scope='portfolio'));self.assertIsNone(all_['wallets'][1]['known_value_usd'])
        self.assertEqual(projection(self.root,settings())['scope'],'none')
    def test_scope_provider_and_wallet_changes_do_not_replay_history(self):
        self.configure(settings(scope='portfolio'));self.done(self.store,self.send('Earlier portfolio discussion.'))
        self.configure(settings(provider='claude',scope='none'))
        self.assertEqual(self.store.messages,[]);self.done(self.store,self.send('Fresh question.'))
        self.assertNotIn('Earlier portfolio discussion.',self.prompts[-1]);self.assertNotIn('Demo wallet',self.prompts[-1])
    def test_retention_off_does_not_write_transcripts_and_on_is_private(self):
        self.configure();self.done(self.store,self.send())
        self.assertFalse((self.root/'conversations').exists())
        self.configure(settings(retain_history=True));self.done(self.store,self.send('Saved synthetic.'))
        files=list((self.root/'conversations').glob('*.json'));self.assertEqual(len(files),1);self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
        self.assertEqual(AgentStore(self.root,detector=ready).messages,[])
    def test_duplicate_send_and_conflict_are_safe(self):
        self.configure();key=str(uuid.uuid4());turn=self.send(idempotency_key=key);self.done(self.store,turn)
        again=self.send(idempotency_key=key);self.assertEqual(turn['id'],again['id']);self.assertEqual(len(self.store.messages),2)
        with self.assertRaises(JobError):self.send('Changed',idempotency_key=key)
    def test_busy_reset_and_cancel_ignore_late_success(self):
        self.configure();release=threading.Event()
        def held(*args):release.wait(2);return 'Late response.'
        self.store.runner=held;turn=self.send()
        with self.assertRaises(JobError):self.send('Duplicate while busy.')
        self.store.reset();release.set();self.done(self.store,turn);self.assertEqual(self.store.messages,[])
        release.clear();turn=self.send();self.store.cancel(turn['id']);release.set();self.done(self.store,turn);time.sleep(.03)
        self.assertEqual(self.store.messages,[])
    def test_old_conversation_and_removed_wallet_rejected(self):
        self.configure()
        with self.assertRaises(JobError):self.send(conversation_id=str(uuid.uuid4()))
        with self.assertRaises(JobError):projection(self.root,settings(scope='wallet',wallet='0x'+'2'*40))
    def test_errors_are_bounded_and_do_not_leak_provider_text(self):
        self.configure()
        def broken(*args):raise RuntimeError('private endpoint and credential')
        self.store.runner=broken;turn=self.done(self.store,self.send());self.assertEqual(turn['state'],'failed');self.assertNotIn('credential',json.dumps(turn))
    def test_native_environment_and_version_gate(self):
        with patch.dict(os.environ,{'ALCHEMY_API_KEY':'private','OPENAI_API_KEY':'private','ANTHROPIC_API_KEY':'private','KIRA_DATA_DIR':'private'}):
            self.assertFalse(any(k in native_env() for k in ('ALCHEMY_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','KIRA_DATA_DIR')))
        self.assertTrue(supported('codex','codex-cli 0.158.0'));self.assertFalse(supported('codex','0.159.0'))
        self.assertFalse(supported('claude','2.1.247'));self.assertTrue(supported('claude','2.1.284'))
    def test_native_process_output_timeout_and_cancellation(self):
        script=self.root/'synthetic-cli';script.write_text('#!/usr/bin/env python3\nimport sys,json,time\nif "--version" in sys.argv:print("codex-cli 0.158.0")\nelse:\n text=sys.stdin.read()\n if text=="timeout":time.sleep(5)\n elif text=="oversized":sys.stdout.write("x"*2100000)\n elif text=="malformed":print("bad json")\n else:\n  print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"Synthetic response."}}))\n  print(json.dumps({"type":"turn.completed"}))\n');script.chmod(0o700)
        with patch('kira_agent.shutil.which',return_value=str(script)):
            self.assertEqual(run_native(settings(),'Hello',threading.Event()),'Synthetic response.')
            for prompt,code in [('oversized','output_too_large'),('malformed','invalid_response'),('timeout','timeout')]:
                with self.assertRaises(JobError) as caught:run_native(settings(),prompt,threading.Event(),timeout=.2)
                self.assertEqual(caught.exception.code,code)
            cancelled=threading.Event();cancelled.set()
            with patch('kira_agent.subprocess.Popen') as model:
                with self.assertRaises(JobError) as caught:run_native(settings(),'timeout',cancelled)
                model.assert_not_called();self.assertEqual(caught.exception.code,'cancelled')
    def test_exited_leader_descendant_and_cleanup_error_preserve_timeout(self):
        script=self.root/'synthetic-descendant'
        script.write_text('#!/usr/bin/env python3\nimport os,sys,time\nif "--version" in sys.argv: print("codex-cli 0.158.0")\nelse:\n sys.stdin.read()\n if os.fork()==0: time.sleep(20);os._exit(0)\n os._exit(0)\n')
        script.chmod(0o700)
        real_killpg=os.killpg;injected=[]
        def cleanup(group,sig):
            try:real_killpg(group,sig)
            except OSError:pass
            if sig==signal.SIGKILL:
                injected.append(True);raise PermissionError('Synthetic exited group')
        with patch('kira_agent.shutil.which',return_value=str(script)),patch('kira_agent.os.killpg',side_effect=cleanup):
            with self.assertRaises(JobError) as caught:run_native(settings(),'Synthetic only',threading.Event(),timeout=.2)
            self.assertEqual(caught.exception.code,'timeout')
            self.assertEqual(injected,[True])
    def test_stale_cancel_does_not_invalidate_new_turn(self):
        self.configure();releases=[threading.Event(),threading.Event()];calls=[]
        def held(*args):
            index=len(calls);calls.append(index);releases[index].wait(2);return 'Recorded response.'
        self.store.runner=held;old=self.send();self.store.reset();new=self.send('New generation.')
        self.store.cancel(old['id']);releases[0].set();releases[1].set()
        self.assertEqual(self.done(self.store,new)['state'],'succeeded');self.assertEqual(len(self.store.messages),2)
        self.store.cancel(old['id']);self.assertEqual(self.store.read(new['id'])['state'],'succeeded')

if __name__=='__main__':unittest.main()
