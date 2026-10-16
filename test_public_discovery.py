"""Keyless discovery evidence boundaries, with no live provider calls."""
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import unittest
from unittest.mock import patch
import public_discovery as public
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
        finally:server.shutdown();server.server_close();thread.join()

    def test_default_and_custom_only_preserve_distinct_coverage(self):
        config={'discovery':{'provider':'none','public':True,'explorers':False},
                'rpc':{'mode':'public','allow_public_fallback':True}}
        with tempfile.TemporaryDirectory() as temp,patch.object(wallet,'load_config',return_value=config),patch.object(wallet.h,'secrets',return_value={}):
            row=wallet.discover(ADDRESS,{'chain_id':8453,'environment':'mainnet'},Path(temp))
            self.assertEqual(row['discovery_status'],'unsupported')
            config['rpc']={'mode':'custom','allow_public_fallback':False}
            with patch.object(public,'discover') as fetch:
                row=wallet.discover(ADDRESS,{'chain_id':1,'environment':'mainnet'},Path(temp))
            fetch.assert_not_called();self.assertFalse(row['complete'])


if __name__=='__main__':unittest.main()
