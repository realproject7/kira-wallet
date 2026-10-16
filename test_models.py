"""Metadata never starts a model turn. Synthetic stdio runners only."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from kira_models import clean_catalog, codex_catalog, catalog
from kira_agent import AgentStore, native_env
from kira_jobs import atomic, JobError

class ModelsTest(unittest.TestCase):
    def test_filter_and_bound_metadata(self):
        rows=[None,{'model':'bad model'}, {'model':'hidden','hidden':True}, {'model':'valid','displayName':'Readable model'}, {'model':'valid'}]
        self.assertEqual(clean_catalog(rows),[{'id':'valid','name':'Readable model'}])
        self.assertEqual(len(clean_catalog([{'model':f'model-{i}'} for i in range(120)])),40)
        for value in ({},None,'invalid'):self.assertEqual(clean_catalog(value),[])
    def runner(self, directory, body):
        path=Path(directory)/'codex';path.write_text('#!/usr/bin/env python3\n'+body);path.chmod(0o700);return str(path)
    def test_only_metadata_messages_and_sanitized_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path=self.runner(directory,"""import json,sys,os
request=json.loads(sys.stdin.readline());assert request['method']=='initialize'
assert 'ALCHEMY_API_KEY' not in os.environ
print(json.dumps({'id':1,'result':{}}),flush=True)
assert json.loads(sys.stdin.readline())=={'method':'initialized'}
request=json.loads(sys.stdin.readline());assert request['method']=='model/list'
assert request['params']['includeHidden'] is False
print(json.dumps({'id':2,'result':{'data':[{'model':'native-model','displayName':'Native model'}]}}),flush=True)
""")
            with patch.dict(os.environ,{'ALCHEMY_API_KEY':'synthetic-secret'}):
                self.assertEqual(codex_catalog(path,native_env()),[{'id':'native-model','name':'Native model'}])
    def test_deadline_and_malformed_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path=self.runner(directory,'import time\ntime.sleep(30)\n')
            started=time.monotonic()
            with self.assertRaises(TimeoutError):codex_catalog(path,native_env(),timeout=.15)
            self.assertLess(time.monotonic()-started,3)
            path=self.runner(directory,"import sys,json\nsys.stdin.readline()\nprint('{\"id\":1,\"result\":{}}',flush=True)\nsys.stdin.readline();sys.stdin.readline()\nprint('{\"id\":2,\"result\":[]}',flush=True)\n")
            self.assertEqual(codex_catalog(path,native_env()),[])
    def test_catalog_failure_default_and_claude_aliases(self):
        with patch('kira_models.codex_catalog',side_effect=ValueError('private native message')),patch('kira_models.shutil.which',return_value='synthetic'):
            result=catalog('codex');self.assertEqual(result['models'],[]);self.assertNotIn('private native message',json.dumps(result))
        self.assertEqual([r['id'] for r in catalog('claude')['models']],['sonnet','opus','haiku'])
    def test_store_gates_native_catalog_caches_and_explicit_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);atomic(root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]})
            store=AgentStore(root,detector=lambda:[{'id':'codex','installed':True,'supported':False,'logged_in':True}])
            with patch('kira_models.catalog',return_value={'models':[]}) as metadata:
                self.assertEqual(store.models('codex')['models'],[]);metadata.assert_not_called()
                store.detector=lambda:[{'id':'codex','installed':True,'supported':True,'logged_in':True}]
                store.models('codex',True);store.models('codex');self.assertEqual(metadata.call_count,1)
                store.models('codex',True);self.assertEqual(metadata.call_count,2)
            with self.assertRaises(JobError):store.models('unknown')
