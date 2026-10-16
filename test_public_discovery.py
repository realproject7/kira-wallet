"""Keyless discovery evidence boundaries, with no live provider calls."""
import copy
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import unittest
from unittest.mock import patch
import public_discovery as public
import discovery_state as storage
import wallet

ADDRESS='0x'+'1'*40
TOKEN='0x'+'2'*40


class PublicDiscoveryTests(unittest.TestCase):
    def item(self, **changes):
        return {'chainId':'1','tokenAddress':TOKEN,'tokenQuantity':'123',
                'tokenDecimals':18,'tokenSymbol':'TEST',**changes}

    def test_bounded_pagination_deduplicates_candidates_without_reusing_balances(self):
        responses=[{'items':[self.item()],'link':{'nextToken':'opaque?&'}},
                   {'items':[self.item()],'link':{}}]
        with patch.object(public,'fetch_page') as unused:
            calls=[]
            result=public.discover(ADDRESS,1,fetch=lambda url,timeout: calls.append((url,timeout)) or responses.pop(0))
        unused.assert_not_called()
        self.assertTrue(result['complete']);self.assertEqual(len(result['tokens']),1)
        self.assertIn('next=opaque%3F%26',calls[1][0])
        self.assertNotIn('tokenQuantity',result['tokens'][0])
        self.assertTrue(all(timeout<=8 for _,timeout in calls))

    def test_unsupported_chain_never_probes_provider(self):
        with patch.object(public,'fetch_page') as fetch:
            row=public.discover(ADDRESS,8453,fetch=fetch)
        fetch.assert_not_called();self.assertEqual(row['discovery_status'],'unsupported')

    def test_outage_after_page_keeps_candidates_but_never_claims_complete(self):
        responses=[{'items':[self.item()],'link':{'nextToken':'next'}},{'error':{'code':'429'}}]
        row=public.discover(ADDRESS,1,fetch=lambda *args:responses.pop(0))
        self.assertFalse(row['complete']);self.assertEqual(len(row['tokens']),1)
        self.assertEqual(row['discovery_status'],'provider_error')

    def test_invalid_identity_balance_and_foreign_pagination_are_incomplete(self):
        for token in (self.item(chainId='8453'),self.item(tokenQuantity='NaN'),self.item(tokenAddress='bad')):
            row=public.discover(ADDRESS,1,fetch=lambda *args:{'items':[token],'link':{}})
            self.assertFalse(row['complete']);self.assertEqual(row['tokens'],[])
        calls=[]
        row=public.discover(ADDRESS,1,fetch=lambda url,*args:calls.append(url) or {'items':[],'link':{'next':'https://foreign.test'}})
        self.assertFalse(row['complete']);self.assertEqual(len(calls),1)

    def test_malformed_falsy_cursor_never_claims_checked(self):
        for cursor in (0,False,[],{},''):
            row=public.discover(ADDRESS,1,fetch=lambda *args:{'items':[self.item()],'link':{'nextToken':cursor}})
            self.assertFalse(row['complete']);self.assertEqual(len(row['tokens']),1)

    def test_repeated_cursor_page_and_time_limits_are_partial(self):
        fetch=lambda *args:{'items':[self.item()],'link':{'nextToken':'same'}}
        row=public.discover(ADDRESS,1,fetch=fetch)
        self.assertFalse(row['complete']);self.assertEqual(len(row['pages']),2)
        self.assertFalse(public.discover(ADDRESS,1,fetch=fetch,max_pages=1)['complete'])
        self.assertFalse(public.discover(ADDRESS,1,fetch=fetch,budget=0)['complete'])

    def test_restart_uses_saved_cursor_and_unions_candidates_after_durable_page_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'routescan-1.json'
            save=lambda state:storage.save(path,state,ADDRESS,1,'routescan')
            first=public.discover(ADDRESS,1,fetch=lambda *args:{'items':[self.item()],'link':{'nextToken':'opaque?&'}},max_pages=1,save=save)
            self.assertEqual(first['discovery_status'],'history_pending')
            state=storage.load(path,ADDRESS,1,'routescan');calls=[]
            second=public.discover(ADDRESS,1,state=state,save=save,fetch=lambda url,timeout:calls.append(url) or {'items':[self.item(tokenAddress='0x'+'3'*40)],'link':{}})
            self.assertIn('next=opaque%3F%26',calls[0]);self.assertTrue(second['complete'])
            self.assertEqual(len(second['tokens']),2)
            self.assertEqual(second['pagination']['pages_checked'],2)
            self.assertTrue(storage.load(path,ADDRESS,1,'routescan')['complete'])
            self.assertNotIn('tokenQuantity',str(second['tokens']))

    def test_loop_detection_and_quota_backoff_survive_restart(self):
        saved=[]
        save=lambda state:saved.append(copy.deepcopy(state))
        public.discover(ADDRESS,1,fetch=lambda *args:{'items':[self.item()],'link':{'nextToken':'loop'}},max_pages=1,save=save)
        checkpoint=copy.deepcopy(saved[-1])
        row=public.discover(ADDRESS,1,state=checkpoint,save=save,fetch=lambda *args:{'items':[],'link':{'nextToken':'loop'}})
        self.assertFalse(row['complete']);self.assertEqual(saved[-1]['page'],2)
        with patch.object(public.time,'time',return_value=1000):
            row=public.discover(ADDRESS,1,state=checkpoint,save=save,fetch=lambda *args:{'error':{'http_status':429,'retry_after':120}})
        self.assertEqual(row['discovery_status'],'throttled')
        self.assertEqual(saved[-1]['retry_not_before'],1120)
        with patch.object(public.time,'time',return_value=1119),patch.object(public,'fetch_page') as fetch:
            row=public.discover(ADDRESS,1,state=saved[-1],fetch=fetch)
        fetch.assert_not_called();self.assertFalse(row['complete']);self.assertEqual(len(row['tokens']),1)
        with patch.object(public.time,'time',return_value=1121):
            row=public.discover(ADDRESS,1,state=saved[-1],save=save,fetch=lambda *args:{'items':[],'link':{}})
        self.assertTrue(row['complete'])

    def test_malformed_saved_frontiers_are_preserved_without_provider_requests(self):
        saved=[]
        public.discover(ADDRESS,1,budget=0,save=lambda state:saved.append(copy.deepcopy(state)))
        for changes in ({'started_at':None},{'retry_not_before':'later'},{'page':2,'cursor':None},{'wallet':'wrong'}):
            with patch.object(public,'fetch_page') as fetch,patch.object(storage,'save') as save:
                row=public.discover(ADDRESS,1,state={**saved[-1],**changes},fetch=fetch,save=save)
            fetch.assert_not_called();save.assert_not_called()
            self.assertEqual(row['discovery_status'],'checkpoint_error');self.assertFalse(row['complete'])

    def test_trickling_response_cannot_hold_initial_report_past_deadline(self):
        class Slow(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                body=b'{"items":[],"link":{}}'
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:
                    for char in body:self.wfile.write(bytes([char]));self.wfile.flush();time.sleep(.04)
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Slow)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(public,'_last',0):
                start=time.monotonic();row=public.fetch_page('http://127.0.0.1:'+str(server.server_port),.4)
            self.assertLess(time.monotonic()-start,1);self.assertIn('error',row)
            start=time.monotonic();row=wallet.fetch('http://127.0.0.1:'+str(server.server_port),deadline=time.monotonic()+.4)
            self.assertLess(time.monotonic()-start,1);self.assertTrue(row.get('research_pending'))
        finally:server.shutdown();server.server_close();thread.join()

    def test_default_and_custom_only_preserve_distinct_coverage(self):
        config={'discovery':{'provider':'none','public':True,'explorers':False},
                'rpc':{'mode':'public','allow_public_fallback':True}}
        with tempfile.TemporaryDirectory() as temp,patch.object(wallet,'load_config',return_value=config),patch.object(wallet.h,'secrets',return_value={}),patch('transfer_discovery.discover',return_value={'source':'keyless','complete':False,'tokens':[],'native':[],'pages':[],'discovery_status':'history_pending'}) as transfer:
            row=wallet.discover(ADDRESS,{'chain_id':8453,'environment':'mainnet'},Path(temp))
            self.assertEqual(row['discovery_status'],'history_pending');transfer.assert_called_once()
            config['rpc']={'mode':'custom','allow_public_fallback':False}
            with patch.object(public,'discover') as fetch:
                row=wallet.discover(ADDRESS,{'chain_id':1,'environment':'mainnet'},Path(temp))
            fetch.assert_not_called();self.assertFalse(row['complete'])

    def test_overlapping_sources_union_identities_without_erasing_unfinished_coverage(self):
        common={'chain_id':1,'address':TOKEN,'prices':[]}
        transfer={'source':'etherscan','provider':'etherscan_keyless','complete':False,'tokens':[common],
                  'pages':[{'page':1}],'discovery_status':'history_pending'}
        routescan={'source':'routescan','provider':'routescan','complete':True,
                   'tokens':[{**common,'suspicious_zero_check':True},{**common,'address':'0x'+'4'*40}],
                   'pages':[{'page':1}],'discovery_status':'checked'}
        with tempfile.TemporaryDirectory() as temp,patch.object(wallet,'ROOT',Path(temp)),patch('transfer_discovery.discover',return_value=transfer) as history,patch.object(public,'discover',return_value=routescan) as holdings:
            row=wallet.free_sources(ADDRESS,1,60,continue_only=True)
        self.assertEqual(len(row['tokens']),2);self.assertTrue(row['tokens'][0]['suspicious_zero_check'])
        self.assertFalse(row['complete']);self.assertEqual(row['discovery_status'],'history_pending')
        self.assertEqual(row['provider'],'multiple');self.assertEqual(len(row['sources']),2)
        self.assertTrue(row['sources'][1]['complete']);self.assertFalse(row['complete_inventory_guaranteed'])
        self.assertEqual(history.call_args.kwargs['budget'],30);self.assertEqual(holdings.call_args.kwargs['budget'],30)
        self.assertTrue(history.call_args.kwargs['continue_only'])

    def test_admitted_testnet_route_and_corrupt_source_do_not_silence_other_sources(self):
        import transfer_discovery
        for cid in (130,33139,4663,11155111,84532,43113):self.assertIn(cid,transfer_discovery.CHAINS)
        with tempfile.TemporaryDirectory() as temp,patch.object(wallet,'ROOT',Path(temp)),patch.object(storage,'load',side_effect=[ValueError('synthetic corrupt state'),None]),patch('transfer_discovery.discover') as history,patch.object(public,'discover',return_value={'source':'routescan','provider':'routescan','complete':True,'tokens':[{'chain_id':1,'address':TOKEN}], 'pages':[],'discovery_status':'checked'}):
            row=wallet.free_sources(ADDRESS,1,60)
        history.assert_not_called();self.assertEqual(len(row['tokens']),1)
        self.assertFalse(row['complete']);self.assertEqual(row['sources'][0]['discovery_status'],'checkpoint_error')


if __name__=='__main__':unittest.main()
