"""Alchemy admission, private setup and immutable sell-analysis source boundaries."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

import kira_cli
from kira_config import default_config, provider_config
from kira_jobs import JobStore, JobError, atomic
import wallet

ADDRESS='0x'+'1'*40


class AlchemyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        kira_cli.initialize(self.root)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')})
        self.env.start();self.addCleanup(self.env.stop);self.addCleanup(self.temp.cleanup)

    def connect_fixture(self):
        config=provider_config(default_config(),'alchemy','KIRA_INVENTORY_FIXTURE')
        config['secret_env_file']=str(self.root/'fixture.env')
        atomic(self.root/'.kira.local.json',config)
        (self.root/'fixture.env').write_text('KIRA_INVENTORY_FIXTURE=fixture-only-key\n')

    def test_missing_connection_cannot_register_or_start_a_lookup(self):
        store=JobStore(self.root);before=(self.root/'wallets.json').read_bytes()
        with self.assertRaises(JobError) as error:
            store.submit({'schema_version':1,'operation':'wallet.add','input':{'address':ADDRESS,'tag':'Fixture'},'idempotency_key':'missing-alchemy'})
        self.assertEqual(error.exception.code,'alchemy_required')
        self.assertEqual(store.list(),[]);self.assertEqual((self.root/'wallets.json').read_bytes(),before)
        self.connect_fixture()
        job=store.submit({'schema_version':1,'operation':'wallet.add','input':{'address':ADDRESS,'tag':'Fixture'},'idempotency_key':'connected-alchemy'})
        self.assertEqual(job['scan_policy'],'alchemy_inventory_v1')
        self.assertIn('holdings',store.engine_command(job))

    def test_interactive_setup_keeps_key_out_of_output_jobs_and_configuration(self):
        secret='synthetic-hidden-setup-key';out=io.StringIO()
        with patch('sys.stdin.isatty',return_value=True),patch('getpass.getpass',return_value=secret),patch.object(JobStore,'launch'),contextlib.redirect_stdout(out):
            kira_cli.connect_alchemy(self.root)
        self.assertNotIn(secret,out.getvalue())
        files=list((self.root/'.secrets').glob('*.env'));self.assertEqual(len(files),1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode),0o600)
        store=JobStore(self.root);self.assertEqual(len(store.list()),1)
        store.worker()
        config=json.loads((self.root/'.kira.local.json').read_text())
        self.assertEqual(config['rpc']['priority'],'custom_first')
        self.assertEqual(config['discovery']['provider'],'alchemy')
        self.assertFalse(config['discovery']['public'])
        for p in self.root.rglob('*.json'):self.assertNotIn(secret,p.read_text())
        with patch('sys.stdin.isatty',return_value=False):
            with self.assertRaises(ValueError):kira_cli.connect_alchemy(self.root)
        self.assertEqual(len(list((self.root/'.secrets').glob('*.env'))),1)

    def test_sell_analysis_reuses_only_its_wallets_saved_holdings_without_discovery(self):
        self.connect_fixture();entry={'address':ADDRESS,'address_key':ADDRESS,'tags':['Fixture']}
        atomic(self.root/'wallets.json',{'wallets':[entry],'research_runs':[]})
        source=self.root/'snapshots/source'
        original={'wallet_address':ADDRESS,'pipeline':{'phase':'holdings'},'tokens':[]}
        atomic(source/'results.json',original)
        atomic(source/'onchain-summary.json',{'wallet':ADDRESS,'chains':[]})
        atomic(source/'market-prices.json',{'tokens':[]})
        before={p.name:p.read_bytes() for p in source.iterdir()}
        result={'compiled_at':'2026-10-17T00:00:00Z','status':'completed','counts':{}}
        with patch.object(wallet,'ROOT',self.root),patch.object(wallet,'source_check') as support,patch.object(wallet,'discover') as discover,patch.object(wallet,'run_node') as node,patch.object(wallet,'finish',return_value=result) as finish,patch.object(sys,'argv',['wallet.py','refresh','Fixture','--phase','sell','--holdings-snapshot','snapshots/source']),contextlib.redirect_stdout(io.StringIO()):
            wallet.main()
        support.assert_not_called();discover.assert_not_called();node.assert_not_called()
        self.assertEqual(finish.call_args.kwargs['holdings_source'],'snapshots/source')
        self.assertEqual({p.name:p.read_bytes() for p in source.iterdir()},before)
        child=self.root/'snapshots/child'
        with patch.object(wallet,'ROOT',self.root):
            with self.assertRaises(ValueError):wallet.saved_holdings({**entry,'address_key':'0x'+'2'*40},'snapshots/source',child)
            with self.assertRaises(ValueError):wallet.saved_holdings(entry,'../outside',child)

    def test_ows_creation_stops_before_vault_work_without_alchemy(self):
        from kira_ows import OwsStore
        runner=lambda request:self.fail('A missing data connection must not reach the wallet SDK.')
        store=OwsStore(self.root,vault=self.root/'vault',runner=runner)
        with self.assertRaises(JobError) as error:
            store.submit({'name':'Fixture wallet','tag':'Fixture','passphrase':'synthetic-passphrase','idempotency_key':'11111111-1111-4111-8111-111111111111'},create=True)
        self.assertEqual(error.exception.code,'alchemy_required')


if __name__=='__main__':unittest.main()
