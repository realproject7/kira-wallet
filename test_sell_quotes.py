from copy import deepcopy
from datetime import datetime, timezone
import tempfile
import unittest
from unittest.mock import patch
from sell_quotes import candidates, enrich, classify_with_cache

WALLET = '0x'+'9'*40
TOKEN = '0x'+'1'*40
OUTPUT = '0x4200000000000000000000000000000000000006'
POOL = '0x'+'3'*40
HASH = '0x'+'a'*64
NOW = 1792368000
STAMP = datetime.fromtimestamp(NOW, timezone.utc).isoformat()


def fixture():
    token = {'chain_id':8453, 'token_address':TOKEN, 'token_type':'ERC20', 'wallet_balance':'100',
             'wallet_balance_raw':'100', 'balance_block_number':'7', 'balance_block_hash':HASH, 'dex_pools':[]}
    pool = {'pool':POOL, 'venue':'aerodrome', 'version_labels':[], 'source_url':'https://example.com/pool',
            'paired_tokens':[{'address':TOKEN},{'address':OUTPUT}], 'reported_liquidity':{'usd':10000}}
    snapshot = {'wallet_address':WALLET, 'tokens':[token], 'coverage':[{'chain_id':8453,'environment':'mainnet'}]}
    price = {'chain_id':8453,'address':OUTPUT,'usd':'2000','basis':'DEX market','liquidity_usd':1000000,
             'quality':'estimated','source':'https://example.com/weth','observed_at':STAMP}
    market = {'tokens':[price], 'markets':[{'id':'8453:'+TOKEN,'pools':[pool]}]}
    quote = {'status':'quoted','kind':'aerodrome_pool','input_address':TOKEN,'input_amount_raw':'100','holding_amount_raw':'100',
             'pool':POOL,'output_amount':'2','output_address':OUTPUT,'output_symbol':'WETH','partial_input':False,
             'block_number':'9','block_hash':HASH,'observed_at':STAMP,
             'gas_included':False,'route_fees_included':True,'price_impact_included':True}
    row = {'chain_id':8453,'address':TOKEN,'pool':POOL,'wallet_balance_raw':'100','status':'quoted','checked_at':STAMP,
           'balance_block_number':'9','balance_block_hash':HASH,'balance_observed_at':STAMP,'quote':quote}
    return snapshot, market, row


class SellQuoteTests(unittest.TestCase):
    def test_supported_terminal_pools_only_not_v4_nonterminal_or_wrong_identity(self):
        snapshot, market, row = fixture()
        pools = market['markets'][0]['pools']
        pools.insert(0,{**pools[0],'pool':'0x'+'4'*64,'venue':'uniswap','version_labels':['v4'],'reported_liquidity':{'usd':1000000}})
        self.assertEqual(candidates(snapshot,market)[0]['dex_pools'][0]['pool'],POOL)
        for change in ({'environment':'testnet'},{'environment':'unknown'}):
            snapshot['coverage'][0].update(change);self.assertEqual(candidates(snapshot,market),[])
        snapshot['coverage'][0]['environment']='mainnet'
        for field in ('balance_evidence_retained','metadata_evidence_retained'):
            snapshot['tokens'][0][field]=True;self.assertEqual(candidates(snapshot,market),[]);snapshot['tokens'][0].pop(field)
        for change in ({'retained_from_previous':True},{'quality':'unreliable'},{'liquidity_usd':1},{'basis':'Curve spot'}):
            altered=deepcopy(market);altered['tokens'][0].update(change);self.assertEqual(candidates(snapshot,altered),[])
        pools[1]['paired_tokens']=[{'address':TOKEN},{'address':'0x'+'5'*40}]
        self.assertEqual(candidates(snapshot,market),[])

    def test_fresh_same_quantity_cache_has_zero_provider_work_and_expiry_is_bounded(self):
        snapshot, market, row = fixture()
        market['sell_quotes']={'version':1,'wallet_address':WALLET,'records':[row]}
        original=deepcopy(snapshot)
        def fail(*args):self.fail('A fresh cached quote must not contact a provider')
        with tempfile.TemporaryDirectory() as folder, patch('kira_config.require_alchemy'):
            cached=enrich(snapshot,market,folder,now=NOW+599,run=fail)
            self.assertEqual(cached['sell_quotes']['attempted'],0)
            calls=[]
            def run(payload):calls.append(payload);return {'status':'checked','records':[row]}
            enrich(snapshot,market,folder,now=NOW+600,run=run)
            self.assertEqual(len(calls),1);self.assertEqual(calls[0]['budget_ms'],20000)
            snapshot['tokens'][0]['wallet_balance_raw']='101'
            changed=enrich(snapshot,market,folder,now=NOW+1,run=lambda p:{'status':'partial','records':[]})
            self.assertEqual(changed['sell_quotes']['records'][0]['status'],'unknown')
        self.assertEqual(snapshot['tokens'][0]['balance_block_number'],original['tokens'][0]['balance_block_number'])

    def test_cap_and_negative_cache_prevent_refresh_bursts(self):
        snapshot,market,row=fixture()
        template=deepcopy(snapshot['tokens'][0]);pool=deepcopy(market['markets'][0]['pools'][0])
        snapshot['tokens']=[];market['markets']=[]
        for i in range(20):
            address='0x'+format(i+1,'040x')
            snapshot['tokens'].append({**template,'token_address':address,'wallet_balance':str(i+1)})
            market['tokens'].append({'chain_id':8453,'address':address,'usd':'1'})
            market['markets'].append({'id':'8453:'+address,'pools':[{**pool,'paired_tokens':[{'address':address},{'address':OUTPUT}]}]})
        seen=[]
        with tempfile.TemporaryDirectory() as folder, patch('kira_config.require_alchemy'):
            result=enrich(snapshot,market,folder,now=NOW,run=lambda p:seen.append(p) or {'status':'partial','records':[]})
            self.assertEqual(len(seen[0]['tokens']),12);self.assertEqual(result['sell_quotes']['deferred'],8)
            self.assertEqual(seen[0]['tokens'][0]['token_address'],snapshot['tokens'][-1]['token_address'])
            # A failure cooldown also avoids retrying those same 12 tokens.
            enrich(snapshot,result,folder,now=NOW+1,run=lambda p:seen.append(p) or {'status':'partial','records':[]})
            self.assertEqual(len(seen[1]['tokens']),8)

    def test_independent_balance_pin_projects_full_quote_without_mutating_snapshot(self):
        snapshot,market,row=fixture();token=snapshot['tokens'][0]
        market['sell_quotes']={'version':1,'wallet_address':WALLET,'records':[row]}
        before=deepcopy(snapshot)
        result=classify_with_cache(token,market,wallet_address=WALLET)
        self.assertEqual(result['quotes'][0]['quoted_output_usd'],'4000')
        self.assertEqual(result['quotes'][0]['block_number'],'9')
        self.assertEqual(result['quotes'][0]['output_symbol'],'WETH')
        self.assertEqual(snapshot,before)
        for path,value in [('wallet_balance_raw','99'),('balance_block_hash','0x'+'b'*64),('balance_block_number','8'),('balance_observed_at',None)]:
            wrong=deepcopy(market);wrong['sell_quotes']['records'][0][path]=value
            self.assertFalse(classify_with_cache(token,wrong,wallet_address=WALLET)['quotes'])
        for field,value in [('partial_input',True),('input_amount_raw','50'),('input_address',OUTPUT),('pool',OUTPUT),('gas_included',True)]:
            wrong=deepcopy(market);wrong['sell_quotes']['records'][0]['quote'][field]=value
            self.assertFalse(classify_with_cache(token,wrong,wallet_address=WALLET)['quotes'])
        self.assertFalse(classify_with_cache(token,market,wallet_address=TOKEN)['quotes'])
        self.assertFalse(classify_with_cache(token,market,wallet_address=WALLET,environment='testnet')['quotes'])

if __name__=='__main__':unittest.main()
