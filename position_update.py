"""Bring platform positions up to date right after a holdings refresh.

A holdings refresh (one wallet, a batch, or a new wallet) ends here: every wallet's
saved claims, wallet NFT inventories, staking pools and new Aero gauges (Aeromax
ranges) are read again in one Node run that works on every chain and wallet at once.
Legacy registries stay with Find new positions.

The positions are saved in the holdings job's own folder and the positions index
points there. What the run does not finish keeps its earlier records, marked partial.
A failure here never changes the holdings that were already published.
"""
import json
import math
from pathlib import Path
import subprocess
import uuid

from kira_config import ASSETS
from kira_jobs import atomic, now
import position_worker

# Every wallet starts at once, so the same reads of different wallets share multicalls.
# Alchemy bills each multicall once; the run is paced by the shared compute-unit budget.
WALLET_CONCURRENCY = 100
UPDATE_BUDGET_MS = 240000


def timeout(count):
    """Each reader stops itself within its budget; this only bounds a stuck process."""
    return 120 + UPDATE_BUDGET_MS / 1000 * math.ceil(count / WALLET_CONCURRENCY)


def update(root, jobs, *, run=subprocess.run):
    """Update positions for the wallets of these holdings jobs. Returns {job_id: summary}."""
    root = Path(root)
    work = []
    for job in jobs:
        address = str(job['input'].get('wallet') or job['input'].get('address') or '').lower()
        record = {'job_id': job['job_id'], 'created_at': job.get('created_at') or now(), 'checkpoint': job['checkpoint'] + '/positions',
                  'attempt': 1, 'input': {'wallet': address, 'discover': False}}
        folder = root / record['checkpoint']
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # Every refresh reads afresh; a leftover checkpoint would replay an older pin.
            (folder / 'positions-checkpoint.json').unlink(missing_ok=True)
            atomic(folder / 'positions-input.json', {**position_worker.prepare_input(root, address, False), 'budget_ms': UPDATE_BUDGET_MS})
        except (OSError, ValueError, KeyError, StopIteration):
            continue
        work.append((record, folder))
    if not work:
        return {}
    spec = root / 'cache' / ('positions-update-' + uuid.uuid4().hex + '.json')
    atomic(spec, {'shared_path': str(root / 'cache/positions-shared.json'), 'wallet_concurrency': WALLET_CONCURRENCY,
                  'wallets': [{'input_path': str(folder / 'positions-input.json'), 'checkpoint_path': str(folder / 'positions-checkpoint.json')}
                              for _, folder in work]})
    try:
        run(['node', str(ASSETS / 'position-reader.cjs'), '--batch', str(spec)], cwd=ASSETS, timeout=timeout(len(work)),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass  # Checkpoints saved so far are published below.
    finally:
        spec.unlink(missing_ok=True)
    results = {}
    for record, folder in work:
        try:
            state = json.loads((folder / 'positions-checkpoint.json').read_text())
            saved = position_worker.publish(root, record, state, final=True)
            results[record['job_id']] = {'status': saved['status'], 'position_count': len(saved['positions']),
                                         'coverage_gaps': sum(c.get('status') != 'checked' for c in saved['coverage'])}
        except (OSError, ValueError, KeyError, TypeError):
            results[record['job_id']] = None
        for name in ('positions-input.json', 'positions-checkpoint.json'):
            (folder / name).unlink(missing_ok=True)
    return results
