"""A list of priced holdings still says how many unpriced ones it leaves out."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kira_cli import initialize, sample
from kira_jobs import JobError, atomic
from kira_service import Application
from kira_state import filter_assets, unpriced_hidden


def row(index, value, chain=1, status='portfolio'):
    address=f'0x{index:040x}'
    return {'id':f'{chain}:{address}','chain_id':chain,'environment':'mainnet','symbol':f'T{index}','name':f'Token {index}',
            'address':address,'value_usd':value,'portfolio_status':status}


class UnpricedFilterTests(unittest.TestCase):
    def setUp(self):
        self.rows=[row(1,12),row(2,3),row(3,None),row(4,None),row(5,None,chain=8453),row(6,None,status='excluded'),row(7,0)]

    def symbols(self,**filters):return [a['symbol'] for a in filter_assets(self.rows,**filters)]

    def test_priced_list_leaves_unpriced_holdings_out_and_counts_them(self):
        self.assertEqual(self.symbols(pricing='priced'),['T1','T2','T7'])
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced'),3)

    def test_a_zero_value_is_a_price(self):
        self.assertIn('T7',self.symbols(pricing='priced'))
        self.assertNotIn('T7',self.symbols(pricing='unpriced'))

    def test_count_follows_chain_status_and_search(self):
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',chain_id=1),2)
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',chain_id=8453),1)
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',portfolio_status='excluded'),1)
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',portfolio_status='all'),4)
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',query='T4'),1)
        self.assertEqual(unpriced_hidden(self.rows,pricing='priced',query='T1'),0)

    def test_a_minimum_value_counts_them_too(self):
        self.assertEqual(self.symbols(minimum_value_usd='5'),['T1'])
        self.assertEqual(unpriced_hidden(self.rows,minimum_value_usd='5'),3)
        self.assertEqual(unpriced_hidden(self.rows,minimum_value_usd='5',pricing='priced'),3)

    def test_showing_all_hides_nothing(self):
        self.assertEqual(self.symbols(),['T1','T2','T7','T3','T4','T5'])
        self.assertEqual(unpriced_hidden(self.rows),0)
        self.assertEqual(unpriced_hidden(self.rows,pricing='unpriced'),0)

    def test_invalid_filters_still_fail_before_any_count(self):
        with self.assertRaises(JobError):filter_assets(self.rows,pricing='cheap')
        with self.assertRaises(JobError):filter_assets(self.rows,minimum_value_usd='-1')


class UnpricedPageTests(unittest.TestCase):
    """The saved-data views carry the count with every page."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
        initialize(self.root);sample(self.root)
        file=self.root/'snapshots/demo/initial/results.json';snapshot=json.loads(file.read_text());template=snapshot['tokens'][0]
        # The sample prices one token. Four more have no price reference at all.
        snapshot['tokens']=[template]+[{**template,'token_address':f'0x{i+900:040x}','symbol':f'NOPRICE{i}','indexer_price_references':[]} for i in range(4)]
        atomic(file,snapshot);self.app=Application(self.root)

    def tearDown(self):self.env.stop();self.temp.cleanup()

    def test_wallet_page_counts_unpriced_holdings_left_out(self):
        everything=self.app.views.wallet('Demo wallet')
        self.assertEqual(everything['matched_count'],5);self.assertEqual(everything['unpriced_hidden_count'],0)
        priced=self.app.views.wallet('Demo wallet',pricing='priced')
        self.assertEqual(priced['matched_count'],1);self.assertEqual(priced['unpriced_hidden_count'],4)
        self.assertEqual(priced['unpriced_count'],4,'The wallet summary keeps its own unpriced total.')
        self.assertTrue(all(a['value_usd'] is not None for a in priced['assets']))
        found=self.app.views.wallet('Demo wallet',pricing='priced',query='NOPRICE2')
        self.assertEqual(found['matched_count'],0);self.assertEqual(found['unpriced_hidden_count'],1)

    def test_holdings_page_counts_them_across_wallets(self):
        self.assertEqual(self.app.views.holdings()['unpriced_hidden_count'],0)
        priced=self.app.views.holdings(pricing='priced')
        self.assertEqual(priced['matched_count'],1);self.assertEqual(priced['unpriced_hidden_count'],4)
        self.assertEqual(self.app.views.holdings(minimum_value_usd='5')['unpriced_hidden_count'],4)


if __name__=='__main__':unittest.main()
