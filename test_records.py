"""Preserved recorded financial projections and query completeness invariants."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from kira_records import projection, recorded_valuation
from kira_jobs import JobError, atomic
from kira_cli import sample

def settings(**changes):
    return {'scope':'none','wallet':None,'wallet_tools':False,**changes}

class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        atomic(self.root/'wallets.json',{'schema_version':1,'wallets':[],'research_runs':[]});sample(self.root)
    def tearDown(self):self.temp.cleanup()

    def test_rank_completion_combines_only_contiguous_pages_of_the_same_query(self):
            from kira_records import read_completion,read_receipt
            def page(offset,count,available=40,**filters):
                args={'mode':'rank','offset':offset,'limit':25,**filters}
                result={'query_scope':{'mode':'rank','full_inventory_scanned':True,'complete':True,
                        'offset':offset,'returned_count':count,'requested_limit':25,'result_count':available}}
                return read_receipt('holdings_query',args,result)
            def status(rows):return read_completion('top 30 tokens',rows,None)['status']
            first=page(0,25)
            self.assertEqual(status([first]),'partial')
            self.assertEqual(status([first,page(25,5)]),'complete')
            self.assertEqual(status([first,first]),'partial')
            self.assertEqual(status([first,page(26,5)]),'partial')
            self.assertEqual(status([first,page(25,5,chain_id=8453)]),'partial')
            self.assertEqual(status([page(0,7,available=7)]),'complete')
            self.assertEqual(status([page(0,0,available=0)]),'complete')

    def test_rank_completion_normalizes_filters_used_by_real_queries(self):
            from copy import deepcopy
            from kira_records import scoped_wallets,read_receipt,read_completion
            from kira_research_tools import ResearchTools
            config=settings(scope='portfolio',wallet_tools=True)
            tools=ResearchTools(self.root,config)
            wallet=scoped_wallets(self.root,config)[0];base=wallet['assets'][0]
            wallet['assets']=[{**deepcopy(base),'id':f'8453:0x{i:040x}','address':f'0x{i:040x}',
                'symbol':'FIX','name':'Fixture '+str(i),'chain_id':8453,'value_usd':i+100,
                'environment':'mainnet','archived':False} for i in range(40)]
            cases=[({'wallet':wallet['name']},{'wallet':wallet['address']},'complete'),
                   ({'minimum_value_usd':100},{'minimum_value_usd':'1e2'},'complete'),
                   ({'query':'FIX'},{'query':' fix '},'complete'),
                   ({},{'environment':'mainnet','group_by':'asset','query':' '},'complete'),
                   ({'query':'FIX'},{'query':'Fixture'},'partial'),
                   ({'minimum_value_usd':100},{'minimum_value_usd':'99'},'partial'),
                   ({},{'environment':'all'},'partial'),
                   ({},{'group_by':'position'},'partial')]
            with patch('kira_records.scoped_wallets',return_value=[wallet]):
                for first,second,expected in cases:
                    with self.subTest(first=first,second=second):
                        receipts=[];identities=[]
                        for offset,filters in ((0,first),(25,second)):
                            args={'mode':'rank','limit':25,'offset':offset,**filters}
                            result=tools.call('holdings_query',args,'rank-regression')
                            receipts.append(read_receipt('holdings_query',args,result))
                            identities.extend(row['identity'] for row in result['results'])
                        self.assertEqual(len(set(identities)),40)
                        for pages in (receipts,list(reversed(receipts))):
                            self.assertEqual(read_completion('top 30 tokens',pages,tools)['status'],expected)

    def test_coverage_counts_identity_and_safe_provider_evidence_survive_compaction(self):
            file=self.root/'snapshots/demo/initial/results.json';result=json.loads(file.read_text())
            result['coverage'].append({**result['coverage'][0],'chain_id':1,'name':'Ethereum','rpc_status':'pending','environment':'mainnet'})
            result['coverage'].append({**result['coverage'][0],'chain_id':11155111,'name':'Sepolia','rpc_status':'unavailable','environment':'testnet'})
            result['coverage'][0]['rpc_routes']=[{'endpoint_class':'public','outcome':'failed','count':1,'http_status':429,'url':'SECRET-MARKER'}, {'endpoint_class':'custom','outcome':'succeeded','count':1}]
            result['tokens'][0]['token_address']='0x538DCE05786fceffC46032f9873589D424dBe0f8';atomic(file,result)
            context=projection(self.root,settings(scope='portfolio'),inventory=True);row=context['wallets'][0]
            self.assertEqual(row['coverage_counts']['mainnet']['rpc']['pending'],{'count':1,'chain_ids':[1]})
            self.assertEqual(row['coverage_counts']['testnet']['rpc']['unavailable']['count'],1)
            self.assertEqual(row['assets'][0]['display_identity'],'8453:0x538DCE…dBe0f8')
            self.assertEqual(row['chains'][0]['rpc_routes'][1]['endpoint_class'],'custom');self.assertNotIn('SECRET-MARKER',json.dumps(context))

    def test_retired_records_keep_history_but_leave_current_valuation(self):
            from chain_lifecycle import lifecycle,retired
            file=self.root/'snapshots/demo/initial/results.json';result=json.loads(file.read_text())
            result['coverage'][0].update(chain_id=666666666,name='Degen L3',native_symbol='ETH',rpc_status='available')
            result['tokens'][0]['chain_id']=666666666;atomic(file,result)
            context=projection(self.root,settings(scope='portfolio'),inventory=True)
            wallet=context['wallets'][0];asset=wallet['assets'][0]
            self.assertTrue(asset['archived']);self.assertIsNone(asset['value_usd']);self.assertIsNotNone(asset['historical_value_usd'])
            self.assertEqual(wallet['chains'][0]['rpc_status'],'retired')
            self.assertTrue(retired(666666666));self.assertFalse(retired(8453));self.assertFalse(retired(8217));self.assertTrue(retired(5112));self.assertTrue(retired(54176))
            self.assertEqual(lifecycle(5112)['confirmation'],'operator');self.assertFalse(lifecycle(5112)['verified'])
            self.assertEqual(lifecycle(8217)['provider_notice']['provider'],'The Graph')
            self.assertEqual(lifecycle(999999)['audit_result'],'not_reviewed')

    def test_projection_preserves_unknowns_and_excludes_private_fields(self):
            registry=json.loads((self.root/'wallets.json').read_text());address='0x'+'2'*40
            registry['wallets'].append({'address':address,'address_key':address,'tags':['Second synthetic']});atomic(self.root/'wallets.json',registry)
            one=projection(self.root,settings(scope='wallet',wallet=registry['wallets'][0]['address_key']))
            self.assertEqual(len(one['wallets']),1);self.assertNotIn(address,json.dumps(one))
            self.assertNotIn('report_url',json.dumps(one));self.assertNotIn('image_url',json.dumps(one));self.assertNotIn('source',json.dumps(one))
            all_=projection(self.root,settings(scope='portfolio'));self.assertIsNone(all_['wallets'][1]['known_value_usd'])
            self.assertEqual(projection(self.root,settings())['scope'],'none')

    def test_market_detail_cannot_displace_holdings_or_disable_large_wallet_chat(self):
            from copy import deepcopy
            import sys
            sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
            import model
            state,stamp,stale=model.load_state(self.root)
            wallet=state['wallets'][0];template=wallet['assets'][0]
            wallet['assets']=[]
            for index in range(100):
                asset=deepcopy(template);asset['id']=f'8453:0x{index:040x}'
                asset['market_pools']=[{'venue':'Uniswap V3','pool':'0x'+'3'*40,
                    'url':'https://example.com/pool/'+str(pool),'liquidity_usd':100,
                    'price_usd':1,'observed_at':'2026-10-05T00:00:00Z',
                    'pair':[{'symbol':'USDC','address':'0x'+'4'*40}]} for pool in range(12)]
                wallet['assets'].append(asset)
            with patch('model.load_state',return_value=(state,stamp,stale)):
                facts=projection(self.root,settings(scope='portfolio'))
                self.assertEqual(len(facts['wallets'][0]['assets']),12)
                self.assertEqual(facts['wallets'][0]['asset_count'],100)
                self.assertEqual(facts['wallets'][0]['next_offset'],12)
                self.assertLessEqual(len(json.dumps(facts,ensure_ascii=False).encode()),240_000)
                self.assertGreater(sum(a['pools_omitted'] for a in facts['wallets'][0]['assets']),0)
                detail=projection(self.root,settings(scope='portfolio'),token_id=wallet['assets'][-1]['id'])
                self.assertEqual(len(detail['wallets'][0]['assets']),1)
                self.assertEqual(len(detail['wallets'][0]['assets'][0]['pools']),12)

    def test_full_inventory_valuation_categories_survive_paging_and_stale_prices(self):
            from copy import deepcopy
            import model
            state,stamp,stale=model.load_state(self.root)
            wallet=state['wallets'][0];template=wallet['assets'][0]
            def position(value,**fields):
                return {**deepcopy(template),'value_usd':value,'curve_state':None,'exit_route':'unverified','is_native':False,
                        'price':{'usd':1,'basis':'indicative curve','observed_at':'2026-10-01T00:00:00Z'},**fields}
            wallet['assets']=[position(12,is_native=True),position(3,curve_state={'reserve_balance':'100'}),
                              position(5),position(None),position(1000,environment='testnet',chain_id=84532)]
            for index,asset in enumerate(wallet['assets']):
                asset['id']=str(asset['chain_id'])+(':'+'native' if asset['is_native'] else ':0x'+format(index,'040x'))
            with patch('model.load_state',return_value=(state,stamp,stale)):
                projected=projection(self.root,settings(scope='portfolio'),limit=1)['wallets'][0]
                token=projection(self.root,settings(scope='portfolio'),token_id=wallet['assets'][0]['id'])['wallets'][0]
            facts=projected['recorded_valuation']
            self.assertEqual(len(projected['assets']),1)
            self.assertEqual(facts['all_priced_positions']['estimated_value_usd'],'20')
            self.assertEqual(len(token['assets']),1)
            self.assertEqual(token['recorded_valuation']['all_priced_positions']['estimated_value_usd'],'20')
            self.assertEqual(facts['categories']['native']['estimated_value_usd'],'12')
            self.assertEqual(facts['categories']['mintclub']['estimated_value_usd'],'3')
            self.assertEqual(facts['categories']['other_tokens']['estimated_value_usd'],'5')
            self.assertEqual(facts['unpriced_mainnet_count'],1)
            self.assertIn('Not a floor',facts['interpretation'])
            self.assertEqual(facts['all_priced_positions']['price_observed_at']['from'],'2026-10-01T00:00:00Z')
            empty=recorded_valuation([position(None),position(1000,environment='testnet')])
            self.assertIsNone(empty['all_priced_positions']['estimated_value_usd'])
            self.assertIsNone(empty['categories']['mintclub']['estimated_value_usd'])

    def test_exit_quotes_only_reach_explicitly_approved_context(self):
            registry=json.loads((self.root/'wallets.json').read_text())
            entry=registry['wallets'][0];path=self.root/entry['latest_snapshot']['result']
            snapshot=json.loads(path.read_text());token=snapshot['tokens'][0]
            token['balance_block_number']=123
            token['mintclub']={'reserve_token':'0x'+'9'*40,'reserve_symbol':'SAMPLE','reserve_balance':'100',
                'funded':True,'price_for_next_mint_in_reserve_token':'1','source_url':'https://example.com/fixture',
                'observed_at':'2026-10-04T00:00:00Z','block_number':123,'wallet_full_burn':{'net_refund':'12','gas_included':False}}
            atomic(path,snapshot)
            self.assertNotIn('12',json.dumps(projection(self.root,settings())))
            scoped=projection(self.root,settings(scope='wallet',wallet=entry['address_key']))
            quote=scoped['wallets'][0]['assets'][0]['exit_quote']
            self.assertEqual(quote['output_amount'],'12')
            self.assertFalse(quote['gas_included'])
            self.assertNotIn('source_url',json.dumps(scoped))

    def test_large_inventory_pages_without_changing_scope_or_unknown_values(self):
            from copy import deepcopy
            import model
            state,stamp,stale=model.load_state(self.root)
            wallet=state['wallets'][0];template=wallet['assets'][0]
            wallet['assets']=[]
            for index in range(800):
                asset=deepcopy(template);asset['id']=f'8453:0x{index:040x}'
                asset['address']='0x'+f'{index:040x}';asset['symbol']='SAMPLE';asset['name']='Synthetic holding'
                asset['value_usd']=None;asset['price']=None;asset['balance']='1.2345'
                asset['links']=[{'label':'Uniswap','url':'https://example.com/pool/'+str(index)}]
                asset['exit_quote']={'output_amount':'0.1234','output_symbol':'ETH','gas_included':False,'observed_at':'2026-10-05T00:00:00Z'}
                wallet['assets'].append(asset)
            config=settings(scope='portfolio',wallet_tools=True)
            with patch('model.load_state',return_value=(state,stamp,stale)):
                facts=projection(self.root,config)
                self.assertEqual(facts['scope'],'portfolio')
                holdings=facts['wallets'][0]['assets']
                self.assertEqual([a['id'] for a in holdings],[a['id'] for a in wallet['assets'][:12]])
                self.assertEqual(facts['wallets'][0]['asset_count'],800)
                self.assertEqual(facts['wallets'][0]['assets_omitted'],788)
                self.assertEqual(holdings[-1]['balance'],'1.2345')
                self.assertIsNone(holdings[-1]['value_usd']);self.assertIsNone(holdings[-1]['price'])
                self.assertTrue(holdings[-1]['exit_quote_recorded'])
                self.assertNotIn('exit_quote',holdings[-1])
                self.assertLessEqual(len(json.dumps(facts,ensure_ascii=False).encode()),40_000)
                detail=projection(self.root,config,token_id=holdings[-1]['id'])
                self.assertEqual(detail['wallets'][0]['assets'][0]['exit_quote']['output_amount'],'0.1234')
