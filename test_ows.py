"""OWS connection receipts never persist passphrases or replace existing tags."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from kira_ows import OwsStore
from kira_jobs import JobError, atomic

class OwsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]})
        self.rows=[];self.created=0;self.fail=False
        def runner(request):
            if request['action']=='create':
                existing=next((w for w in self.rows if w['name']==request['name']),None)
                if existing:return {'wallet':existing,'recovered':True}
                self.created+=1
                wallet={'id':str(uuid.uuid4()),'name':request['name'],'accounts':[{'chain_id':'eip155:1','address':'0x'+'1'*40}],'mnemonic':'must-never-project'}
                self.rows.append(wallet)
                if self.fail:self.fail=False;raise JobError('interrupted','Interrupted after local creation')
                return {'wallet':wallet}
            return {'wallets':self.rows}
        self.store=OwsStore(self.root,vault=self.root/'vault',runner=runner)
        self.launch=patch('kira_jobs.JobStore.launch');self.launch.start()
    def tearDown(self):self.launch.stop();self.temp.cleanup()
    def request(self):return {'name':'Test wallet','tag':'Exact Kira name','passphrase':'synthetic-encryption-only','idempotency_key':str(uuid.uuid4())}
    def test_encryption_required_and_secret_never_persisted(self):
        request=self.request()
        with self.assertRaises(JobError):self.store.submit({**request,'passphrase':''},create=True)
        result=self.store.submit(request,create=True)
        self.assertTrue(result['job_id']);self.assertEqual(self.created,1)
        self.assertEqual(self.store.submit(request,create=True)['job_id'],result['job_id'])
        self.assertEqual(self.created,1)
        for file in self.root.rglob('*.json'):
            text=file.read_text();self.assertNotIn(request['passphrase'],text);self.assertNotIn('must-never-project',text)
    def test_unknown_outcome_recovers_same_created_wallet(self):
        self.fail=True;request=self.request()
        with self.assertRaises(JobError):self.store.submit(request,create=True)
        recovered=self.store.submit(request,create=True);self.assertTrue(recovered['recovered']);self.assertFalse(recovered['created']);self.assertEqual(self.created,1)
        with self.assertRaises(JobError):self.store.submit({**request,'name':'Changed'},create=True)
    def test_existing_tags_and_vault_survive_disconnect(self):
        request=self.request();first=self.store.submit(request,create=True)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[{'address':'0x'+'1'*40,'address_key':'0x'+'1'*40,'tags':['Preserved']}],'research_runs':[]})
        result=self.store.submit({'wallet_id':first['connection']['wallet_id'],'tag':'New name','idempotency_key':str(uuid.uuid4())})
        self.assertEqual(result['connection']['tag'],'Preserved');self.assertIsNone(result['job_id'])
        self.store.disconnect();self.assertIsNone(self.store.status()['connection']);self.assertEqual(len(self.rows),1)

    def test_same_uuid_prefix_does_not_reuse_another_creation(self):
        first=self.request();first['idempotency_key']='12345678-1111-4111-8111-111111111111'
        second={**first,'idempotency_key':'12345678-2222-4222-8222-222222222222'}
        a=self.store.submit(first,create=True);b=self.store.submit(second,create=True)
        self.assertNotEqual(a['connection']['wallet_id'],b['connection']['wallet_id']);self.assertEqual(self.created,2)
        self.assertTrue(a['created']);self.assertTrue(b['created'])
    def test_unrelated_reserved_name_is_not_reused(self):
        request=self.request();self.rows.append({'id':'unrelated','name':request['name']+'-'+request['idempotency_key'],'accounts':[]})
        with self.assertRaisesRegex(JobError,'already uses'):self.store.submit(request,create=True)
        self.assertEqual(self.created,0)
