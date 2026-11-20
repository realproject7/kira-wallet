"""Synthetic deposit accounting through the agent and web projection entry points."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kira_cli import initialize, sample
from kira_jobs import JobError, atomic
from kira_service import Application

CHAIN=8453
STABLE='0x'+format(2,'040x')
WALLET='0x'+format(1,'040x')
PEER='0x'+format(3,'040x')
OTHER='0x'+format(4,'040x')

def tx(i):
    return '0x'+format(i,'064x')

def leg(order,kind,asset,quantity,usd,peer=None,block=1):
    row={'order':order,'kind':kind,'asset':asset,'quantity':str(quantity),'block':block,'at':'2026-01-01T16:00:00Z','tx_hash':tx(order)}
    if usd is not None:row.update(usd=str(usd),usd_source='market')
    if peer:row['peer']=peer
    return row

def mark(asset,symbol,quantity,price):
    row={'asset':asset,'symbol':symbol,'quantity':str(quantity)}
    if price is not None:row.update(price_usd=str(price),source='market')
    return row

def sequence():
    events=[leg(0,'deposit',STABLE,6000,6000,PEER),
            leg(1,'sell',STABLE,3000,3000),leg(2,'buy','native',1,3000),
            leg(3,'sell',STABLE,2000,2000),leg(4,'buy','native',1,2000),
            leg(5,'sell','native',1,2800),leg(6,'buy',STABLE,2800,2800),
            leg(7,'sell',STABLE,2100,2100),leg(8,'buy','native',1,2100)]
    for i in (2,4,6,8):events[i]['tx_hash']=events[i-1]['tx_hash']
    return {'wallet':WALLET,'chain_id':CHAIN,'expected_revision':0,'base_revision':0,
            'from_block':1,'to_block':1,'block_hash':tx(100),'basis':'first_deposit','coverage':'verified',
            'from_time':'2026-01-01T00:00:00Z','as_of':'2026-01-02T00:00:00Z',
            'events':events,'balances':[mark('native','ETH',2,2400),mark(STABLE,'DEMO',1700,1)],
            'unclassified':[],'idempotency_key':'synthetic-pnl-one'}

class PnlTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        env=patch.dict(os.environ,{'KIRA_DATA_DIR':temp.name,'KIRA_CONFIG':str(self.root/'.kira.local.json')})
        env.start()
        self.addCleanup(env.stop)
        initialize(self.root)
        sample(self.root)
        path=self.root/'snapshots/demo/initial/results.json'
        snapshot=json.loads(path.read_text())
        snapshot['coverage'][0]['native_balance']='2'
        atomic(path,snapshot)
        self.app=Application(self.root)

    def save(self,args):
        return self.app.call('pnl_publish',args,allow_write=True)

    def read(self):
        return self.app.call('pnl_read',{'wallet':WALLET})

    def test_average_cost_and_cash_flows_through_views(self):
        initial=self.app.views.data_revision()
        self.assertIsNone(self.read()['summary'])
        self.assertFalse((self.root/'pnl').exists())
        batch=sequence()
        receipt=self.save(batch)
        self.assertEqual(receipt,self.save(batch))
        self.assertNotEqual(initial,self.app.views.data_revision())
        result=self.read()
        self.assertEqual(result['summary']['pnl_usd'],'500')
        eth=next(a for a in result['assets'] if a['asset']=='native')
        self.assertEqual([eth[k] for k in ('average_cost','realized','unrealized')],['2300','300','200'])
        self.assertEqual(self.app.views.overview()['dashboard']['pnl'],result['summary'])
        self.assertEqual([result['summary'][k] for k in ('capital_in_usd','value_and_withdrawals_usd')], ['6000','6500'])
        self.assertEqual(self.app.views.token(CHAIN,STABLE)['pnl_assets'][0]['realized'],'0')
        self.assertEqual(self.app.views.token(CHAIN,STABLE)['pnl']['total'],'0')
        self.assertEqual(self.app.views.token(CHAIN,'native')['pnl']['total'],'500')
        for page in (self.app.views.holdings(), self.app.views.wallet(WALLET)):
            self.assertEqual(next(a for a in page['assets'] if a['is_native'])['pnl']['unrealized'],'200')
        archived=self.app.call('pnl_evidence',{'wallet':WALLET,'chain_id':CHAIN,'revision':1,'limit':1})
        self.assertEqual(archived['events_count'],9)
        self.assertEqual(archived['next_offset'],1)
        with self.assertRaises(JobError):self.save({**batch,'balances':[]})
        self.assertEqual(self.read()['chains'][0]['revision'],1)

    def test_token_totals_respect_holders_closed_trades_and_folder(self):
        registry=json.loads((self.root/'wallets.json').read_text())
        folder='snapshots/demo/second'
        snapshot=json.loads((self.root/registry['wallets'][0]['latest_snapshot']['result']).read_text())
        snapshot['wallet_address']=OTHER
        atomic(self.root/folder/'results.json',snapshot)
        second={'address':OTHER,'address_key':OTHER,'tags':['Second'],
                'latest_snapshot':{'directory':folder,'result':folder+'/results.json'}}
        registry['wallets'].append(second)
        atomic(self.root/'wallets.json',registry)
        self.save(sequence())
        token=lambda folder=None: self.app.views.token(CHAIN,'native',folder_id=folder)['pnl']
        self.assertEqual(token()['missing_holders'],1)
        self.assertIsNone(token()['unrealized'])
        group=self.app.submit({'schema_version':1,'operation':'folder.create','input':{'name':'Long term'},
                               'idempotency_key':'pnl-folder-create'})['folder_id']
        self.app.submit({'schema_version':1,'operation':'folder.assign','input':{'folder_id':group,'wallets':[WALLET]},
                         'idempotency_key':'pnl-folder-assign'})
        self.assertEqual(token(group)['total'],'500')
        batch=sequence()
        batch.update(wallet=OTHER,events=[leg(0,'deposit','native',1,2500,PEER),leg(1,'sell','native',1,2000),
                                         {**leg(2,'buy',STABLE,2000,2000),'tx_hash':tx(1)}],
                     balances=[mark(STABLE,'DEMO',2000,1)],idempotency_key='pnl-closed-trade')
        snapshot['coverage'][0]['native_balance']='0'
        atomic(self.root/folder/'results.json',snapshot)
        self.save(batch)
        both=token()
        self.assertEqual([both[k] for k in ('realized','unrealized','total','reporting_wallets')],['-200','200','0',2])
        self.assertEqual(token(group)['total'],'500')
        self.assertEqual(next(a for a in self.app.views.holdings(folder_id=group)['assets'] if a['is_native'])['pnl']['total'],'500')

    def test_append_then_repair_and_unknown(self):
        batch=sequence()
        self.save(batch)
        later={**batch,'expected_revision':1,'base_revision':1,'from_block':2,'to_block':2,
               'from_time':batch['as_of'],'as_of':'2026-01-03T00:00:00Z','events':[],
               'idempotency_key':'synthetic-pnl-two','unclassified':[tx(43)]}
        self.save(later)
        self.assertIsNone(self.read()['summary']['pnl_usd'])
        with self.assertRaises(JobError):self.save({**later,'idempotency_key':'stale-revision'})
        self.save({**later,'unclassified':[],'expected_revision':2,'idempotency_key':'repair-revision'})
        self.assertEqual(self.read()['summary']['pnl_usd'],'500')
        for name,changes in [('balance',{'balances':[mark('native','ETH',3,2000)]}),
                             ('price',{'balances':[mark('native','ETH',2,None),mark(STABLE,'DEMO',1700,1)]}),
                             ('coverage',{'coverage':'partial'})]:
            revision=self.read()['chains'][0]['revision']
            self.save({**later,'expected_revision':revision,'unclassified':[],'idempotency_key':'missing-'+name,**changes})
            self.assertIsNone(self.read()['summary']['pnl_usd'])

    def test_internal_funding_and_folder_scope(self):
        registry=json.loads((self.root/'wallets.json').read_text())
        registry['wallets'].append({'address':OTHER,'address_key':OTHER,'tags':['Second']})
        atomic(self.root/'wallets.json',registry)
        batch=sequence()
        batch['events'].append(leg(9,'withdrawal',STABLE,100,100,OTHER))
        batch['balances'][1]['quantity']='1600'
        self.save(batch)
        self.assertIsNone(self.app.views.overview()['dashboard']['pnl']['pnl_usd'])
        receive=leg(9,'deposit',STABLE,100,100,WALLET)
        second={**batch,'wallet':OTHER,'events':[receive],'balances':[mark(STABLE,'DEMO',100,1)],'idempotency_key':'synthetic-other'}
        self.save(second)
        total=self.app.views.overview()['dashboard']['pnl']
        self.assertEqual((total['pnl_usd'],total['deposits_usd'],total['withdrawals_usd']),('500','6000','0'))
        self.assertEqual(self.read()['summary']['withdrawals_usd'],'100')
        self.save({**second,'expected_revision':1,'idempotency_key':'other-unmatched','events':[{**receive,'tx_hash':tx(80)}]})
        self.assertIsNone(self.app.views.overview()['dashboard']['pnl']['pnl_usd'])

    def test_tracking_start_and_fee(self):
        batch=sequence()
        batch.update(basis='tracking_start',events=[leg(0,'opening','native',2,4000),leg(1,'fee','native','0.01',20)],
                     balances=[mark('native','ETH','1.99',2000)])
        self.save(batch)
        self.assertEqual(float(self.read()['summary']['pnl_usd']),-20)
        self.assertFalse(self.read()['summary']['first_deposit'])
        for field,value in [('chain_id',11155111),('events',[leg(8,'sell','native',1,100)]),
                            ('as_of','not a date'),('from_block',-1)]:
            with self.assertRaises(JobError):self.save({**batch,'expected_revision':1,'idempotency_key':'invalid-'+field,field:value})

    def test_bridge_remains_pending_until_the_destination_is_analyzed(self):
        batch=sequence()
        bridge='8453:'+tx(22)+':0'
        batch['events'].append({**leg(9,'convert_out','native',1,None),'bridge_id':bridge})
        batch['balances'][0]['quantity']='1'
        self.save(batch)
        self.assertEqual(self.read()['summary']['pending_bridges'],1)
        other={**batch,'chain_id':1,'events':[{**leg(0,'convert_in','native',1,2300),'bridge_id':bridge,'usd_source':'carried_cost'}],
               'balances':[mark('native','ETH',1,2400)],'idempotency_key':'destination-bridge'}
        self.save(other)
        self.assertEqual(self.read()['summary']['pnl_usd'],'500')

    def test_reference_receipt_is_pinned_and_shared_across_wallets(self):
        import pnl_activity
        args={'wallet':WALLET,'chain_id':CHAIN,'kind':'receipt','tx_hash':tx(7),'block_hash':tx(22),'daily_budget_cu':120}
        with patch('kira_config.load_config',return_value={'discovery':{'provider':'alchemy','key_env':'TEST'}}), \
             patch('kira_config.secret_values',return_value={'TEST':'fixture'}), \
             patch('public_discovery.fetch_bounded',return_value={'result':{'transactionHash':tx(7),'blockHash':tx(22)}}) as fetch:
            self.assertEqual(pnl_activity.reference(self.root,WALLET,args)['cu'],20)
            self.assertEqual(pnl_activity.reference(self.root,OTHER,{**args,'wallet':OTHER})['cu'],0)
            self.assertEqual(fetch.call_count,1)
            with self.assertRaises(JobError):pnl_activity.reference(self.root,WALLET,{**args,'block_hash':tx(99)})

    def test_reads_preserve_latest_state_across_saves_and_cost_gaps(self):
        batch=sequence()
        self.save(batch)
        old_http=self.app.views.wallet(WALLET)
        self.assertEqual(old_http['pnl_asset_count'],2)
        self.assertEqual(old_http['pnl']['pnl_usd'],'500')
        revised={**batch,'expected_revision':1,'idempotency_key':'unknown-entry-cost'}
        del revised['events'][2]['usd'],revised['events'][2]['usd_source']
        self.save(revised)
        new_http=self.app.views.wallet(WALLET)
        self.assertNotEqual(old_http['data_revision'],new_http['data_revision'])
        eth=next(a for a in new_http['pnl_assets'] if a['asset']=='native')
        self.assertIsNone(eth['average_cost'])
        self.assertIsNone(eth['realized'])
        self.assertEqual(new_http['pnl']['pnl_usd'],'500')
        self.assertEqual(new_http['pnl']['started_at'],'2026-01-01T16:00:00.000000+00:00')

    def test_fetch_cache_cost_and_limits(self):
        import pnl_activity
        args={'wallet':WALLET,'chain_id':CHAIN,'from_block':1,'to_block':2,'block_hash':tx(2),'direction':'incoming','daily_budget_cu':120}
        with self.assertRaises(JobError):self.app.call('pnl_fetch_transfers',args,allow_write=True)
        with patch('kira_config.load_config',return_value={'discovery':{'provider':'alchemy','key_env':'TEST'}}), \
             patch('kira_config.secret_values',return_value={'TEST':'fixture'}), \
             patch('public_discovery.fetch_bounded',return_value={'result':{'transfers':[]}}) as fetch:
            self.assertEqual(pnl_activity.fetch(self.root,WALLET,args)['cu'],120)
            self.assertEqual(pnl_activity.fetch(self.root,WALLET,args)['cu'],0)
            with self.assertRaises(JobError):pnl_activity.fetch(self.root,WALLET,{**args,'direction':'outgoing'})
            self.assertEqual(fetch.call_count,1)

if __name__=='__main__':unittest.main()
