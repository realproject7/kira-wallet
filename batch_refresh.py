"""Refresh the holdings of several wallets in one run.

Kira's worker hands every queued holdings refresh of the same scope to this
process. Each wallet keeps its own job, snapshot folder and published result,
written by the same steps as a single refresh. What the wallets share is the
reading: one token list request per wallet, one chain read per network for all
wallets at one pinned block, one market and price lookup per token, and one
Node process whose Alchemy reads spend from one compute-unit budget.
"""
import argparse
import fcntl
import json
import os
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wallet as engine
from wallet import ASSETS, ROOT, atomic, h, read

# Token lists: explorer hosts see at most this many wallets at once, each host paced
# at four requests a second (public_discovery.fetch_page).
DISCOVERY_WORKERS = 8
# Prices, markets, sell quotes and publication, wallet by wallet.
FINISH_WORKERS = 6
# DEX Screener allows 300 token lookups a minute; stay under it.
DEX_INTERVAL = 0.22
# Alchemy's price index: at most three requests a second.
INDEX_INTERVAL = 0.34
SCAN_TIMEOUT = 1800


class Item:
    def __init__(self, job, wallet):
        self.job_id = job['job_id']
        self.wallet = wallet
        self.folder = ROOT / job['checkpoint']
        self.generation = job.get('parent_job_id', job['job_id'])
        self.prepared = None
        self.error = None
        self.cancelled = False


def cancelled(job_id):
    try:
        return bool(read(ROOT / 'jobs' / f'{job_id}.json').get('cancel_requested'))
    except (OSError, ValueError):
        return False


def run_record(item, scope, **fields):
    atomic(item.folder / 'run.json', {'wallet_address': item.wallet['address'], 'tags': item.wallet['tags'],
                                      'inventory_policy': 'full_registry', 'refresh_scope': scope, 'batch_size': fields.pop('batch_size', None), **fields})


def fail(item, scope, error, size):
    item.error = error
    run_record(item, scope, batch_size=size, failed_at=h.now(), status='failed', error_code=getattr(error, 'code', 'engine_failed'), error=h.redact(str(error)))
    engine.CONTEXT.job_id = item.job_id
    try:
        engine.event('failed', error=h.redact(str(error)), resume=str(item.folder.relative_to(ROOT)))
    finally:
        engine.CONTEXT.job_id = None


def in_job(item, step):
    """Run one wallet's step in this thread, tagged with its job."""
    engine.CONTEXT.job_id = item.job_id
    engine.CONTEXT.generation = item.generation
    try:
        return step()
    finally:
        engine.CONTEXT.job_id = None
        engine.CONTEXT.generation = None


class MarketLookups:
    """DEX Screener records for every token the batch prices, thirty contracts per
    request and at most four requests a second. Each wallet's pricing then uses the
    records that list its own tokens, as if it had asked for them itself."""

    def __init__(self):
        self.records, self.by_token = [], {}
        self.lock, self.pace = threading.Lock(), threading.Lock()
        self.next = 0.0

    def turn(self):
        with self.pace:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + DEX_INTERVAL
        time.sleep(max(0, start - now))

    def fetch(self, keys):
        with self.lock:
            missing = [key for key in keys if key not in self.by_token]

        def get(request):
            self.turn()
            response = engine.fetch(request[3], deadline=time.monotonic() + 25)
            return request, {'source': request[3], 'observed_at': h.now(), 'response': response}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for (cid, slug, addresses, source), record in pool.map(get, engine.dex_requests(missing)):
                with self.lock:
                    self.records.append({'chain_id': cid, 'record': record})
                    if isinstance(record['response'], list):
                        for address in addresses:
                            self.by_token[(cid, address)] = len(self.records) - 1

    def listed(self):
        listed = set()
        for row in self.records:
            for pair in row['record']['response'] if isinstance(row['record']['response'], list) else []:
                for side in ('baseToken', 'quoteToken'):
                    token = (pair.get(side) or {}) if isinstance(pair, dict) else {}
                    if isinstance(token.get('address'), str):
                        listed.add((row['chain_id'], token['address'].lower()))
        return listed


def mainnet_ids(networks):
    return {n['chain_id'] for n in networks if n.get('environment') == 'mainnet'}


def candidate_keys(items, networks):
    """Tokens worth looking up before the chain read finishes: discovered and earlier holdings."""
    mainnets, keys = mainnet_ids(networks), set()
    for item in items:
        for t in read(item.folder / 'scan-input.json').get('candidates', []):
            if t.get('chain_id') in mainnets and isinstance(t.get('address'), str):
                keys.add((t['chain_id'], t['address'].lower()))
    return keys


def held_tokens(items, networks):
    """Every wallet's market-priced tokens, and the tokens worth asking the price index about."""
    mainnets, wanted, worth = mainnet_ids(networks), {}, set()
    for item in items:
        chains = read(item.folder / 'onchain-summary.json')['chains']
        tokens = [engine.canonical_token(t) for c in chains if isinstance(c, dict) for t in c.get('tokens', [])]
        mine = engine.market_wanted(tokens, mainnets)
        wanted.update(mine)
        worth.update(engine.worth_asking(mine, engine.index_hint(item.wallet)))
    return wanted, worth


def index_lookups(lookups, wanted, worth, work):
    """Alchemy's price index for held tokens DEX Screener lists in no pair at all."""
    listed = lookups.listed()
    unlisted = sorted(key for key, t in wanted.items() if key in lookups.by_token and key not in listed
                      and key[0] in engine.ALCHEMY and t.get('token_type') == 'ERC20' and key in worth)
    from curve_pricing import index_prices
    ask = engine.unasked(unlisted)
    chunks = [ask[i:i + 25] for i in range(0, len(ask), 25)]
    answered = set()
    deadline = time.monotonic() + 90
    prices = {}
    pace, turn = threading.Lock(), [0.0]

    def lookup(chunk):
        # Alchemy's price index answered 429 to eight requests at once (2026-11-15).
        # Start at most three requests a second, four in flight.
        with pace:
            start = max(time.monotonic(), turn[0])
            turn[0] = start + INDEX_INTERVAL
        time.sleep(max(0, start - time.monotonic()))
        answer = index_prices(chunk, work, deadline)
        answered.update(answer.get('answered', set()))
        return answer['tokens']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for found in pool.map(lookup, chunks):
            for row in found:
                prices[(row['chain_id'], row['address'].lower())] = row
    engine.remember_index_answers(answered, set(prices))
    return {'prices': prices, 'asked': set(unlisted), 'observed_at': h.now()}


def factory_lookups(items, networks, helper, work):
    """Check every wallet's factory tokens against DEX factories in one run (market_discovery)."""
    import market_discovery
    union = {}
    for item in items:
        chains = read(item.folder / 'onchain-summary.json')['chains']
        snapshot = {'tokens': [t for c in chains if isinstance(c, dict) for t in c.get('tokens', [])],
                    'coverage': [{'chain_id': n['chain_id'], 'environment': n.get('environment')} for n in networks]}
        tokens, _ = market_discovery.factory_plan(snapshot, market_discovery.active_mainnets(snapshot))
        for t in tokens:
            union.setdefault(f"{t['chain_id']}:{t['token_address'].lower()}", t)
    if not union:
        return None
    source, output = work / 'factory-input.json', work / 'factory-markets.json'
    atomic(source, {'tokens': list(union.values()), 'networks': read(ASSETS / 'networks.json')['networks'], 'budget_ms': 120000})
    helper.call('factory-markets', source, output, 150)
    found = read(output)
    return {'by_id': {row['id']: row['pools'] for row in found.get('markets', [])}, 'status': found.get('status', 'partial'),
            'checked': set(union), 'checked_requests': found.get('checked'), 'total_requests': found.get('total')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('full', 'fast'), default='full')
    parser.add_argument('--job', action='append', required=True)
    args = parser.parse_args(argv)
    from kira_config import require_alchemy
    require_alchemy()
    with (os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (ROOT / '.analysis.lock').open('a')) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another wallet analysis is running. Resume after it finishes.')
        return run(args.job, args.scope)


def run(job_ids, scope):
    """Every Alchemy request of this batch, here and in its Node helper, counts toward one usage group."""
    import uuid, kira_usage
    previous = os.environ.get('KIRA_BATCH_ID')
    os.environ['KIRA_BATCH_ID'] = 'batch-' + uuid.uuid4().hex[:16]
    try:
        kira_usage.note_batch(os.environ['KIRA_BATCH_ID'], list(dict.fromkeys(job_ids)), scope, ROOT)
        return refresh(job_ids, scope)
    finally:
        if previous is None:
            os.environ.pop('KIRA_BATCH_ID', None)
        else:
            os.environ['KIRA_BATCH_ID'] = previous


def refresh(job_ids, scope):
    started = time.monotonic()
    timings = {}
    registry = read(ROOT / 'wallets.json')
    registered = read(ROOT / 'networks.json')['networks']
    candidates = read(ASSETS / 'sources/rpc-candidates.json')
    from chain_lifecycle import retired
    networks = [{**n, **next((c for c in candidates if c['chain_id'] == n['chain_id']), {})} for n in registered if not retired(n['chain_id'])]
    items = []
    for job_id in dict.fromkeys(job_ids):
        job = read(ROOT / 'jobs' / f'{job_id}.json')
        if job.get('operation') != 'wallet.refresh' or job.get('checkpoint') != 'snapshots/jobs/' + job_id:
            raise SystemExit('Only holdings refresh jobs can run in a batch.')
        entry = next((w for w in registry['wallets'] if w['address_key'] == str(job['input'].get('wallet', '')).lower()), None)
        if entry is None or entry['address_key'] in registry.get('removed_wallets', {}):
            continue
        item = Item(job, entry)
        item.folder.mkdir(parents=True, exist_ok=True)
        items.append(item)
    size = len(items)
    for item in items:
        run_record(item, scope, batch_size=size, started_or_resumed_at=h.now(), status='running')
        in_job(item, lambda: engine.event('registered', wallet=item.wallet['address'], tags=item.wallet['tags'], snapshot=str(item.folder.relative_to(ROOT))))
    if not items:
        return 0
    try:
        # The deployment catalogue is checked once; every wallet keeps the same evidence.
        engine.source_check(registered, items[0].folder)
        for item in items[1:]:
            shutil.copyfile(items[0].folder / 'mintclub-support.json', item.folder / 'mintclub-support.json')
    except Exception as error:
        for item in items:
            fail(item, scope, error, size)
        return 1
    work = ROOT / 'cache' / 'batch-refresh' / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    engine.BATCH.clear()
    engine.BATCH.update(active=True, images=True)
    try:
        with engine.NodeHelper() as helper:
            engine.NODE_HELPER = helper

            def prepare(item):
                if cancelled(item.job_id):
                    item.cancelled = True
                    return
                try:
                    item.prepared = in_job(item, lambda: engine.prepare_holdings(item.wallet, item.folder, networks, scope))
                except Exception as error:
                    fail(item, scope, error, size)
            # Wallets that held the most tokens last time page longest; start them first.
            def previous(item):
                try:
                    chains = read(ROOT / item.wallet['latest_snapshot']['directory'] / 'onchain-summary.json')['chains']
                    return -sum(len(c.get('tokens', [])) for c in chains if isinstance(c, dict))
                except (OSError, ValueError, KeyError, TypeError):
                    return 0
            with ThreadPoolExecutor(max_workers=DISCOVERY_WORKERS) as pool:
                list(pool.map(prepare, sorted(items, key=previous)))
            timings['token_lists'] = round(time.monotonic() - started, 1)
            ready = [item for item in items if item.prepared]
            # Market lookups use DEX Screener, not Alchemy, so they run during the chain read.
            lookups = MarketLookups()
            early = threading.Thread(target=lambda: lookups.fetch(candidate_keys(ready, networks)), daemon=True)
            early.start()
            if ready:
                batch_input = work / 'batch-scan.json'
                atomic(batch_input, {'wallets': [{'job_id': item.job_id, 'folder': str(item.folder), 'input_path': str(item.folder / 'scan-input.json')} for item in ready]})
                try:
                    helper.call('batch-scan', batch_input, None, SCAN_TIMEOUT)
                except (TimeoutError, ValueError):
                    pass
                # A wallet the batch read could not finish is read on its own, as before.
                for item in ready:
                    if not (item.folder / 'onchain-summary.json').exists():
                        try:
                            in_job(item, lambda: engine.run_node('scan', item.folder / 'scan-input.json', item.folder))
                        except Exception as error:
                            fail(item, scope, error, size)
                ready = [item for item in ready if not item.error]
            timings['chain_reads'] = round(time.monotonic() - started, 1)
            early.join()
            if ready:
                try:
                    wanted, worth = held_tokens(ready, networks)
                    lookups.fetch(list(wanted))
                    engine.BATCH['dex'] = {'records': lookups.records, 'by_token': lookups.by_token}
                    engine.BATCH['index'] = index_lookups(lookups, wanted, worth, work)
                    timings['markets'] = {'tokens': len(wanted), 'dex_requests': len(lookups.records),
                                          'index_asked': len(engine.BATCH['index']['asked']), 'index_priced': len(engine.BATCH['index']['prices'])}
                except Exception:
                    engine.BATCH.pop('dex', None)
                    engine.BATCH.pop('index', None)
                try:
                    factory = factory_lookups(ready, networks, helper, work)
                    if factory:
                        engine.BATCH['factory'] = factory
                except Exception:
                    engine.BATCH.pop('factory', None)
            timings['shared_prices'] = round(time.monotonic() - started, 1)

            def finish(item):
                if cancelled(item.job_id):
                    item.cancelled = True
                    return None
                try:
                    result = in_job(item, lambda: engine.finish_holdings(item.wallet, item.folder, networks, item.prepared, pipeline={'batch_size': size}))
                    run_record(item, scope, batch_size=size, completed_at=h.now(), status=result['status'])
                    in_job(item, lambda: engine.event('published', snapshot=str(item.folder.relative_to(ROOT)), counts=result['counts'], status=result['status']))
                    return result
                except Exception as error:
                    fail(item, scope, error, size)
                    return None
            # The wallets with the most holdings start first, so the longest ones overlap the rest.
            def holdings(item):
                try:
                    return sum(len(c.get('tokens', [])) for c in read(item.folder / 'onchain-summary.json')['chains'] if isinstance(c, dict))
                except (OSError, ValueError, KeyError):
                    return 0
            ready.sort(key=holdings, reverse=True)
            with ThreadPoolExecutor(max_workers=FINISH_WORKERS) as pool:
                results = list(pool.map(finish, ready))
            timings['published'] = round(time.monotonic() - started, 1)
            engine.NODE_HELPER = None
        # Platform positions of every published wallet follow in one shared run.
        published = [item for item, result in zip(ready, results) if result and not cancelled(item.job_id)]
        if published:
            for item in published:
                in_job(item, lambda: engine.event('onchain_progress', operation='positions'))
            try:
                import position_update
                position_update.update(ROOT, [read(ROOT / 'jobs' / f'{item.job_id}.json') for item in published])
            except Exception:
                pass  # Holdings are published; positions keep their earlier records.
            timings['positions'] = round(time.monotonic() - started, 1)
        snapshots = [result for result in results if result]
        if snapshots:
            # Artwork is shared by contract across wallets; refresh it once.
            sys.path.insert(0, str(ASSETS / 'viewer'))
            from token_images import refresh_catalog
            metadata = [row['record'] for row in engine.BATCH.get('dex', {}).get('records', [])]
            native = engine.BATCH.get(('native', tuple(sorted(n['chain_id'] for n in networks))), {})
            # Artwork lookups go to DEX Screener too, so they keep the same pace.
            def paced(url):
                lookups.turn()
                return engine.fetch(url, deadline=time.monotonic() + 20)
            try:
                refresh_catalog(snapshots, ROOT, native_images=native.get('images') or {}, market_metadata=metadata, fetch=paced)
            except (OSError, ValueError):
                pass
        registry = read(ROOT / 'wallets.json')
        for item in items:
            try:
                engine.prune_resume_checkpoints(item.wallet, registry)
            except (OSError, ValueError, KeyError):
                pass
    finally:
        engine.NODE_HELPER = None
        engine.BATCH.clear()
        shutil.rmtree(work, ignore_errors=True)
    timings['total'] = round(time.monotonic() - started, 1)
    summary = {'observed_at': h.now(), 'wallets': size, 'scope': scope, 'failed': sum(1 for item in items if item.error),
               'cancelled': sum(1 for item in items if item.cancelled), 'timings': timings}
    try:
        atomic(ROOT / 'cache' / 'batch-refresh-last.json', summary)
    except OSError:
        pass
    engine.emit({'stage': 'batch_summary', **summary})
    return 0 if all(not item.error for item in items) else 1


if __name__ == '__main__':
    sys.exit(main())
