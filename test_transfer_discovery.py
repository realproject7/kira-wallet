"""Candidate admission, fixed history windows and bounded provider failures."""
import json
import unittest
from unittest.mock import patch
import transfer_discovery as discovery

WALLET='0x'+'1'*40
TOKEN='0x'+'2'*40

def result(data, **changes):
    return {'jsonrpc':'2.0','id':1,'result':{'content':[{'type':'text','text':json.dumps({'ok':True,'status':'1','result':data})}],**changes}}


class TransferTests(unittest.TestCase):
    def transfer(self,**changes):return {'contractAddress':TOKEN,'blockNumber':'9','from':WALLET,'to':'0x'+'3'*40,'value':'999999',**changes}
    def request(self, responses, calls):
        def fetch(body,timeout):calls.append(body['params']);return result(responses.pop(0))
        return fetch
    def test_partial_page_keeps_fixed_window_and_resumes_without_reusing_balances(self):
        saved=[];calls=[]
        row=discovery.discover(WALLET,8453,request=self.request(['10',[self.transfer()]*100],calls),save=lambda s:saved.append(json.loads(json.dumps(s))),max_pages=1)
        self.assertFalse(row['complete']);self.assertEqual(row['discovery_status'],'history_pending')
        self.assertEqual(row['tokens'],[{'chain_id':8453,'address':TOKEN,'prices':[]}])
        self.assertEqual(saved[-1]['page'],2);self.assertEqual(saved[-1]['endblock'],10)
        row=discovery.discover(WALLET,8453,state=saved[-1],request=self.request(['10',[]],calls))
        self.assertTrue(row['complete']);self.assertEqual(calls[-1]['arguments']['page'],2);self.assertEqual(calls[-1]['arguments']['endblock'],10)
    def test_new_window_keeps_prior_identities_and_reconciles_bounded_reorg_overlap(self):
        calls=[];state={'schema_version':1,'wallet':WALLET,'chain_id':8453,'startblock':0,'endblock':10,'page':2,'contracts':[TOKEN],'complete':True}
        row=discovery.discover(WALLET,8453,state=state,request=self.request(['20',[]],calls))
        self.assertEqual(calls[-1]['arguments']['startblock'],0);self.assertEqual(len(row['tokens']),1);self.assertTrue(row['complete'])
        state.update(endblock=10000,startblock=0)
        replacement='0x'+'5'*40
        row=discovery.discover(WALLET,8453,state=state,request=self.request(['10010',[self.transfer(contractAddress=replacement,blockNumber='9999')]],calls))
        self.assertEqual(calls[-1]['arguments']['startblock'],7952)
        self.assertEqual({t['address'] for t in row['tokens']},{TOKEN,replacement})
    def test_new_receipts_are_detected_while_older_history_still_needs_pages(self):
        state={'schema_version':1,'wallet':WALLET,'chain_id':8453,'startblock':0,'endblock':10,'page':2,'contracts':[TOKEN],'complete':False,'last_block':9}
        newer='0x'+'4'*40;calls=[];saved=[]
        row=discovery.discover(WALLET,8453,state=state,request=self.request(['20',[self.transfer(contractAddress=newer,blockNumber='19')],[]],calls),save=lambda s:saved.append(dict(s)))
        self.assertEqual({t['address'] for t in row['tokens']},{TOKEN,newer});self.assertTrue(row['complete'])
        self.assertEqual(calls[1]['arguments']['startblock'],11);self.assertEqual(calls[2]['arguments']['endblock'],10)
        self.assertEqual(saved[-1]['page'],3)
    def test_invalid_page_never_advances_frontier_or_claims_zero_holdings(self):
        for transfer in (self.transfer(contractAddress='bad'),self.transfer(blockNumber='11'),self.transfer(**{'from':'foreign','to':'foreign'})):
            saved=[];row=discovery.discover(WALLET,8453,request=self.request(['10',[transfer]],[]),save=lambda s:saved.append(dict(s)))
            self.assertEqual(row['discovery_status'],'provider_error');self.assertFalse(row['complete']);self.assertEqual(saved[-1]['page'],1)
    def test_rpc_and_tool_errors_repeated_pages_and_limits_remain_partial(self):
        for content in ([None],[[]],[{'type':'text','text':None}]):
            row=discovery.discover(WALLET,8453,request=lambda *args:{'id':1,'result':{'content':content}})
            self.assertEqual(row['discovery_status'],'provider_error')
        response=self.request(['10',[self.transfer()]*100,[self.transfer()]*100],[])
        row=discovery.discover(WALLET,8453,request=response)
        self.assertFalse(row['complete']);self.assertEqual(len(row['tokens']),1);self.assertEqual(row['history_window']['page'],2)
        row=discovery.discover(WALLET,8453,request=lambda *args:result([],isError=True))
        self.assertEqual(row['discovery_status'],'provider_error')
        calls=[];saved=[]
        row=discovery.discover(WALLET,8453,request=self.request(['100',[self.transfer(blockNumber='80')]*100,[self.transfer(blockNumber='90')]],calls),save=lambda s:saved.append(dict(s)))
        self.assertEqual(row['discovery_status'],'provider_error');self.assertFalse(row['complete']);self.assertEqual(saved[-1]['page'],2)
        row=discovery.discover(WALLET,8453,request=lambda *args:{'error':{'http_status':429}})
        self.assertEqual(row['discovery_status'],'provider_error')
    def test_unsupported_wrong_wallet_cache_and_zero_budget_cannot_claim_complete(self):
        with patch.object(discovery,'fetch') as fetch:
            row=discovery.discover(WALLET,5112,request=fetch)
        fetch.assert_not_called();self.assertEqual(row['discovery_status'],'unsupported')
        state={'schema_version':1,'wallet':'wrong','chain_id':8453,'startblock':0,'endblock':10,'page':2,'contracts':[TOKEN],'complete':True}
        row=discovery.discover(WALLET,8453,state=state,request=self.request(['10',[]],[]));self.assertEqual(row['tokens'],[])
        self.assertFalse(discovery.discover(WALLET,8453,budget=0,request=lambda *args:{'error':{}})['complete'])
    def test_initialized_session_is_memory_only_and_throttle_pauses_lane(self):
        session='session-123'
        initialize={'http_status':200,'session':session,'body':json.dumps({'result':{'protocolVersion':'2025-03-26'}})}
        transport=[initialize,{'http_status':202,'body':''},{'error':{'http_status':429,'retry_after':120}}]
        with patch.object(discovery,'_session',None),patch.object(discovery,'_next',0),patch.object(discovery,'_cooldown',0),patch.object(discovery,'fetch_bounded',side_effect=transport) as network:
            row=discovery.fetch({'method':'tools/call'},10)
            self.assertEqual(row['error']['http_status'],429)
            self.assertEqual(discovery.fetch({'method':'tools/call'},10)['error']['code'],'throttled')
            self.assertEqual(network.call_count,3)
            self.assertNotIn(session,json.dumps(row));self.assertEqual(network.call_args.kwargs['headers']['Mcp-Session-Id'],session)
        for body in ('[]','null','{"result":null}'):
            with patch.object(discovery,'_session',None),patch.object(discovery,'_next',0),patch.object(discovery,'_cooldown',0),patch.object(discovery,'fetch_bounded',return_value={'session':session,'body':body}):
                self.assertEqual(discovery.fetch({},1)['error']['code'],'initialize_failed')
        for responses in ([{'error':{'http_status':429,'retry_after':120}}],[initialize,{'error':{'http_status':429,'retry_after':120}}]):
            with patch.object(discovery,'_session',None),patch.object(discovery,'_next',0),patch.object(discovery,'_cooldown',0),patch.object(discovery,'fetch_bounded',side_effect=responses) as network:
                discovery.fetch({},10);calls=network.call_count
                self.assertEqual(discovery.fetch({},10)['error']['code'],'throttled');self.assertEqual(network.call_count,calls)


if __name__=='__main__':unittest.main()
