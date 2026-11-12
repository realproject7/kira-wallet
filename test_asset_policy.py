"""Valuation membership, cross-surface totals and explicit risk lookup boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from asset_policy import apply, fetch_risk
from kira_cli import initialize, sample
from kira_jobs import JobError, atomic
from kira_service import Application, describe_tools
import test_application

ADDRESS = '0x' + '1' * 40

class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def asset(self, **changes):
        return {'id':'56:'+ADDRESS,'chain_id':56,'environment':'mainnet','is_native':False,
                'value_usd':120000,'price':{'basis':'DEX market'},'market_pools':[{'liquidity_usd':95000}],
                'sell_out':None,**changes}
    def wallets(self, assets):
        return [{'assets':[a],'chains':[{'id':a['chain_id']}]} for a in assets]
    def test_material_pool_mismatch_uses_full_cross_wallet_inventory(self):
        wallets=self.wallets([self.asset(),self.asset()]);apply(wallets,self.root)
        self.assertEqual([w['assets'][0]['portfolio_status'] for w in wallets],['review','review'])
        self.assertEqual([w['known_value_usd'] for w in wallets],[None,None])
        self.assertEqual(wallets[0]['assets'][0]['value_usd'],120000)
    def test_unknown_name_domain_and_closed_source_alone_do_not_exclude(self):
        wallets=self.wallets([self.asset(value_usd=None,name='ordinary.io')])
        atomic(self.root/'token-policy.json',{'overrides':{},'risk_checks':{'56:'+ADDRESS:{'flags':['Closed source'],'review_reasons':[],'status':'unknown'}}})
        apply(wallets,self.root);self.assertEqual(wallets[0]['assets'][0]['portfolio_status'],'portfolio')
    def test_quote_or_curve_does_not_trigger_the_spot_only_rule(self):
        for changes in ({'sell_out':{'value_usd':0}}, {'price':{'basis':'Curve spot'}}, {'value_usd':None}):
            wallets=self.wallets([self.asset(**changes),self.asset(**changes)])
            apply(wallets,self.root);self.assertTrue(wallets[0]['assets'][0]['included_in_totals'])
    def test_manual_include_keeps_warning_and_contract_identity_scope(self):
        atomic(self.root/'token-policy.json',{'overrides':{'56:'+ADDRESS:{'mode':'include'}},'risk_checks':{}})
        other=self.asset(id='137:'+ADDRESS,chain_id=137)
        wallets=self.wallets([self.asset(),self.asset(),other]);apply(wallets,self.root)
        self.assertTrue(wallets[0]['assets'][0]['included_in_totals'])
        self.assertTrue(wallets[0]['assets'][0]['valuation_policy']['reasons'])
        self.assertEqual(wallets[2]['assets'][0]['valuation_policy']['mode'],'auto')

class PolicyApplicationTest(unittest.TestCase):
    setUp=test_application.ApplicationTest.setUp
    tearDown=test_application.ApplicationTest.tearDown
    def args(self, mode='exclude'):
        token=self.app.views.refresh()['details']['tokens'][0]
        return {'chain_id':token['chain_id'],'address':token['address'] or 'native','mode':mode,'idempotency_key':'policy-test-action'}
    def test_exclusion_persists_all_wallets_and_invalidates_cached_totals(self):
        snapshots={str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'snapshots').rglob('*') if p.is_file()}
        state=self.app.views.refresh();args=self.args();identity=str(args['chain_id'])+':'+args['address']
        affected=[a for w in state['wallets'] for a in w['assets'] if a['id']==identity]
        old=state['dashboard']['known_value_usd'];revision=self.app.views.revision
        with patch('asset_policy.fetch_risk',side_effect=AssertionError('Implicit risk lookup')):
            receipt=self.app.call('token_policy',args,allow_write=True)
            self.assertEqual(receipt,self.app.call('token_policy',args,allow_write=True))
            after=Application(self.root).views.refresh()
        delta=sum(a['value_usd'] or 0 for a in affected)
        self.assertAlmostEqual(after['dashboard']['known_value_usd'] or 0,old-delta)
        self.assertNotEqual(Application(self.root).views.summary()[1],revision)
        self.assertNotIn(identity,[a['id'] for a in self.app.views.holdings()['assets']])
        excluded=self.app.views.holdings(portfolio_status='excluded')['assets']
        self.assertEqual([a['id'] for a in excluded],[identity])
        self.assertEqual(self.app.views.token(args['chain_id'],args['address'])['portfolio_status'],'excluded')
        self.assertTrue(all(a['value_usd'] is not None for a in affected))
        valuation=self.app.call('holdings_query',{'mode':'aggregate'})['valuation']['all_priced_positions']['estimated_value_usd']
        self.assertAlmostEqual(float(valuation or 0),old-delta)
        self.assertNotIn(identity,[r['identity'] for r in self.app.call('holdings_query',{'mode':'rank'})['results']])
        facts=self.app.call('token_read',{k:v for k,v in args.items() if k in ('chain_id','address')})
        self.assertTrue(all(not p['asset']['included_in_totals'] for p in facts['positions']))
        self.assertFalse(Application(self.root).jobs.list())
        args.update(mode='auto',idempotency_key='policy-restore-action');self.app.call('token_policy',args,allow_write=True)
        self.assertAlmostEqual(self.app.views.refresh()['dashboard']['known_value_usd'],old)
        self.assertEqual(snapshots,{str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'snapshots').rglob('*') if p.is_file()})
    def test_collision_and_unrecorded_identity_are_rejected(self):
        args=self.args();self.app.call('token_policy',args,allow_write=True)
        with self.assertRaises(JobError):self.app.call('token_policy',{**args,'mode':'include'},allow_write=True)
        with self.assertRaises(JobError):self.app.call('token_policy',{**args,'address':'0x'+'f'*40},allow_write=True)
        with self.assertRaises(JobError):self.app.submit({'schema_version':1,'operation':'token.policy','input':[],'idempotency_key':'invalid-test'})
        with self.assertRaises(JobError):self.app.call('token_policy',args)
    def test_request_keys_cannot_cross_token_and_job_operations(self):
        args=self.args();self.app.call('token_policy',args,allow_write=True)
        with patch.object(self.app.jobs,'launch'):
            with self.assertRaises(JobError):
                self.app.call('wallet_tags',{'wallet':'Demo wallet','tags':['Daily wallet'],'idempotency_key':args['idempotency_key']},allow_write=True)
            self.app.call('wallet_tags',{'wallet':'Demo wallet','tags':['Daily wallet'],'idempotency_key':'queued-tags-request'},allow_write=True)
        with self.assertRaises(JobError):
            self.app.call('token_policy',{**args,'idempotency_key':'queued-tags-request'},allow_write=True)
    def test_risk_is_explicit_retains_previous_flags_on_failure_and_obeys_override(self):
        registry=json.loads((self.root/'wallets.json').read_text());registry.pop('demo',None);atomic(self.root/'wallets.json',registry)
        args=self.args();args.pop('mode')
        if args['address']=='native':
            token=next(t for t in self.app.views.refresh()['details']['tokens'] if t['address']);args.update(chain_id=token['chain_id'],address=token['address'])
        args['idempotency_key']='explicit-risk-test'
        observation={'provider':'GoPlus','observed_at':'2026-11-12T02:00:00Z','source':'https://api.gopluslabs.io/','completed':True,'status':'flagged','review_reasons':['Provider reports a honeypot.'],'flags':[]}
        with patch('asset_policy.fetch_risk',return_value=observation) as fetch:
            self.app.call('token_risk_check',args,allow_write=True);self.app.call('token_risk_check',args,allow_write=True)
            fetch.assert_called_once()
        self.assertEqual(self.app.views.token(args['chain_id'],args['address'])['portfolio_status'],'review')
        with patch('asset_policy.fetch_risk',return_value={'observed_at':'2026-11-12T03:00:00Z','completed':False,'status':'unknown'}):
            self.app.call('token_risk_check',{**args,'idempotency_key':'risk-failed-attempt'},allow_write=True)
        token=self.app.views.token(args['chain_id'],args['address']);self.assertEqual(token['risk_check']['status'],'flagged');self.assertIn('last_attempt',token['risk_check'])
        self.app.call('token_policy',{**args,'mode':'include','idempotency_key':'explicit-include'},allow_write=True)
        token=self.app.views.token(args['chain_id'],args['address']);self.assertTrue(token['included_in_totals']);self.assertTrue(token['valuation_policy']['reasons'])
    def test_demo_rejects_external_risk_check(self):
        args=self.args();args.pop('mode')
        with self.assertRaises(JobError):self.app.call('token_risk_check',args,allow_write=True)
    def test_catalog_documents_immediate_write_and_risk_destination(self):
        self.assertIn('immediately',describe_tools('token_policy')['description'])
        self.assertIn('GoPlus',describe_tools('token_risk_check')['description'])

class RiskResponseTest(unittest.TestCase):
    def response(self,token,code=1):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,*_):return json.dumps({'code':code,'result':{ADDRESS:token}}).encode()
        return Response()
    def test_closed_source_missing_fields_are_unknown_not_clean(self):
        with patch('urllib.request.urlopen',return_value=self.response({'is_open_source':'0','sell_tax':''})):
            result=fetch_risk(56,ADDRESS)
        self.assertEqual(result['status'],'unknown');self.assertEqual(result['review_reasons'],[])
    def test_explicit_honeypot_and_tax_flags(self):
        with patch('urllib.request.urlopen',return_value=self.response({'is_honeypot':'1','sell_tax':'0.99'})):
            result=fetch_risk(56,ADDRESS)
        self.assertEqual(result['status'],'flagged');self.assertEqual(len(result['review_reasons']),2)
    def test_errors_and_empty_results_remain_unknown(self):
        for response in (self.response({}),self.response({},code=0)):
            with patch('urllib.request.urlopen',return_value=response):
                result=fetch_risk(56,ADDRESS)
            self.assertFalse(result['completed']);self.assertEqual(result['status'],'unknown')
        with patch('urllib.request.urlopen',side_effect=OSError()):self.assertFalse(fetch_risk(56,ADDRESS)['completed'])
