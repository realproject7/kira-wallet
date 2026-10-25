"""Local external-agent contract. Synthetic records, no model or provider calls."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import re
import typing
from unittest.mock import patch
from kira_cli import initialize, sample
from kira_jobs import JobError, State
from kira_service import validate
from kira_tools import ReadTools, TOOLS, serve

class ReadToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'.kira.local.json')});self.env.start()
        initialize(self.root);sample(self.root);self.tools=ReadTools(self.root)
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_declared_reads_are_headless_and_preserve_identity(self):
        self.assertTrue(all(t['annotations']['readOnlyHint'] and not t['annotations']['openWorldHint'] for t in TOOLS))
        state=self.tools.call('portfolio_read',{});self.assertEqual(state['dashboard']['known_value_usd'],125)
        wallet=self.tools.call('wallet_read',{'wallet':'Demo wallet'});self.assertEqual(wallet['known_value_usd'],125)
        token=self.tools.call('token_read',{'chain_id':8453,'address':'0x'+'0'*39+'2'})
        self.assertEqual(token['positions'][0]['asset']['symbol'],'DEMO')
        self.assertEqual(self.tools.call('network_read',{'chain_id':8453})['id'],8453)
        self.assertEqual(self.tools.call('holdings_query',{'mode':'rank','limit':1})['results'][0]['positions'][0]['asset']['symbol'],'DEMO')
        self.assertFalse((self.root/'viewer-process.json').exists())
    def test_mutation_unknown_fields_and_escape_denied(self):
        for name,args in [('wallet_add',{'address':'anything'}),('portfolio_read',{'shell':'anything'}),('snapshot_read',{'snapshot_id':'../wallets.json'}),('network_read',{'chain_id':True})]:
            with self.assertRaises(JobError):self.tools.call(name,args)
        self.assertEqual(self.tools.call('job_list',{})['jobs'],[])
        result=self.tools.call('snapshot_read',{'snapshot_id':'snapshots/demo/initial'})
        self.assertEqual(result['wallets'][0]['assets'][0]['balance'],'100')
    def transcript(self):
        return '\n'.join(json.dumps(item) for item in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'portfolio_read','arguments':{}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'wallet_add','arguments':{}}}])+'\n'
    def test_stdio_handshake_and_typed_errors(self):
        output=io.StringIO();serve(self.root,io.StringIO(self.transcript()),output);rows=[json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual(len(rows),4);self.assertEqual(rows[0]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(len(rows[1]['result']['tools']),len(TOOLS));self.assertEqual(rows[2]['result']['structuredContent']['data']['dashboard']['known_value_usd'],125)
        self.assertTrue(rows[3]['result']['isError']);self.assertEqual(rows[3]['result']['structuredContent']['error']['code'],'unsupported_tool')
    def test_process_stdio_has_no_extra_output(self):
        result=subprocess.run([sys.executable,'kira_cli.py','--data-dir',str(self.root),'tools'],input=self.transcript(),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stderr,'');self.assertEqual(len([json.loads(s) for s in result.stdout.splitlines()]),4)
    def test_write_mode_reuses_idempotent_job_without_provider_access(self):
        tools=ReadTools(self.root,allow_write=True)
        args={'wallet':'Demo wallet','tags':['Updated name'],'idempotency_key':'external-tags-fixture'}
        with patch.object(tools.application.jobs,'launch'):
            first=tools.call('wallet_tags',args);second=tools.call('wallet_tags',args)
        self.assertEqual(first['job_id'],second['job_id'])
        tools.application.jobs.worker()
        self.assertEqual(tools.call('wallet_read',{'wallet':'Updated name'})['tags'],['Updated name'])
    def test_uninitialized_and_invalid_json(self):
        output=io.StringIO();serve(self.root,io.StringIO('not json\n'+json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'})+'\n'),output)
        rows=[json.loads(s) for s in output.getvalue().splitlines()];self.assertEqual(rows[0]['error']['code'],-32700);self.assertEqual(rows[1]['error']['code'],-32602)
    def test_job_list_filters_every_state_an_agent_can_read(self):
        jobs=self.tools.application.jobs;created={}
        for state in typing.get_args(State):
            job=jobs.submit({'schema_version':1,'operation':'wallet.setTags','input':{'wallet':'Demo wallet','tags':['Name '+state]},'idempotency_key':'state-filter-'+state})
            job['state']=state;jobs.save(job);created[job['job_id']]=state
        advertised=next(t for t in TOOLS if t['name']=='job_list')['inputSchema']['properties']['state']['enum']
        def states(value):
            result=self.tools.call('job_list',{'state':value,'limit':100})
            self.assertEqual(result['total'],len(result['jobs']))
            return sorted(created[job['job_id']] for job in result['jobs'])
        for state in typing.get_args(State):
            self.assertIn(state,advertised)
            self.assertIn(state,states(state))
        self.assertEqual(states('running'),['running'])
        self.assertEqual(states('active'),['queued','running'])
        self.assertEqual(states('succeeded'),['partial','succeeded'])
        self.assertEqual(states('attention'),['failed','interrupted'])
        self.assertEqual(states('all'),sorted(typing.get_args(State)))
        self.assertEqual(self.tools.call('job_list',{'wallet':'Demo wallet'})['total'],len(created))
        with self.assertRaises(JobError) as error:self.tools.call('job_list',{'state':'done'})
        self.assertTrue(all(value in str(error.exception) for value in advertised))
    def test_documented_call_examples_match_published_schemas(self):
        schemas={t['name']:t['inputSchema'] for t in TOOLS}
        from kira_service import WRITE_TOOLS
        schemas.update({t['name']:t['inputSchema'] for t in WRITE_TOOLS})
        examples=[]
        for path in ('README.md','docs/CLI.md','docs/AGENT_TOOLS.md','skills/kira-wallet/SKILL.md'):
            examples+=re.findall(r"kira call (\w+) --arguments '([^']*)'",Path(path).read_text())
        self.assertIn('job_list',{name for name,_ in examples})
        for name,arguments in examples:
            with self.subTest(name=name,arguments=arguments):validate(json.loads(arguments),schemas[name])
