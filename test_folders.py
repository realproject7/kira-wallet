"""Folder metadata and saved-only aggregation. Synthetic wallets, no providers."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from kira_cli import initialize
from kira_jobs import atomic, JobError, digest
from kira_service import Application
from kira_folders import catalog, load
from viewer.test_viewer import fixture_snapshot

A='0x'+'1'*40
B='0x'+'2'*40
C='0x'+'3'*40


class FoldersTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
        initialize(self.root);wallets=[]
        for index,address in enumerate((A,B,C)):
            entry={'address':address,'address_key':address,'tags':[['Savings','Long term'],['Treasury'],['Awaiting research']][index]}
            if index<2:
                folder='snapshots/synthetic/'+str(index);snapshot=fixture_snapshot();snapshot['wallet_address']=address
                snapshot['tokens'][0]['wallet_balance']=str(index+1)
                atomic(self.root/folder/'results.json',snapshot)
                entry['latest_snapshot']={'directory':folder,'result':folder+'/results.json'}
            wallets.append(entry)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':wallets,'research_runs':[]})
        self.app=Application(self.root)
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('Folder operation contacted a provider'));self.network.start()
        self.launch=patch.object(self.app.jobs,'launch',side_effect=AssertionError('Folder operation launched research'));self.launch.start()
        self.counter=0

    def tearDown(self):self.launch.stop();self.network.stop();self.env.stop();self.temp.cleanup()

    def act(self,operation,value,key=None):
        self.counter+=1
        return self.app.submit({'schema_version':1,'operation':operation,'input':value,'idempotency_key':key or 'folder-fixture-'+str(self.counter)})

    def create(self,name='Savings group'):return self.act('folder.create',{'name':name})['folder_id']

    def test_metadata_is_immediate_and_never_changes_names_or_snapshots(self):
        protected={p:p.read_bytes() for p in (self.root/'wallets.json',self.root/'snapshots/synthetic/0/results.json',self.root/'snapshots/synthetic/1/results.json')}
        with (self.root/'.analysis.lock').open('a') as writer:
            fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            group=self.create();self.act('folder.assign',{'folder_id':group,'wallets':[A,B]})
        self.assertEqual(catalog(self.root)['folders'][0]['wallet_count'],2)
        for path,body in protected.items():self.assertEqual(path.read_bytes(),body)
        self.assertEqual(self.app.jobs.list(),[])

    def test_move_replace_and_delete_keep_wallets_and_return_them_to_unfiled(self):
        first=self.create();second=self.create('Research')
        self.act('folder.assign',{'folder_id':first,'wallets':[A,B]})
        self.act('folder.assign',{'folder_id':second,'wallets':[A]})
        revision=catalog(self.root)['revision']
        self.act('folder.setMembers',{'folder_id':first,'wallets':[A,C],'expected_revision':revision})
        saved=catalog(self.root);self.assertEqual(saved['assignments'],{A:first,C:first});self.assertEqual(saved['unfiled_count'],1)
        self.act('folder.delete',{'folder_id':first})
        self.assertEqual(catalog(self.root)['assignments'],{});self.assertEqual(len(json.loads((self.root/'wallets.json').read_text())['wallets']),3)
        self.assertTrue((self.root/'snapshots/synthetic/0/results.json').exists())

    def test_stale_edits_validation_and_concurrent_membership_are_atomic(self):
        first=self.create();revision=catalog(self.root)['revision']
        def assign(address):
            try:return self.act('folder.assign',{'folder_id':first,'wallets':[address],'expected_revision':revision})['completed']
            except JobError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(assign,[A,B]))
        self.assertEqual(results.count(True),1);self.assertEqual(results.count('folder_conflict'),1)
        before=(self.root/'wallet-folders.json').read_bytes()
        for args in ({'folder_id':first,'wallets':[A,A]}, {'folder_id':first,'wallets':['0x'+'f'*40]}, {'folder_id':'../outside','wallets':[A]}):
            with self.assertRaises(JobError):self.act('folder.assign',args)
        with self.assertRaises(JobError):self.act('folder.setMembers',{'folder_id':first,'wallets':[],'expected_revision':None})
        with self.assertRaises(JobError):self.create('savings GROUP')
        with self.assertRaises(JobError):self.create('  ')
        self.assertEqual((self.root/'wallet-folders.json').read_bytes(),before)

    def test_receipt_replay_does_not_restore_an_old_name_or_deleted_folder(self):
        result=self.act('folder.create',{'name':'Original folder'},'stable-folder-key');group=result['folder_id']
        self.act('folder.rename',{'folder_id':group,'name':'Renamed folder'})
        self.assertEqual(self.act('folder.create',{'name':'Original folder'},'stable-folder-key'),result)
        self.assertEqual(catalog(self.root)['folders'][0]['name'],'Renamed folder')
        self.act('folder.delete',{'folder_id':group})
        self.assertEqual(self.act('folder.create',{'name':'Original folder'},'stable-folder-key'),result)
        self.assertEqual(catalog(self.root)['folders'],[])
        with self.assertRaises(JobError):self.act('folder.create',{'name':'Other'},'stable-folder-key')

    def test_crash_after_state_commit_recovers_receipt_before_a_later_edit(self):
        original=atomic
        def fail_receipt(path,value):
            if '.folder-actions' in Path(path).parts:raise OSError('Synthetic receipt interruption')
            original(path,value)
        with patch('kira_folders.atomic',side_effect=fail_receipt):
            with self.assertRaises(OSError):self.act('folder.create',{'name':'Committed'},'crash-folder-key')
        group=catalog(self.root)['folders'][0]['id']
        for operation,value in [('wallet.setTags',{'wallet':A,'tags':['Should not change']}),('portfolio.refresh',{})]:
            with self.assertRaises(JobError) as caught:self.act(operation,value,'crash-folder-key')
            self.assertEqual(caught.exception.code,'idempotency_conflict')
        self.act('folder.rename',{'folder_id':group,'name':'Latest'})
        self.assertTrue((self.root/'.folder-actions'/(digest('crash-folder-key')+'.json')).exists())
        self.act('folder.create',{'name':'Committed'},'crash-folder-key')
        self.assertEqual(catalog(self.root)['folders'][0]['name'],'Latest')

    def test_folder_totals_tokens_and_coverage_use_only_selected_saved_wallets(self):
        group=self.create();self.act('folder.assign',{'folder_id':group,'wallets':[A]})
        all_state=self.app.views.refresh();overview=self.app.views.overview(group)
        self.assertEqual(overview['dashboard']['wallet_count'],1)
        self.assertEqual(overview['dashboard']['known_value_usd'],all_state['wallets'][0]['known_value_usd'])
        self.assertEqual(overview['wallets'][0]['assets'],[])
        identity='0x'+f'{3:040x}'
        self.assertEqual(self.app.views.token(8453,identity,folder_id=group)['balance'],'1')
        self.assertEqual(self.app.views.token(8453,identity,folder_id=group)['wallet_count'],1)
        self.assertEqual(self.app.views.token(8453,identity)['wallet_count'],2)
        self.assertEqual(len(self.app.views.network(8453,folder_id=group)['wallets']),1)
        unfiled=self.app.views.overview('unfiled');self.assertEqual(unfiled['dashboard']['wallet_count'],2)
        empty=self.create('Empty');empty_view=self.app.views.overview(empty)
        self.assertIsNone(empty_view['dashboard']['known_value_usd']);self.assertIsNone(empty_view['dashboard']['sell_out_summary']['value_usd'])
        self.assertEqual(empty_view['dashboard']['wallet_count'],0)
        with self.assertRaises(JobError):self.app.select({'view':'token','token':'8453:'+identity,'folder_id':empty})
        self.app.submit({'schema_version':1,'operation':'token.policy','input':{'chain_id':8453,'address':identity,'mode':'exclude'},'idempotency_key':'folder-policy-fixture'})
        hidden=self.app.views.holdings(folder_id=group,portfolio_status='excluded')['assets']
        self.assertEqual(len(hidden),1);self.assertFalse(hidden[0]['included_in_totals'])

    def test_scopes_are_cached_bounded_and_metadata_does_not_reproject_snapshots(self):
        groups=[self.create('Group '+str(i)) for i in range(10)]
        self.act('folder.assign',{'folder_id':groups[0],'wallets':[A,B]})
        self.app.views.refresh()
        with patch('kira_state.project_details',wraps=__import__('kira_state').project_details) as projected:
            for _ in range(20):
                self.app.views.overview(groups[0]);self.app.views.holdings(folder_id=groups[0])
            self.assertEqual(projected.call_count,1)
        for group in groups:self.app.views.overview(group)
        self.assertEqual(len(self.app.views.scope_cache),8)
        self.act('folder.rename',{'folder_id':groups[0],'name':'New label'})
        with patch('model.project_wallet',side_effect=AssertionError('Metadata reparsed a snapshot')):
            self.assertEqual(next(f for f in self.app.views.overview(groups[0])['wallet_folders']['folders'] if f['id']==groups[0])['name'],'New label')
        self.assertEqual(len(self.app.views.scope_cache),1)

    def test_folder_batches_freeze_membership_and_tool_access_honors_write_mode(self):
        group=self.create();self.act('folder.assign',{'folder_id':group,'wallets':[A]})
        # Only queue admission is exercised. No worker or provider is started.
        with patch.object(self.app.jobs,'require_connection'):
            receipt=self.app.submit({'schema_version':1,'operation':'portfolio.refresh','input':{'folder_id':group},'idempotency_key':'scoped-batch-key'},launch=False)
        self.assertEqual([j['wallet'] for j in receipt['jobs']],[A])
        self.act('folder.assign',{'folder_id':group,'wallets':[B]})
        repeated=self.app.submit({'schema_version':1,'operation':'portfolio.refresh','input':{'folder_id':group},'idempotency_key':'scoped-batch-key'},launch=False)
        self.assertEqual(repeated['wallet_count'],1)
        self.assertEqual(self.app.call('folder_overview',{'folder_id':group})['dashboard']['wallet_count'],2)
        with self.assertRaises(JobError):self.app.call('folder_create',{'name':'Blocked','idempotency_key':'read-only-folder'})
        created=self.app.call('folder_create',{'name':'Through tools','idempotency_key':'write-folder-tool'},allow_write=True)
        self.assertTrue(created['completed']);self.assertEqual(len(self.app.call('folders_list')['folders']),2)

    def test_hundred_wallet_folder_keeps_reads_bounded_and_reuses_projection(self):
        wallets=[];template=fixture_snapshot()
        for index in range(100):
            address=f'0x{index+1000:040x}';folder=f'snapshots/scale/{index}';snapshot=deepcopy(template);snapshot['wallet_address']=address
            snapshot['tokens']=[{**snapshot['tokens'][0],'token_address':f'0x{token+10000:040x}','mintclub':None} for token in range(150)]
            atomic(self.root/folder/'results.json',snapshot)
            wallets.append({'address':address,'address_key':address,'tags':['Wallet '+str(index)],'latest_snapshot':{'directory':folder,'result':folder+'/results.json'}})
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':wallets,'research_runs':[]})
        group=self.create();self.act('folder.assign',{'folder_id':group,'wallets':[w['address_key'] for w in wallets[:50]]})
        overview=self.app.views.overview(group)
        self.assertEqual(sum(w['asset_count'] for w in overview['wallets']),7550)
        self.assertLess(len(json.dumps(overview)),500000)
        first=self.app.views.scope_builds
        with patch('kira_state.load_state',side_effect=AssertionError('Saved folder was recomputed')):
            for _ in range(10):self.assertEqual(len(self.app.views.holdings(limit=20,folder_id=group)['assets']),20)
        self.assertEqual(self.app.views.scope_builds,first)


if __name__=='__main__':unittest.main()
