"""A token list can be read through one platform, the way the allocation counts it."""
import unittest
from kira_jobs import JobError
from kira_state import filter_assets, platform_rows
from positions import asset_platform, receipt_platforms

RECEIPT = '0x' + '1' * 40
CURVE = '0x' + '2' * 40
PLAIN = '0x' + '3' * 40


def asset(address, value, **extra):
    return {'id': '8453:' + address, 'chain_id': 8453, 'address': address, 'environment': 'mainnet', 'symbol': address[2:5],
            'value_usd': value, 'included_in_totals': True, 'portfolio_status': 'portfolio', **extra}


def wallet():
    return {'key': '0x' + 'a' * 40, 'assets': [asset(RECEIPT, 5, sell_out={'value_usd': 4}), asset(CURVE, 3, curve_reserve={'amount': '1', 'symbol': 'HUNT'}, sell_out={'value_usd': 2}), asset(PLAIN, 9)],
            'positions': [{'id': 'lp', 'platform': 'lptoken', 'chain_id': 8453, 'receipt': {'address': RECEIPT.upper().replace('0X', '0x'), 'custody': 'wallet'}, 'assets': []},
                          {'id': 'staked', 'platform': 'mintclub-staking', 'chain_id': 8453, 'receipt': {'address': PLAIN, 'custody': 'mintclub-staking'}, 'assets': []}]}


class PlatformFilterTests(unittest.TestCase):
    def test_each_token_has_the_allocation_group(self):
        w = wallet(); receipts = receipt_platforms([w])
        self.assertEqual(receipts, {'8453:' + RECEIPT: 'lptoken'})
        self.assertEqual([asset_platform(a, receipts) for a in w['assets']], ['lptoken', 'mintclub', 'wallet'])

    def test_a_platform_keeps_only_its_tokens(self):
        w = wallet(); receipts = receipt_platforms([w])
        pick = lambda p: [a['symbol'] for a in filter_assets(w['assets'], platform=p, platforms=receipts)]
        self.assertEqual(pick('lptoken'), ['111'])
        self.assertEqual(pick('mintclub'), ['222'])
        self.assertEqual(pick('wallet'), ['333'])
        self.assertEqual(pick('aeromax'), [])
        self.assertEqual(len(filter_assets(w['assets'], platforms=receipts)), 3)
        with self.assertRaises(JobError):filter_assets(w['assets'], platform='unknown', platforms=receipts)

    def test_rows_name_their_platform_and_a_view_sums_its_sell_out(self):
        w = wallet(); receipts = receipt_platforms([w])
        result = platform_rows({'assets': list(w['assets'])}, [w], receipts, 'mintclub')
        self.assertEqual([a['platform'] for a in result['assets']], ['lptoken', 'mintclub', 'wallet'])
        self.assertEqual(result['platform_sell_out_summary']['value_usd'], 2)
        self.assertEqual(result['platform_sell_out_summary']['position_count'], 1)
        self.assertNotIn('platform_sell_out_summary', platform_rows({'assets': []}, [w], receipts))


if __name__ == '__main__':
    unittest.main()
