"""Read-only agent adapter tests. No account, model or provider connection."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from kira_cli import initialize, sample
from kira_jobs import JobError
from kira_tools import ReadTools, TOOLS, serve

class ReadToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
        initialize(self.root);sample(self.root);self.tools=ReadTools(self.root)
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_declared_read_tools_and_exact_identity(self):
        self.assertTrue(all(t['annotations']['readOnlyHint'] and not t['annotations']['openWorldHint'] for t in TOOLS))
        state=self.tools.call('portfolio_read',{});self.assertEqual(state['dashboard']['known_value_usd'],125)
        wallet=self.tools.call('wallet_read',{'wallet':'Demo wallet'});self.assertEqual(wallet['known_value_usd'],125)
        token=self.tools.call('token_read',{'chain_id':8453,'address':'0x'+'0'*39+'2'});self.assertEqual(token['symbol'],'DEMO')
        self.assertEqual(self.tools.call('network_read',{'chain_id':8453})['id'],8453)
        with self.assertRaises(JobError):self.tools.call('token_read',{'chain_id':1,'address':'0x'+'0'*39+'2'})
    def test_mutation_unknown_fields_and_path_escape_denied(self):
        for name,args in [('wallet.add',{'address':'anything'}),('portfolio_read',{'shell':'anything'}),('snapshot_read',{'snapshot_id':'../wallets.json'}),('network_read',{'chain_id':True})]:
            with self.assertRaises(JobError):self.tools.call(name,args)
        self.assertEqual(self.tools.call('job_list',{}),[])
        self.assertEqual(self.tools.call('snapshot_read',{'snapshot_id':'snapshots/demo/initial'})['tokens'][0]['wallet_balance'],'100')
        same=self.tools.call('snapshots_compare',{'before':'snapshots/demo/initial','after':'snapshots/demo/initial'});self.assertEqual(same['positions'][0]['balance_delta'],'0')
    def transcript(self):
        return '\n'.join(json.dumps(item) for item in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'portfolio_read','arguments':{}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'wallet.add','arguments':{}}}])+'\n'
    def test_stdio_handshake_typed_results_and_mutation_denial(self):
        output=io.StringIO();serve(self.root,io.StringIO(self.transcript()),output);rows=[json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual(len(rows),4);self.assertEqual(rows[0]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(len(rows[1]['result']['tools']),8);self.assertEqual(rows[2]['result']['structuredContent']['data']['dashboard']['known_value_usd'],125)
        self.assertTrue(rows[3]['result']['isError'])
    def test_process_stdio_no_extra_stdout_or_auth(self):
        result=subprocess.run([sys.executable,'kira_cli.py','--data-dir',str(self.root),'tools'],input=self.transcript(),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stderr,'');self.assertEqual(len([json.loads(s) for s in result.stdout.splitlines()]),4)
    def test_uninitialized_invalid_json_and_unknown_method(self):
        output=io.StringIO();serve(self.root,io.StringIO('not json\n'+json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'})+'\n'),output)
        rows=[json.loads(s) for s in output.getvalue().splitlines()];self.assertEqual(rows[0]['error']['code'],-32700);self.assertEqual(rows[1]['error']['code'],-32602)

if __name__=='__main__':unittest.main()
