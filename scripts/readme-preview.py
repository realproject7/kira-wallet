"""Render README captures in a disposable, offline portfolio.

Uses only public fixture identities and handwritten scenario answers. It never
reads an operator workspace, invokes a model CLI, queues research, or creates keys.
The actual viewer UI and snapshot projection render the screenshots unchanged.
"""
import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]

USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
WETH = '0x4200000000000000000000000000000000000006'
USDB = '0x4300000000000000000000000000000000000003'
BLAST = '0xb1a5700fa2358173fe465e6ea4ff52e36e88e2ad'
SIGNET = '0xdf2b673ec06d210c8a8be89441f8de60b5c679c9'
STAMP = '2026-10-05T00:00:00Z'


def records(root, atomic):
    public = json.loads((PROJECT / 'docs/screenshots/kira-readme-sources.json').read_text())
    wallets = []
    pools = []
    for i, (venue, liquidity) in enumerate([('uniswap-v3', 2450000), ('aerodrome', 840000), ('uniswap-v3', 360000), ('aerodrome', 190000)]):
        pools.append({'venue': venue, 'pool': public['pool_addresses'][i],
                      'paired_tokens': [{'symbol': 'USDC', 'address': USDC}, {'symbol': 'WETH', 'address': WETH}],
                      'reported_liquidity': {'usd': liquidity}, 'reported_price_usd': '1',
                      'source_url': f'https://example.com/markets/usdc/{i + 1}', 'observed_at': STAMP})
    for i, (name, address) in enumerate(zip(('Daily', 'Savings'), public['wallet_addresses'])):
        folder = f'snapshots/{name.lower()}/initial'
        balances = ('0.4', '2.4', '0.035') if i == 0 else ('0.25', '0.12', '0')
        coverage = [{'chain_id': chain, 'name': label, 'environment': 'mainnet', 'native_symbol': 'ETH',
                     'native_balance': balance, 'native_observed_at': STAMP,
                     'general_erc20_discovery': 'incomplete' if chain == 81457 else 'indexer_checked',
                     'rpc_status': 'available'} for chain, label, balance in zip((1, 8453, 81457), ('Ethereum', 'Base', 'Blast'), balances)]
        token_rows = [(8453, USDC, 'USDC', 'USD Coin', '3400' if i == 0 else '1000', 1, pools)]
        if i == 0:
            token_rows += [(81457, USDB, 'USDB', 'USDB', '900', 1, []),
                           (81457, BLAST, 'BLAST', 'Blast', '50000', .006, []),
                           (8453, SIGNET, 'SIGNET', 'Signet', '650', None, [])]
        tokens, prices = [], []
        for chain, contract, symbol, label, balance, price, markets in token_rows:
            tokens.append({'chain_id': chain, 'network': 'base' if chain == 8453 else 'blast',
                           'token_address': contract, 'token_type': 'ERC20', 'symbol': symbol,
                           'name': label, 'wallet_balance': balance, 'decimals': 18,
                           'mintclub': None, 'dex_pools': markets, 'balance_observed_at': STAMP})
            if price is not None:
                # Bind the saved USDC price to its existing handwritten pool so
                # current liquidity validation can use that same demo evidence.
                prices.append({'chain_id': chain, 'address': contract, 'usd': price,
                               'basis': 'DEX market', 'quality': 'estimated', 'observed_at': STAMP,
                               **({'source': markets[0]['source_url']} if markets else {})})
        atomic(root / folder / 'results.json', {'schema_version': 1, 'wallet_address': address,
               'tags': [name], 'compiled_at': STAMP, 'status': 'completed_with_coverage_gaps',
               'counts': {}, 'coverage': coverage, 'tokens': tokens})
        atomic(root / folder / 'market-prices.json', {'observed_at': STAMP,
               'native_usd': {'ETH': {'usd': 2700, 'basis': 'Market index', 'observed_at': STAMP}}, 'tokens': prices})
        wallets.append({'address': address, 'address_key': address.lower(), 'tags': [name],
                        'latest_snapshot': {'directory': folder, 'result': folder + '/results.json'}})
    atomic(root / 'wallets.json', {'schema_version': 1, 'wallets': wallets})
    provenance = json.loads((PROJECT / 'site/assets/token-artwork-sources.json').read_text())
    images = {Path(row['asset']).name: row.get('source') or row.get('image')
              for row in provenance['tokens'] + provenance['existing_assets']}
    atomic(root / 'cache/token-images.json', {'tokens': {
        f'{chain}:{address}': {'image_url': images[name + '.png']}
        for chain, address, name in [(8453, USDC, 'usdc'), (8453, WETH, 'eth'),
                                     (81457, USDB, 'usdb'), (81457, BLAST, 'blast'),
                                     (8453, SIGNET, 'signet')]}})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8806)
    parser.add_argument('--package-root', type=Path, default=PROJECT,
                        help='Absolute installed kira-wallet package directory; defaults to this repository.')
    args = parser.parse_args(argv)
    if not args.package_root.is_absolute():
        parser.error('--package-root must be an absolute package directory.')
    package_root = args.package_root.resolve()
    if not (package_root / 'kira_service.py').is_file() or not (package_root / 'viewer/server.py').is_file():
        parser.error('--package-root must contain the Kira application and viewer.')
    with tempfile.TemporaryDirectory(prefix='kira-readme-preview-') as folder:
        root = Path(folder)
        # Configure isolation before importing runtime modules. In particular, no
        # inherited operator configuration or OWS vault belongs in this preview.
        os.environ['KIRA_DATA_DIR'] = str(root)
        os.environ['KIRA_CONFIG'] = str(root / '.kira.local.json')
        os.environ['KIRA_RPC_ENV'] = str(root / 'unused-provider.env')
        os.environ['KIRA_OWS_VAULT'] = str(root / 'unused-vault')
        sys.path[:0] = [str(package_root), str(package_root / 'viewer')]
        from kira_jobs import JobStore, atomic
        from kira_ows import OwsStore
        from kira_service import Application
        import server

        records(root, atomic)
        server.ROOT = root
        JobStore.launch = lambda _: None
        application = Application(root)
        state = application.views.refresh()
        # USDB and BLAST have no handwritten liquidity evidence. The current
        # application correctly leaves those saved spot references unpriced.
        assert abs(state['dashboard']['known_value_usd'] - 13053.5) < .001
        http = ThreadingHTTPServer(('127.0.0.1', args.port), server.Handler)
        http.controls = True; http.session_token = secrets.token_urlsafe(32)
        http.daemon_threads = True
        http.application = application; http.jobs = application.jobs
        http.ows = OwsStore(root, vault=root / 'unused-vault', runner=lambda _: {'wallets': []})
        package = json.loads((package_root / 'package.json').read_text())
        print(json.dumps({'package_root': str(package_root), 'package_version': package['version'],
                          'viewer_source': str(Path(server.__file__).resolve()),
                          'fixture_source': str(Path(__file__).resolve()),
                          'synthetic_demo': True, 'fixture_observed_at': STAMP,
                          'provider_workers': False, 'isolated_ows': True}), flush=True)
        print(f'Isolated README preview: http://127.0.0.1:{args.port}', flush=True)
        try: http.serve_forever()
        except KeyboardInterrupt: pass
        finally: http.server_close()


if __name__ == '__main__': main()
