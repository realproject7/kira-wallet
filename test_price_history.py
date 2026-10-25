"""Immutable price observations reuse the scoped, paged history contract."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kira_cli import sample
from kira_jobs import atomic, JobError
from kira_service import Application


class PriceHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'wallets':[],'research_runs':[]});sample(self.root)
        self.app=Application(self.root)
        self.entry=json.loads((self.root/'wallets.json').read_text())['wallets'][0]
        self.source=self.entry['latest_snapshot']['directory']
        self.snapshot=json.loads((self.root/self.source/'results.json').read_text())
        self.token=self.snapshot['tokens'][0]['token_address']

    def observation(self,name,usd):
        identity='snapshots/jobs/'+name
        atomic(self.root/identity/'prices.json',{'wallet_address':self.entry['address'],'snapshot_id':self.source,
            'observed_at':'2026-10-25T02:00:00Z','job_result_status':'completed','source_requests':[{'debug':'PRIVATE-MARKER'}],
            'tokens':[{'chain_id':8453,'address':self.token,'usd':usd,'quality':'estimated','basis':'Market index',
                       'observed_at':'2026-10-25T01:00:00Z','source':'https://www.alchemy.com'}]})
        return identity

    def test_history_lists_prices_only_when_requested_and_pages_them(self):
        a=self.observation('a',1);b=self.observation('b',2)
        call=self.app.call
        default=call('snapshots_list',{'wallet':self.entry['address']})
        self.assertEqual([r['snapshot_id'] for r in default['snapshots']],[self.source])
        prices=call('snapshots_list',{'wallet':self.entry['address'],'kind':'prices','limit':1})
        self.assertEqual(prices['matched_count'],2);self.assertEqual(prices['next_offset'],1)
        self.assertEqual(prices['snapshots'][0]['phase'],'prices')
        second=call('snapshots_list',{'wallet':self.entry['address'],'kind':'prices','limit':1,'offset':1})
        self.assertEqual([prices['snapshots'][0]['snapshot_id'],second['snapshots'][0]['snapshot_id']],[a,b])
        all_=call('snapshots_list',{'wallet':self.entry['address'],'kind':'all'})
        self.assertEqual({r['snapshot_id'] for r in all_['snapshots']},{self.source,a,b})
        with self.assertRaises(JobError):call('snapshots_list',{'wallet':self.entry['address'],'kind':'unknown'})

    def test_saved_price_read_survives_later_projection_changes_without_provider_calls(self):
        old=self.observation('a',1);new=self.observation('b',2)
        original=(self.root/self.source/'results.json').read_bytes()
        atomic(self.root/self.source/'market-prices.json',{'tokens':[{'chain_id':8453,'address':self.token,
            'usd':999,'basis':'Market index','quality':'estimated'}]})
        with patch('research.fetch',side_effect=AssertionError('History is read-only')):
            first=self.app.call('snapshot_read',{'snapshot_id':old})
            later=self.app.call('snapshot_read',{'snapshot_id':new})
            comparison=self.app.call('snapshots_compare',{'before':old,'after':new})
        self.assertEqual(first['wallets'][0]['assets'][0]['price']['usd'],1)
        self.assertEqual(later['wallets'][0]['assets'][0]['price']['usd'],2)
        self.assertEqual(first['price_observation']['holdings_snapshot'],self.source)
        row=next(p for p in comparison['positions'] if p['address']==self.token.lower())
        self.assertEqual(row['balance_delta'],'0');self.assertEqual(row['before_price']['usd'],1)
        self.assertEqual(row['after_price']['usd'],2);self.assertTrue(comparison['price_references_changed'])
        self.assertNotIn('PRIVATE-MARKER',json.dumps(first))
        self.assertNotIn('PRIVATE-MARKER',json.dumps(self.app.jobs.snapshot(old)))
        self.assertEqual((self.root/self.source/'results.json').read_bytes(),original)

    def test_unknown_price_and_wrong_wallet_or_source_fail_closed(self):
        identity=self.observation('a',None)
        result=self.app.call('snapshot_read',{'snapshot_id':identity})
        self.assertIsNone(result['wallets'][0]['assets'][0]['value_usd'])
        file=self.root/identity/'prices.json';value=json.loads(file.read_text())
        for changes in ({'wallet_address':'0x'+'9'*40},{'snapshot_id':'snapshots/../../private'},
                        {'snapshot_id':identity}):
            atomic(file,{**value,**changes})
            with self.assertRaises(JobError):self.app.call('snapshot_read',{'snapshot_id':identity})


if __name__=='__main__':unittest.main()
