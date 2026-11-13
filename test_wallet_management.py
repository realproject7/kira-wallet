"""Registration removal must be recoverable, atomic and free of provider work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from kira_cli import initialize
from kira_jobs import atomic, JobError
from kira_service import Application
from kira_wallets import management, removed_page
from kira_folders import catalog
from viewer.test_viewer import fixture_snapshot

A='0x'+'1'*40;B='0x'+'2'*40;C='0x'+'3'*40


class WalletManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start();initialize(self.root)
        wallets=[]
        for i,address in enumerate((A,B,C)):
            folder=f'snapshots/synthetic/{i}';snapshot=fixture_snapshot();snapshot['wallet_address']=address;atomic(self.root/folder/'results.json',snapshot)
            wallets.append({'address':address,'address_key':address,'tags':[['Savings','Long term'],['Treasury'],['Research']][i],
                            'research_generation':None,'latest_snapshot':{'directory':folder,'result':folder+'/results.json'}})
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':wallets,'research_runs':[],'wallet_admissions':{}})
        self.app=Application(self.root);self.n=0
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('Registration control contacted a provider'));self.network.start()
        self.launch=patch.object(self.app.jobs,'launch',side_effect=AssertionError('Registration control launched a worker'));self.launch.start()

    def tearDown(self):self.launch.stop();self.network.stop();self.env.stop();self.temp.cleanup()
    def registry(self):return json.loads((self.root/'wallets.json').read_text())
    def act(self,op,wallets,*,key=None,revision=None):
        self.n+=1
        return self.app.submit({'schema_version':1,'operation':op,'input':{'wallets':wallets,'expected_revision':revision or management(self.registry())['revision']},'idempotency_key':key or 'wallet-control-'+str(self.n)})

    def test_remove_and_restore_preserve_names_snapshots_folders_and_keys(self):
        result=self.app.submit({'schema_version':1,'operation':'folder.create','input':{'name':'Savings group'},'idempotency_key':'wallet-folder-create'})
        self.app.submit({'schema_version':1,'operation':'folder.assign','input':{'folder_id':result['folder_id'],'wallets':[A,C]},'idempotency_key':'wallet-folder-assign'})
        before=deepcopy(self.registry()['wallets']);protected={p:p.read_bytes() for p in self.root.rglob('results.json')};folders=(self.root/'wallet-folders.json').read_bytes()
        atomic(self.root/'.ows/sentinel.json',{'synthetic':'untouched'});keys=(self.root/'.ows/sentinel.json').read_bytes()
        removed=self.act('wallet.remove',[A,C]);self.assertEqual(removed['wallet_count'],2)
        self.assertEqual([w['address_key'] for w in self.registry()['wallets']],[B]);self.assertEqual(catalog(self.root)['folders'][0]['wallet_count'],0)
        self.assertEqual(len(self.app.views.refresh()['wallets']),1)
        page=removed_page(self.root,query='long TERM');self.assertEqual([w['key'] for w in page['wallets']],[A])
        self.act('wallet.restore',[C]);self.act('wallet.restore',[A])
        self.assertEqual(self.registry()['wallets'],before);self.assertEqual(catalog(self.root)['folders'][0]['wallet_count'],2)
        self.assertEqual((self.root/'wallet-folders.json').read_bytes(),folders);self.assertEqual((self.root/'.ows/sentinel.json').read_bytes(),keys)
        for p,value in protected.items():self.assertEqual(p.read_bytes(),value)
        self.assertEqual(self.app.jobs.list(),[])

    def test_stale_and_invalid_selections_never_remove_a_subset(self):
        revision=management(self.registry())['revision'];self.act('wallet.remove',[A])
        before=(self.root/'wallets.json').read_bytes()
        for wallets,rev in (([B,C],revision),([B,A],None),([B,B],None),([],None),(['../outside'],None)):
            with self.assertRaises(JobError):self.act('wallet.remove',wallets,revision=rev)
            self.assertEqual((self.root/'wallets.json').read_bytes(),before)

    def test_restore_cannot_duplicate_an_existing_registration(self):
        entry=deepcopy(self.registry()['wallets'][0]);self.act('wallet.remove',[A])
        registry=self.registry();registry['wallets'].append(entry);atomic(self.root/'wallets.json',registry)
        before=(self.root/'wallets.json').read_bytes()
        with self.assertRaisesRegex(JobError,'already registered'):self.act('wallet.restore',[A])
        self.assertEqual((self.root/'wallets.json').read_bytes(),before)

    def test_busy_selected_wallet_blocks_whole_removal_but_other_work_does_not(self):
        with patch.object(self.app.jobs,'require_connection'):
            job=self.app.jobs.submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':A},'idempotency_key':'active-wallet-refresh'})
        before=(self.root/'wallets.json').read_bytes()
        with self.assertRaisesRegex(JobError,'Pause their scans'):self.act('wallet.remove',[A,B])
        self.assertEqual((self.root/'wallets.json').read_bytes(),before)
        self.act('wallet.remove',[B]);self.assertEqual(self.app.jobs.get(job['job_id'])['state'],'queued')

    def test_old_add_receipt_and_legacy_registration_cannot_resurrect_removed_wallet(self):
        request={'schema_version':1,'operation':'wallet.add','input':{'address':A,'tag':'Savings'},'idempotency_key':'old-wallet-add-key'}
        with patch.object(self.app.jobs,'require_connection'):
            job=self.app.jobs.submit(request)
        self.app.jobs.submit({'schema_version':1,'operation':'job.cancel','input':{'job_id':job['job_id']},'idempotency_key':'cancel-old-wallet-add'})
        self.act('wallet.remove',[A]);before=(self.root/'wallets.json').read_bytes()
        with self.assertRaises(JobError):self.app.jobs.submit(request)
        from wallet import register
        with self.assertRaisesRegex(ValueError,'Wallet removed'):register(self.registry(),A,'Old name')
        self.assertEqual((self.root/'wallets.json').read_bytes(),before)
        self.act('wallet.restore',[A]);self.assertEqual(self.app.jobs.submit(request)['job_id'],job['job_id'])

    def test_receipt_replay_after_restore_does_not_remove_again_and_keys_are_shared(self):
        revision=management(self.registry())['revision'];result=self.act('wallet.remove',[A],key='stable-wallet-action',revision=revision)
        self.act('wallet.restore',[A]);self.assertEqual(self.act('wallet.remove',[A],key='stable-wallet-action',revision=revision),result)
        self.assertEqual(len(self.registry()['wallets']),3)
        with self.assertRaises(JobError):self.app.submit({'schema_version':1,'operation':'folder.create','input':{'name':'Conflict'},'idempotency_key':'stable-wallet-action'})
        with self.assertRaises(JobError):self.app.jobs.submit({'schema_version':1,'operation':'settings.h402','input':{'enabled':False},'idempotency_key':'stable-wallet-action'})

    def test_state_commit_recovers_receipt_after_an_interrupted_response(self):
        import kira_wallets
        original=kira_wallets.atomic;revision=management(self.registry())['revision']
        def interrupted(path,value):
            if '.wallet-actions' in path.parts:raise OSError('Synthetic interrupted receipt')
            return original(path,value)
        with patch.object(kira_wallets,'atomic',interrupted),self.assertRaises(OSError):self.act('wallet.remove',[A],key='interrupted-wallet-action',revision=revision)
        self.assertNotIn(A,{w['address_key'] for w in self.registry()['wallets']})
        self.act('wallet.restore',[A]);self.act('wallet.remove',[A],key='interrupted-wallet-action',revision=revision)
        self.assertIn(A,{w['address_key'] for w in self.registry()['wallets']})

    def test_concurrent_removals_with_one_revision_have_one_commit(self):
        revision=management(self.registry())['revision']
        def remove(address):
            try:return self.act('wallet.remove',[address],key='concurrent-remove-'+address,revision=revision)['completed']
            except JobError as e:return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(remove,[A,B]))
        self.assertCountEqual(results,[True,'wallet_conflict']);self.assertEqual(len(self.registry()['wallets']),2)

    def test_thousand_wallet_actions_have_bounded_recovery_pages(self):
        registry=self.registry();registry['wallets']=[{'address':'0x'+format(i+1,'040x'),'address_key':'0x'+format(i+1,'040x'),'tags':['Saved '+str(i)]} for i in range(1000)];atomic(self.root/'wallets.json',registry)
        self.act('wallet.remove',[w['address_key'] for w in registry['wallets']]);page=removed_page(self.root,limit=50)
        self.assertEqual(len(page['wallets']),50);self.assertEqual(page['matched_count'],1000);self.assertEqual(page['next_offset'],50)
        with self.assertRaises(JobError):removed_page(self.root,limit=1000)
        self.act('wallet.restore',list(self.registry()['removed_wallets']));self.assertEqual(len(self.registry()['wallets']),1000)

    def test_tools_expose_revision_and_bound_removal_without_provider_setup(self):
        page=self.app.call('wallets_removed',{});self.assertEqual(page['wallets'],[])
        result=self.app.call('wallets_remove',{'wallets':[A],'expected_revision':page['revision'],'idempotency_key':'tool-remove-wallet'},allow_write=True)
        self.assertTrue(result['completed']);self.assertEqual(len(self.registry()['wallets']),2)

    def test_workspace_market_union_does_not_expand_folder_balances(self):
        group=self.app.submit({'schema_version':1,'operation':'folder.create','input':{'name':'One wallet'},'idempotency_key':'market-scope-folder'})['folder_id']
        self.app.submit({'schema_version':1,'operation':'folder.assign','input':{'folder_id':group,'wallets':[A]},'idempotency_key':'market-scope-members'})
        for i in (0,1):
            path=self.root/f'snapshots/synthetic/{i}/results.json';value=json.loads(path.read_text());token=value['tokens'][0]
            token['dex_pools']=[{'pool':'0x'+format(i+100,'040x'),'venue':'uniswap','version_labels':['v3'],
                'paired_tokens':[{'address':token['token_address'],'symbol':'TOKEN'},{'address':'0x4200000000000000000000000000000000000006','symbol':'WETH'}],
                'reported_liquidity':{'usd':10000},'source_url':f'https://example.com/pool/{i}','observed_at':f'2026-11-1{i+1}T00:00:00Z'}]
            atomic(path,value)
        token=self.app.views.token(8453,'0x'+format(3,'040x'),folder_id=group)
        self.assertEqual(token['wallet_count'],1);self.assertEqual(token['balance'],'1');self.assertEqual(len(token['market_pools']),2)
        self.assertEqual(token['market_scope'],'workspace')

    def test_removed_records_require_local_auth_and_actions_cannot_delete_files(self):
        from http.server import ThreadingHTTPServer
        import threading
        import urllib.request,urllib.error
        import viewer.server as server
        self.network.stop()
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);http.controls=True;http.session_token='synthetic-session';http.application=self.app
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(http.server_port)
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:urllib.request.urlopen(base+'/api/removed-wallets')
            self.assertEqual(denied.exception.code,403);denied.exception.close()
            args={'schema_version':1,'operation':'wallet.remove','input':{'wallets':[A,B],'expected_revision':management(self.registry())['revision']},'idempotency_key':'http-wallet-remove'}
            request=urllib.request.Request(base+'/api/operations',data=json.dumps(args).encode(),headers={'Content-Type':'application/json','Origin':base,'X-Kira-Session':'synthetic-session'})
            with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['wallet_count'],2)
            with urllib.request.urlopen(urllib.request.Request(base+'/api/removed-wallets',headers={'X-Kira-Session':'synthetic-session'})) as response:
                page=json.load(response);self.assertEqual(len(page['wallets']),2);self.assertNotIn('latest_snapshot',page['wallets'][0])
            self.assertEqual(len(list((self.root/'snapshots').rglob('results.json'))),3)
        finally:http.shutdown();http.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
