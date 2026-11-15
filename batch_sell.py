"""Update the sell estimates of several wallets in one run.

Kira's worker hands every queued sell estimate job to this process, one wallet or many.
Each wallet keeps its own job, folder and published result, written by the same steps as
a single run (wallet.py --phase sell). What the wallets share: one DEX Screener lookup per
token, paced under its limit; one native coin lookup; one Node process whose Alchemy reads
spend from one compute unit budget and read each saved block's header once; one artwork
refresh at the end. Each wallet runs until it is done instead of in three-minute slices;
the worker stops the run when shorter work is queued, and every wallet resumes from its
saved checks.
"""
import argparse
import fcntl
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import wallet as engine
from batch_refresh import MarketLookups, cancelled, in_job
from wallet import ASSETS, ROOT, atomic, h, read

# Wallets whose market steps run at once. Their reads share the Node process's lanes.
WALLET_WORKERS = 8
# DEX Screener allows 300 pool lookups a minute. Python lookups keep 240 of them; route
# lookups from the Node process (a few intermediate tokens per batch) use the rest.
DEX_INTERVAL = 0.25
# One wallet's turn inside the batch. Pools are checked several at a time, so the largest
# wallets finish well inside it; if one does not, it saves its checks and resumes later.
SELL_SECONDS = 1800
# A turn can end with a few checks pending: a pool read that failed once gets its second
# admission in the next turn. A wallet takes up to three turns here, a cooldown apart, while
# each turn makes progress; after that the worker's continuation takes over as before.
TURNS = 3
TURN_PAUSE = 5


class Item:
    def __init__(self, job, wallet, source):
        self.job_id = job['job_id']
        self.wallet = wallet
        self.folder = ROOT / job['checkpoint']
        self.generation = job['parent_job_id']
        self.source = source
        self.size = 0
        self.error = None
        self.cancelled = False


class Pacer:
    """Start requests at most once per interval across every thread."""

    def __init__(self, interval):
        self.interval, self.lock, self.next = interval, threading.Lock(), 0.0

    def __call__(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.interval
        time.sleep(max(0, start - now))


def run_record(item, **fields):
    atomic(item.folder / 'run.json', {'wallet_address': item.wallet['address'], 'tags': item.wallet['tags'],
                                      'inventory_policy': 'full_registry', 'refresh_scope': 'full',
                                      'holdings_snapshot': item.source, **fields})


def stop(item, error, size):
    """Record a paused or failed wallet the way a single run does."""
    item.error = error
    run_record(item, batch_size=size, failed_at=h.now(), status='failed',
               error_code=getattr(error, 'code', 'engine_failed'), error=h.redact(str(error)))
    stage = ('market_paused' if isinstance(error, engine.MarketPause) else
             'research_paused' if isinstance(error, engine.ResearchPause) else 'failed')
    in_job(item, lambda: engine.event(stage, error=h.redact(str(error)), resume=str(item.folder.relative_to(ROOT))))


def progress(item):
    try:
        return read(item.folder / 'continuation.json').get('fingerprint')
    except (OSError, ValueError, AttributeError):
        return None


def held_keys(item):
    """The wallet's held contracts on networks DEX Screener lists."""
    try:
        chains = read(ROOT / item.source / 'onchain-summary.json')['chains']
    except (OSError, ValueError, KeyError, TypeError):
        return set()
    return {(t['chain_id'], t['token_address'].lower()) for c in chains if isinstance(c, dict) for t in c.get('tokens', [])
            if isinstance(t, dict) and t.get('chain_id') in engine.DEX and t.get('token_type') != 'ERC1155' and isinstance(t.get('token_address'), str)}


def holdings_size(item):
    try:
        return sum(len(c.get('tokens', [])) for c in read(ROOT / item.source / 'onchain-summary.json')['chains'] if isinstance(c, dict))
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', action='append', required=True)
    args = parser.parse_args(argv)
    from kira_config import require_alchemy
    require_alchemy()
    with (os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (ROOT / '.analysis.lock').open('a')) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another wallet analysis is running. Resume after it finishes.')
        return run(args.job)


def run(job_ids):
    """Every Alchemy request of this batch, here and in its Node helper, counts toward one usage group."""
    import kira_usage
    previous = os.environ.get('KIRA_BATCH_ID')
    os.environ['KIRA_BATCH_ID'] = 'batch-' + uuid.uuid4().hex[:16]
    try:
        kira_usage.note_batch(os.environ['KIRA_BATCH_ID'], list(dict.fromkeys(job_ids)), 'sell', ROOT)
        return estimate(job_ids)
    finally:
        if previous is None:
            os.environ.pop('KIRA_BATCH_ID', None)
        else:
            os.environ['KIRA_BATCH_ID'] = previous


def items_for(job_ids, registry):
    items = []
    for job_id in dict.fromkeys(job_ids):
        job = read(ROOT / 'jobs' / f'{job_id}.json')
        if (job.get('operation') != 'wallet.refresh' or job.get('analysis_phase') != 'enrichment'
                or job.get('checkpoint') != 'snapshots/jobs/' + job_id or not job.get('parent_job_id')):
            raise SystemExit('Only sell estimate jobs can run in a sell batch.')
        parent = read(ROOT / 'jobs' / f"{job['parent_job_id']}.json")
        source = (parent.get('result') or {}).get('snapshot_id')
        entry = next((w for w in registry['wallets'] if w['address_key'] == str(job['input'].get('wallet', '')).lower()), None)
        if entry is None or entry['address_key'] in registry.get('removed_wallets', {}) or not isinstance(source, str):
            continue
        item = Item(job, entry, source)
        item.folder.mkdir(parents=True, exist_ok=True)
        items.append(item)
    return items


def estimate(job_ids):
    started = time.monotonic()
    registry = read(ROOT / 'wallets.json')
    registered = read(ROOT / 'networks.json')['networks']
    candidates = read(ASSETS / 'sources/rpc-candidates.json')
    from chain_lifecycle import retired
    networks = [{**n, **next((c for c in candidates if c['chain_id'] == n['chain_id']), {})} for n in registered if not retired(n['chain_id'])]
    items = items_for(job_ids, registry)
    size = len(items)
    for item in items:
        item.size = holdings_size(item)
        run_record(item, batch_size=size, started_or_resumed_at=h.now(), status='running')
        in_job(item, lambda: engine.event('registered', wallet=item.wallet['address'], tags=item.wallet['tags'], snapshot=str(item.folder.relative_to(ROOT))))
    if not items:
        return 0
    settings = {name: getattr(engine, name) for name in ('SELL_SECONDS', 'SELL_DISCOVERY_SECONDS', 'SELL_POOL_BUDGET_MS', 'SELL_ROOT_BUDGET_MS')}
    engine.SELL_SECONDS = SELL_SECONDS
    engine.SELL_DISCOVERY_SECONDS = SELL_SECONDS - 300
    engine.SELL_POOL_BUDGET_MS = (SELL_SECONDS - 300) * 1000
    engine.SELL_ROOT_BUDGET_MS = 600_000
    engine.BATCH.clear()
    engine.BATCH.update(active=True, images=True, pace=Pacer(DEX_INTERVAL))
    results = {}
    try:
        # Which held tokens any pool lists, thirty to a request for every wallet at once. Only
        # those get a pool lookup of their own; the others keep this answer as their evidence.
        lookups = MarketLookups()
        try:
            lookups.fetch(sorted(set().union(*(held_keys(item) for item in items))))
        except Exception:
            pass  # Each wallet then asks for its own tokens.
        engine.BATCH['listings'] = {'records': lookups.records, 'by_token': lookups.by_token}
        with engine.NodeHelper() as helper:
            engine.NODE_HELPER = helper

            def one(item):
                if cancelled(item.job_id):
                    item.cancelled = True
                    return
                try:
                    def step():
                        discovered = engine.saved_holdings(item.wallet, item.source, item.folder)
                        result = engine.finish(item.wallet, item.folder, networks, discovered, holdings_source=item.source)
                        engine.publish_snapshot(item.wallet, item.folder, result)
                        return result
                    seen = None
                    for turn in range(TURNS):
                        try:
                            result = in_job(item, step)
                            break
                        except engine.MarketPause:
                            fingerprint = progress(item)
                            if turn == TURNS - 1 or fingerprint == seen or cancelled(item.job_id):
                                raise
                            seen = fingerprint
                            time.sleep(TURN_PAUSE)
                    run_record(item, batch_size=size, completed_at=h.now(), status=result['status'])
                    in_job(item, lambda: engine.event('published', snapshot=str(item.folder.relative_to(ROOT)), counts=result['counts'], status=result['status']))
                    results[item.job_id] = result
                except Exception as error:
                    stop(item, error, size)
            # The wallets with the most holdings start first, so the longest ones overlap the rest.
            with ThreadPoolExecutor(max_workers=WALLET_WORKERS) as pool:
                list(pool.map(one, sorted(items, key=lambda item: -item.size)))
            engine.NODE_HELPER = None
        published = [item for item in items if item.job_id in results]
        if published:
            # Artwork is shared by contract across wallets; refresh it once.
            sys.path.insert(0, str(ASSETS / 'viewer'))
            from token_images import refresh_catalog
            metadata = [row['record'] for row in engine.BATCH.get('listings', {}).get('records', [])]
            native = next((value for key, value in engine.BATCH.items() if isinstance(key, tuple) and key[0] == 'native-sell'), {})

            def paced(url):
                engine.BATCH['pace']()
                return engine.fetch(url, deadline=time.monotonic() + 20)
            try:
                refresh_catalog([results[item.job_id] for item in published], ROOT, native_images=native.get('images') or {}, market_metadata=metadata, fetch=paced)
            except (OSError, ValueError):
                pass
        registry = read(ROOT / 'wallets.json')
        for item in published:
            try:
                engine.prune_resume_checkpoints(item.wallet, registry)
            except (OSError, ValueError, KeyError):
                pass
    finally:
        listed = len((engine.BATCH.get('listings') or {}).get('records', []))
        pool_lookups = len(engine.BATCH.get('lookups', {}))
        engine.NODE_HELPER = None
        engine.BATCH.clear()
        for name, value in settings.items():
            setattr(engine, name, value)
    summary = {'observed_at': h.now(), 'wallets': size, 'scope': 'sell', 'published': len(results),
               'paused_or_failed': sum(1 for item in items if item.error), 'cancelled': sum(1 for item in items if item.cancelled),
               'dex_listing_requests': listed, 'dex_pool_lookups': pool_lookups, 'seconds': round(time.monotonic() - started, 1)}
    try:
        atomic(ROOT / 'cache' / 'batch-sell-last.json', summary)
    except OSError:
        pass
    engine.emit({'stage': 'batch_summary', **summary})
    return 0 if all(not item.error for item in items) else 1


if __name__ == '__main__':
    sys.exit(main())
