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

    def test_market_detail_cannot_displace_holdings_or_disable_large_wallet_chat(self):
        from copy import deepcopy
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
        import model
        state,stamp,stale=model.load_state(self.root)
        wallet=state['wallets'][0];template=wallet['assets'][0]
        wallet['assets']=[]
        for index in range(100):
            asset=deepcopy(template);asset['id']=f'8453:0x{index:040x}'
            asset['market_pools']=[{'venue':'Uniswap V3','pool':'0x'+'3'*40,
                'url':'https://example.com/pool/'+str(pool),'liquidity_usd':100,
                'price_usd':1,'observed_at':'2026-10-05T00:00:00Z',
                'pair':[{'symbol':'USDC','address':'0x'+'4'*40}]} for pool in range(12)]
            wallet['assets'].append(asset)
        with patch('model.load_state',return_value=(state,stamp,stale)):
            facts=projection(self.root,settings(scope='portfolio'))
            self.assertEqual(len(facts['wallets'][0]['assets']),12)
            self.assertEqual(facts['wallets'][0]['asset_count'],100)
            self.assertEqual(facts['wallets'][0]['next_offset'],12)
            self.assertLessEqual(len(json.dumps(facts,ensure_ascii=False).encode()),240_000)
            self.assertGreater(sum(a['pools_omitted'] for a in facts['wallets'][0]['assets']),0)
            detail=projection(self.root,settings(scope='portfolio'),token_id=wallet['assets'][-1]['id'])
            self.assertEqual(len(detail['wallets'][0]['assets']),1)
            self.assertEqual(len(detail['wallets'][0]['assets'][0]['pools']),12)

    def test_exit_quotes_only_reach_explicitly_approved_context(self):
        registry=json.loads((self.root/'wallets.json').read_text())
        entry=registry['wallets'][0];path=self.root/entry['latest_snapshot']['result']
        snapshot=json.loads(path.read_text());token=snapshot['tokens'][0]
        token['balance_block_number']=123
        token['mintclub']={'reserve_token':'0x'+'9'*40,'reserve_symbol':'SAMPLE','reserve_balance':'100',
            'funded':True,'price_for_next_mint_in_reserve_token':'1','source_url':'https://example.com/fixture',
            'observed_at':'2026-10-04T00:00:00Z','block_number':123,'wallet_full_burn':{'net_refund':'12','gas_included':False}}
        atomic(path,snapshot)
        self.assertNotIn('12',json.dumps(projection(self.root,settings())))
        scoped=projection(self.root,settings(scope='wallet',wallet=entry['address_key']))
        quote=scoped['wallets'][0]['assets'][0]['exit_quote']
        self.assertEqual(quote['output_amount'],'12')
        self.assertFalse(quote['gas_included'])
        self.assertNotIn('source_url',json.dumps(scoped))

    def test_large_inventory_pages_without_changing_scope_or_unknown_values(self):
        from copy import deepcopy
        import model
        state,stamp,stale=model.load_state(self.root)
        wallet=state['wallets'][0];template=wallet['assets'][0]
        wallet['assets']=[]
        for index in range(800):
            asset=deepcopy(template);asset['id']=f'8453:0x{index:040x}'
            asset['address']='0x'+f'{index:040x}';asset['symbol']='SAMPLE';asset['name']='Synthetic holding'
            asset['value_usd']=None;asset['price']=None;asset['balance']='1.2345'
            asset['links']=[{'label':'Uniswap','url':'https://example.com/pool/'+str(index)}]
            asset['exit_quote']={'output_amount':'0.1234','output_symbol':'ETH','gas_included':False,'observed_at':'2026-10-05T00:00:00Z'}
            wallet['assets'].append(asset)
        config=settings(scope='portfolio',wallet_tools=True)
        with patch('model.load_state',return_value=(state,stamp,stale)):
            facts=projection(self.root,config)
            self.assertEqual(facts['scope'],'portfolio')
            holdings=facts['wallets'][0]['assets']
            self.assertEqual([a['id'] for a in holdings],[a['id'] for a in wallet['assets'][:12]])
            self.assertEqual(facts['wallets'][0]['asset_count'],800)
            self.assertEqual(facts['wallets'][0]['assets_omitted'],788)
            self.assertEqual(holdings[-1]['balance'],'1.2345')
            self.assertIsNone(holdings[-1]['value_usd']);self.assertIsNone(holdings[-1]['price'])
            self.assertLessEqual(len(json.dumps(facts,ensure_ascii=False).encode()),40_000)
            detail=projection(self.root,config,token_id=holdings[-1]['id'])
            self.assertEqual(detail['wallets'][0]['assets'][0]['exit_quote']['output_amount'],'0.1234')
            self.store.config=config
            self.assertEqual(self.done(self.store,self.send('Which tokens do I hold?'))['state'],'succeeded')
            self.assertEqual(self.store.config,config)

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
    def test_memory_history_survives_new_chat_without_persistence(self):
        self.configure();self.done(self.store,self.send('First synthetic conversation.'))
        old=self.store.conversation;self.store.reset()
        rows=self.store.history();self.assertEqual(rows[0]['id'],old)
        self.assertFalse(rows[0]['saved']);self.assertFalse((self.root/'conversations').exists())
        self.store.open_history(old);self.assertEqual(len(self.store.messages),2)
        self.done(self.store,self.send('Continue this conversation.'))
        self.assertIn('First synthetic conversation.',self.prompts[-1])
        self.assertEqual(AgentStore(self.root,detector=ready).history(),[])

    def test_saved_history_legacy_validation_and_exact_permissions(self):
        self.configure(settings(retain_history=True));self.done(self.store,self.send('Saved synthetic.'))
        old=self.store.conversation;self.store.reset()
        restarted=AgentStore(self.root,detector=ready)
        self.assertEqual(len(restarted.history()),1);restarted.open_history(old)
        self.assertEqual(restarted.messages[0]['text'],'Saved synthetic.')
        self.configure(settings(provider='claude',retain_history=True))
        self.assertFalse(self.store.history(old)['can_continue'])
        with self.assertRaisesRegex(JobError,'different model'):self.store.open_history(old)
        self.assertEqual(self.store.messages,[])
        folder=self.root/'conversations';bad=str(uuid.uuid4())
        atomic(folder/(bad+'.json'),{'schema_version':1,'config':settings(), 'messages':[{'role':'system','text':'Untrusted'}]})
        (folder/(str(uuid.uuid4())+'.json')).symlink_to(folder/(old+'.json'))
        legacy=str(uuid.uuid4());atomic(folder/(legacy+'.json'),{'schema_version':1,'config':settings(retain_history=True),'messages':[{'role':'user','text':'Legacy saved conversation.'}]})
        self.assertEqual({r['id'] for r in restarted.history()},{old,legacy})
        with self.assertRaises(JobError):restarted.history('../../outside')

    def test_bad_config_deep_json_and_fifo_do_not_hide_valid_history(self):
        self.configure(settings(retain_history=True));self.done(self.store,self.send('Valid synthetic conversation.'))
        valid=self.store.conversation;self.store.reset();folder=self.root/'conversations'
        bad=str(uuid.uuid4());atomic(folder/(bad+'.json'),{'schema_version':1,'config':settings(provider=[]),'messages':[]})
        (folder/(str(uuid.uuid4())+'.json')).write_text('['*2000+'0'+']'*2000)
        os.mkfifo(folder/(str(uuid.uuid4())+'.json'))
        self.assertEqual({r['id'] for r in self.store.history()},{valid})
        self.store.open_history(valid);self.assertEqual(self.store.messages[0]['text'],'Valid synthetic conversation.')
        self.store.reset();self.assertEqual(self.store.messages,[])

    def test_history_cannot_switch_during_response_or_replay_different_scope(self):
        self.configure(settings(scope='portfolio'));self.done(self.store,self.send('Portfolio synthetic.'))
        old=self.store.conversation;self.store.reset()
        release=threading.Event();original=self.store.runner
        def held(*args):release.wait(2);return 'Held response.'
        self.store.runner=held
        turn=self.send('Wait for this response.')
        try:
            with self.assertRaisesRegex(JobError,'Finish or stop'):self.store.open_history(old)
        finally:release.set();self.done(self.store,turn);self.store.runner=original
        self.configure(settings(scope='none'))
        self.assertFalse(self.store.history(old)['can_continue'])
        with self.assertRaises(JobError):self.store.open_history(old)

    def test_upgrade_restores_memory_only_with_exact_permissions(self):
        self.configure();self.done(self.store,self.send('Keep this private conversation.'))
        receipt=self.store._session();restarted=AgentStore(self.root,detector=ready)
        restarted.restore_runtime(receipt)
        self.assertEqual(restarted.status()['messages'],self.store.messages)
        self.assertEqual(restarted.conversation,self.store.conversation)
        self.assertFalse((self.root/'conversations').exists())
        with self.assertRaises(ValueError):restarted.restore_runtime(receipt)
        other=AgentStore(self.root,detector=ready);other.config=settings(scope='portfolio')
        with self.assertRaisesRegex(ValueError,'permissions changed'):other.restore_runtime(receipt)
        self.assertEqual(other.messages,[])

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
    def test_native_codex_commentary_is_not_a_final_tool_request(self):
        script=self.root/'synthetic-phase-cli'
        events=[{'type':'item.completed','item':{'type':'agent_message','phase':'commentary','text':'Working {"kira_tool":"portfolio_read"}'}},
                {'type':'item.completed','item':{'type':'agent_message','phase':'final_answer','text':'{"kira_tool":"portfolio_read","arguments":{}}'}},
                {'type':'turn.completed'}]
        script.write_text('#!/usr/bin/env python3\nimport sys,json\nif "--version" in sys.argv:print("codex-cli 0.158.0")\nelse:\n sys.stdin.read()\n for row in '+repr(events)+':print(json.dumps(row))\n');script.chmod(0o700)
        with patch('kira_agent.shutil.which',return_value=str(script)):
            self.assertEqual(json.loads(run_native(settings(),'Hello',threading.Event()))['kira_tool'],'portfolio_read')

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
