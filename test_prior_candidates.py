"""Positive identities remain candidates across stage publication, not saved balances."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import wallet
from kira_jobs import atomic
class PriorTests(unittest.TestCase):
    def test_upgrade_bootstraps_own_positive_history_once_without_balances(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(wallet,'ROOT',Path(tmp).resolve()):
            root=Path(tmp);address='0x'+'1'*40;token='0x'+'2'*40;foreign='0x'+'3'*40
            entry={'address_key':address,'latest_snapshot':{'result':'snapshots/basic/results.json'}}
            atomic(root/entry['latest_snapshot']['result'],{'wallet_address':address,'tokens':[]})
            history=root/'snapshots/old/results.json'
            atomic(history,{'wallet_address':address,'tokens':[
                {'chain_id':7777777,'token_type':'ERC20','token_address':token,'wallet_balance_raw':'1234567'},
                {'chain_id':1,'token_type':'ERC20','token_address':foreign,'wallet_balance_raw':'0'}]})
            atomic(root/'snapshots/foreign/results.json',{'wallet_address':foreign,'tokens':[
                {'chain_id':1,'token_type':'ERC20','token_address':foreign,'wallet_balance_raw':'999'}]})
            atomic(root/'wallets.json',{'research_runs':[
                {'address_key':address,'snapshot':'snapshots/old'},
                {'address_key':address,'snapshot':'snapshots/foreign'},
                {'address_key':foreign,'snapshot':'snapshots/foreign'},
                {'address_key':address,'snapshot':'../outside'}]})
            rows=wallet.prior_candidates(entry)
            self.assertEqual([(r['chain_id'],r['address']) for r in rows],[(7777777,token)])
            self.assertNotIn('1234567',json.dumps(rows));self.assertEqual(rows[0]['prices'],[])
            history.write_text('Historical file must not need another read')
            self.assertEqual(wallet.prior_candidates(entry),rows)
            other=wallet.prior_candidates({'address_key':foreign})
            self.assertEqual([(r['chain_id'],r['address']) for r in other],[(1,foreign)])
            self.assertNotIn(token,json.dumps(other))

    def test_baseline_and_failed_reread_cannot_erase_other_chain_identity(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(wallet,'ROOT',Path(tmp).resolve()):
            address='0x'+'1'*40;token='0x'+'2'*40;entry={'address_key':address,'latest_snapshot':{'result':'snapshots/full/results.json'}}
            atomic(Path(tmp)/entry['latest_snapshot']['result'],{'wallet_address':address,'tokens':[{'chain_id':56,'token_type':'ERC20','token_address':token,'wallet_balance':'99'}]})
            candidates=wallet.prior_candidates(entry)
            self.assertEqual(candidates[0]['address'],token);self.assertNotIn('99',json.dumps(candidates))
            entry['latest_snapshot']['result']='snapshots/baseline/results.json'
            atomic(Path(tmp)/entry['latest_snapshot']['result'],{'wallet_address':address,'tokens':[]})
            self.assertEqual(wallet.prior_candidates(entry),candidates)
            entry.pop('latest_snapshot');self.assertEqual(wallet.prior_candidates(entry),candidates)
            self.assertEqual(wallet.prior_candidates({'address_key':'0x'+'3'*40}),[])
    def test_fresh_metadata_and_prices_survive_prior_verification_hints(self):
        token='0x'+'2'*40
        prior=[{'chain_id':8453,'address':token,'suspicious_zero_check':True,'prices':[]}]
        fresh=[{'chain_id':8453,'address':token,'name':'Fresh name','decimals':6,'prices':[{'value':'1'}]}]
        merged=wallet.merge_candidates(prior,[],fresh)[0]
        self.assertEqual(merged['name'],'Fresh name');self.assertEqual(merged['prices'],fresh[0]['prices']);self.assertTrue(merged['suspicious_zero_check'])
    def test_mintclub_id0_identity_survives_without_reusing_balance_or_admitting_other_nfts(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(wallet,'ROOT',Path(tmp).resolve()):
            address='0x'+'1'*40;token='0x'+'2'*40;entry={'address_key':address,'latest_snapshot':{'result':'snapshots/full/results.json'}}
            atomic(Path(tmp)/entry['latest_snapshot']['result'],{'wallet_address':address,'tokens':[
                {'chain_id':8453,'token_type':'ERC1155','token_address':token,'token_id':'0','wallet_balance_raw':'999','mintclub':{'funded':True}},
                {'chain_id':8453,'token_type':'ERC1155','token_address':'0x'+'3'*40,'token_id':'7','mintclub':{'funded':True}},
                {'chain_id':8453,'token_type':'ERC1155','token_address':'0x'+'4'*40,'token_id':'0','mintclub':None},
                {'chain_id':8453,'token_type':'ERC1155','token_address':'0x'+'5'*40,'token_id':'0','mintclub':None,'mintclub_membership_status':'verified','mintclub_error':{'message':'Details unavailable'}}]})
            candidates=wallet.prior_candidates(entry)
            self.assertEqual(len(candidates),2);self.assertEqual(candidates[0]['token_id'],'0')
            self.assertTrue(candidates[0]['requires_mintclub_membership']);self.assertNotIn('999',json.dumps(candidates))
            entry.pop('latest_snapshot');self.assertEqual(wallet.prior_candidates(entry),candidates)
if __name__=='__main__':unittest.main()
