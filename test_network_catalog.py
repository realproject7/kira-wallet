"""Deployment drift must not disable otherwise unchanged wallet research."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wallet

ADDRESS='0x'+'1'*40
OTHER='0x'+'2'*40


def source(rows):
    return ('  BOND: {\n'+''.join("    ["+name+".id]: '"+address+"',\n" for name,address in rows)+'  },').encode()


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.networks=[{'chain_id':8453,'mintclub_bond_address':ADDRESS},{'chain_id':81457,'mintclub_bond_address':OTHER}]
        self.secrets=patch.object(wallet.h,'secrets',return_value={});self.secrets.start()

    def tearDown(self):self.secrets.stop();self.temp.cleanup()

    def test_removed_entries_require_matching_immutable_provenance(self):
        with patch('urllib.request.urlopen',side_effect=[io.BytesIO(source([('base',ADDRESS),('newChain',ADDRESS)])),io.BytesIO(source([('base',ADDRESS),('blast',OTHER)]))]) as fetch:
            wallet.source_check(self.networks,self.root)
        evidence=json.loads((self.root/'mintclub-support.json').read_text())
        self.assertEqual(evidence['removed_from_current_sdk'],['blast'])
        self.assertEqual(evidence['new_sdk_networks'],['newChain'])
        self.assertEqual(evidence['networks_verified'],2)
        self.assertNotIn('newChain',evidence['bond_deployments'])
        self.assertNotIn('/main/',fetch.call_args_list[1].args[0])

    def test_changed_active_address_does_not_fall_back_to_history(self):
        with patch('urllib.request.urlopen',return_value=io.BytesIO(source([('base',OTHER)]))):
            with self.assertRaises(wallet.NetworkScopeError):wallet.source_check(self.networks[:1],self.root)
        self.assertFalse((self.root/'mintclub-support.json').exists())

    def test_unverified_removed_chain_still_blocks(self):
        with patch('urllib.request.urlopen',side_effect=[io.BytesIO(source([('base',ADDRESS)])),io.BytesIO(source([('base',ADDRESS)]))]):
            with self.assertRaises(wallet.NetworkScopeError):wallet.source_check(self.networks,self.root)

    def test_malformed_or_duplicate_sources_cannot_bypass_validation(self):
        unterminated=("  BOND: {\n    [base.id]: '"+ADDRESS+"',").encode()
        mixed_quotes=("  BOND: {\n    [base.id]: '"+ADDRESS+"\",\n  },").encode()
        for raw in [b'invalid',source([]),source([('base',ADDRESS),('base',OTHER)]),source([('base','malformed')]),unterminated,mixed_quotes]:
            with self.subTest(raw=raw),patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
                with self.assertRaises(wallet.NetworkScopeError):wallet.source_check(self.networks[:1],self.root)
        self.assertFalse((self.root/'mintclub-support.json').exists())

    def test_entry_the_parser_cannot_read_blocks_instead_of_passing_as_removed(self):
        partial=("  BOND: {\n    [base.id]: '"+ADDRESS+"',\n    [blast.id]: unresolvedAddress,\n  },").encode()
        with patch('urllib.request.urlopen',side_effect=[io.BytesIO(partial),io.BytesIO(source([('base',ADDRESS),('blast',OTHER)]))]):
            with self.assertRaises(wallet.NetworkScopeError):wallet.source_check(self.networks,self.root)
        self.assertFalse((self.root/'mintclub-support.json').exists())

    def test_either_quote_style_and_a_space_before_the_colon_are_read(self):
        for quote in ("'",'"'):
            raw=("  BOND: {\n    [base.id] : "+quote+ADDRESS+quote+",\n  },").encode()
            with self.subTest(quote=quote),patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
                wallet.source_check(self.networks[:1],self.root)
                self.assertEqual(json.loads((self.root/'mintclub-support.json').read_text())['bond_deployments'],{'base':ADDRESS})

    def test_extra_sdk_network_does_not_expand_the_selected_catalog(self):
        with patch('urllib.request.urlopen',return_value=io.BytesIO(source([('base',ADDRESS),('extra',OTHER)]))) as fetch:
            wallet.source_check(self.networks[:1],self.root)
        fetch.assert_called_once()
        self.assertEqual(json.loads((self.root/'mintclub-support.json').read_text())['bond_deployments'],{'base':ADDRESS})
