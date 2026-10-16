"""Provider isolation, secret redaction and bounded capability diagnostics."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
import kira_cli
import kira_config as config
import wallet

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'KIRA_DATA_DIR':str(self.root),'KIRA_CONFIG':str(self.root/'config.json'),'PATH':os.environ.get('PATH','')},clear=True);self.env.start()
        self.network={'chain_id':8453,'public_rpc':['https://public.example']}
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def save(self,cfg):kira_cli.atomic(config.config_path(),cfg)
    def test_cli_provider_changes_preserve_explicit_keyless_opt_out(self):
        cfg=config.default_config();cfg['discovery']['public']=False;self.save(cfg)
        for provider in ('none','alchemy'):
            with contextlib.redirect_stdout(io.StringIO()),patch.object(sys,'argv',['kira','discovery',provider]):self.assertEqual(kira_cli.main(),0)
            self.assertFalse(config.load_config()['discovery']['public'])

    def test_public_without_secrets_has_incomplete_discovery(self):
        self.assertEqual(config.endpoints(self.network),['https://public.example']);self.assertFalse(config.secret_values())
        with patch.object(wallet,'load_config',return_value=config.default_config()),patch.object(wallet.h,'secrets',return_value={}),patch.object(wallet,'fetch') as fetch:
            result=wallet.discover('0x'+'1'*40,self.network,self.root)
        fetch.assert_not_called();self.assertFalse(result['complete']);self.assertEqual(result['tokens'],[])
    def test_custom_fallback_defaults_automatic_and_respects_explicit_opt_out(self):
        cfg=config.default_config();cfg['rpc'].update(mode='custom',chains={'8453':{'url_env':'BASE_RPC'}});self.save(cfg)
        self.assertEqual(config.endpoints(self.network),['https://public.example'])
        with patch.dict(os.environ,{'BASE_RPC':'https://custom.example/private-key?secret=value'}):
            self.assertEqual(len(config.endpoints(self.network)),2)
            cfg['rpc']['allow_public_fallback']=True;self.save(cfg)
            self.assertEqual(config.endpoints(self.network)[0],'https://public.example')
            self.assertNotIn('private-key',config.redact('failed https://custom.example/private-key?secret=value'))
            cfg['rpc']['allow_public_fallback']=False;self.save(cfg)
            self.assertEqual(config.endpoints(self.network),['https://custom.example/private-key?secret=value'])
    def test_compatibility_file_is_optional_and_environment_wins(self):
        file=self.root/'private.env';file.write_text('ALCHEMY_API_KEY=fixture-file-key\n')
        cfg=config.default_config();cfg['secret_env_file']=str(file);cfg['discovery']['provider']='alchemy'
        cfg['rpc'].update(mode='custom',chains={'8453':{'url_env':'ALCHEMY_API_KEY','alchemy_network':'base-mainnet'}});self.save(cfg)
        with patch.dict(os.environ,{'ALCHEMY_API_KEY':'fixture-env-key'}):
            self.assertIn('fixture-env-key',config.endpoints(self.network)[-1])
            self.assertNotIn('fixture-env-key',config.redact('Bearer fixture-env-key'))
        file.unlink();self.assertEqual(config.endpoints(self.network),['https://public.example'])
    def test_malformed_or_insecure_configuration_has_safe_errors(self):
        config.config_path().write_text('{bad secret-format')
        with self.assertRaisesRegex(ValueError,'malformed'):config.load_config()
        cfg=config.default_config();cfg['rpc']['chains']={'8453':{'url_env':'bad ref'}};self.save(cfg)
        with self.assertRaisesRegex(ValueError,'environment references'):config.load_config()
        cfg['rpc'].update(mode='custom',chains={'8453':{'url_env':'RPC'}});self.save(cfg)
        with patch.dict(os.environ,{'RPC':'http://remote.example/key'}):
            self.assertEqual(config.endpoints(self.network),['https://public.example'])
    def test_wrong_chain_historical_failure_and_budget(self):
        args=type('Args',(),{'live':True,'chains':'8453','budget':5})()
        import research
        for responses,calls in [([{'result':'0x1'}],1),([{'result':hex(8453)},{'result':'0x100'},{'result':'0xab'},{'result':'0xab'},{'error':{'message':'archive unsupported'}}],5)]:
            output=io.StringIO()
            with patch.object(config,'endpoints',return_value=['https://fixture.example']),patch.object(research,'rpc',side_effect=responses) as rpc,contextlib.redirect_stdout(output):
                code=kira_cli.doctor(args,self.root)
            data=json.loads(output.getvalue());self.assertEqual(code,2);self.assertEqual(data['probes'][0]['status'],'unavailable');self.assertEqual(rpc.call_count,calls)
        args.budget=2;output=io.StringIO()
        with patch.object(config,'endpoints',return_value=['https://fixture.example']),patch.object(research,'rpc',side_effect=[{'result':hex(8453)},{'result':'0x100'}]) as rpc,contextlib.redirect_stdout(output):
            self.assertEqual(kira_cli.doctor(args,self.root),2)
        self.assertEqual(rpc.call_count,2)
    def test_cli_rpc_default_and_explicit_custom_only_are_preserved(self):
        import subprocess,sys
        command=[sys.executable,str(Path(kira_cli.__file__)),'--data-dir',str(self.root),'rpc','set','--chain','8453','--url-env','RPC']
        for flags,expected in (([],True),(['--custom-only'],False),([],False),(['--public-fallback'],True)):
            result=subprocess.run(command+flags,capture_output=True,text=True,env=os.environ.copy())
            self.assertEqual(result.returncode,0);self.assertEqual(config.load_config()['rpc']['allow_public_fallback'],expected)
    def test_unreadable_secret_file_still_exports_public_child_runtime(self):
        cfg=config.default_config();cfg['secret_env_file']=str(self.root/'private.env');cfg['rpc']['mode']='custom';self.save(cfg)
        with patch.object(config,'secret_values',side_effect=ValueError('Fixture permission failure')):
            runtime=config.runtime()
        self.assertTrue(runtime['endpoints']['8453'])
        self.assertEqual(runtime['secrets'],[])
    def test_provider_auth_headers_and_arbitrary_urls_are_redacted(self):
        redacted=config.redact('Authorization: Bearer secret-token https://user:password@rpc.example/key?apiKey=another-token')
        self.assertNotIn('another-token',redacted);self.assertNotIn('password',redacted)
        self.assertNotIn('secret-token',redacted)

    def test_priority_and_legacy_custom_only(self):
        cfg=config.default_config();cfg['rpc'].update(mode='custom',chains={'8453':{'url_env':'RPC'}})
        with patch.dict(os.environ,{'RPC':'https://custom.example'}):
            self.assertEqual(config.endpoints(self.network,cfg),['https://public.example','https://custom.example'])
            cfg['rpc']['priority']='custom_first'
            self.assertEqual(config.endpoints(self.network,cfg),['https://custom.example','https://public.example'])
            cfg['rpc'].pop('priority');cfg['rpc']['allow_public_fallback']=False
            self.assertEqual(config.endpoints(self.network,cfg),['https://custom.example'])
        cfg['rpc']['priority']='unknown';self.save(cfg)
        with self.assertRaisesRegex(ValueError,'priority'):config.load_config()

if __name__=='__main__':unittest.main()
