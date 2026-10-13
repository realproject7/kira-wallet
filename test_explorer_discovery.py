"""Hosted explorer continuation and identity checks without network access."""
import copy
import unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import explorer_discovery as explorer
import wallet

ADDRESS='0x'+'1'*40
TOKEN='0x'+'2'*40


class ExplorerDiscoveryTests(unittest.TestCase):
    def item(self,**changes):
        return {'token':{'address_hash':TOKEN,'type':'ERC-20','decimals':'18','name':'Test','symbol':'T'},'value':'123',**changes}

    def test_resume_uses_query_cursor_on_the_admitted_host_and_preserves_candidates(self):
        saved=[];urls=[]
        cursor={'fiat_value':'0.12','value':'123','id':17}
        row=explorer.discover(ADDRESS,177,max_pages=1,save=lambda s:saved.append(copy.deepcopy(s)),
            fetch=lambda url,timeout:urls.append(url) or {'items':[self.item()],'next_page_params':cursor})
        self.assertFalse(row['complete']);self.assertEqual(row['discovery_status'],'history_pending')
        self.assertEqual(row['tokens'][0]['decimals'],18)
        row=explorer.discover(ADDRESS,177,state=saved[-1],continue_only=True,
            fetch=lambda url,timeout:urls.append(url) or {'items':[],'next_page_params':None})
        self.assertTrue(row['complete']);self.assertEqual(len(row['tokens']),1)
        self.assertTrue(urls[1].startswith('https://explorer.hsk.xyz/api/v2/addresses/'))
        self.assertEqual(parse_qs(urlsplit(urls[1]).query),{'fiat_value':['0.12'],'value':['123'],'id':['17'],'type':['ERC-20']})
        self.assertNotIn('value',row['tokens'][0]);self.assertFalse(row['complete_inventory_guaranteed'])

    def test_invalid_identity_and_cursor_do_not_claim_page_completion(self):
        for page in ({'items':[self.item(token={'type':'ERC-721','address_hash':TOKEN})],'next_page_params':None},
                     {'items':[self.item()],'next_page_params':{}},
                     {'items':[self.item()],'next_page_params':{'type':'ERC-721'}},
                     {'items':[self.item()],'next_page_params':{'next':{'url':'https://foreign.example'}}},
                     {'items':[self.item()]}):
            row=explorer.discover(ADDRESS,109,fetch=lambda *args:page)
            self.assertFalse(row['complete']);self.assertEqual(row['discovery_status'],'provider_error')

    def test_opt_out_and_unadmitted_hosts_are_not_probed(self):
        with patch.object(explorer,'discover') as fetch:
            row=wallet.free_sources(ADDRESS,109,25,explorers=False)
        fetch.assert_not_called();self.assertEqual(row['discovery_status'],'unsupported')
        with patch.object(explorer,'fetch_page') as fetch:
            row=explorer.discover(ADDRESS,5112,fetch=fetch)
        fetch.assert_not_called();self.assertEqual(row['discovery_status'],'unsupported')


if __name__=='__main__':unittest.main()
