"""Positive identities remain candidates across stage publication, not saved balances."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import wallet
from kira_jobs import atomic
class PriorTests(unittest.TestCase):
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
if __name__=='__main__':unittest.main()
