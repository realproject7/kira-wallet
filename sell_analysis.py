"""Compare saved quantities and retain dated sell evidence. No provider access."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path


def signature(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino
    except FileNotFoundError:
        return None


def snapshot_path(root, snapshot_id):
    if not isinstance(snapshot_id, str) or not snapshot_id.startswith('snapshots/'):
        raise ValueError('Invalid analysis snapshot')
    path = (root / snapshot_id / 'results.json').resolve()
    if not path.is_relative_to((root / 'snapshots').resolve()):
        raise ValueError('Analysis snapshot outside research directory')
    return path


@lru_cache(maxsize=4096)
def _job(path, version):
    value = json.loads(Path(path).read_text())
    return {k: value.get(k) for k in ('job_id', 'input', 'state', 'analysis_phase', 'result', 'created_at')}


def analysis_index(root):
    """Compact stat-cached headers, including history beyond the Activity page."""
    rows = {}
    for path in (root / 'jobs').glob('*.json'):
        try:
            job = _job(str(path), signature(path))
            if job['analysis_phase'] != 'enrichment' or job['state'] not in ('partial', 'succeeded'):
                continue
            address = str((job['input'] or {}).get('wallet') or (job['input'] or {}).get('address') or '').lower()
            snapshot_id = (job['result'] or {}).get('snapshot_id')
            evidence = quantities(root, snapshot_id, address)
            if evidence is None:
                continue
            row = {'job_id': job['job_id'], 'snapshot_id': snapshot_id, 'analysed_at': evidence['analysed_at']}
            if (row['analysed_at'] or '', job['created_at'] or '') > rows.get(address, {}).get('_order', ('', '')):
                rows[address] = {**row, '_order': (row['analysed_at'] or '', job['created_at'] or '')}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return rows


def amount(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


@lru_cache(maxsize=512)
def _quantities(path, version):
    value = json.loads(Path(path).read_text())
    chains = {c['chain_id']: c for c in value.get('coverage', [])}
    positions, uncertain = {}, set()
    from chain_lifecycle import retired
    for token in value.get('tokens', []):
        chain = token['chain_id']
        if chains.get(chain, {}).get('environment') == 'testnet' or retired(chain):
            continue
        identity = (chain, token['token_address'].lower(), str(token.get('token_type') or 'ERC20').upper(), str(token.get('token_id') or '0'))
        quantity = amount(token.get('wallet_balance'))
        raw = token.get('wallet_balance_raw')
        raw = str(int(raw)) if raw is not None and str(raw).isdigit() else None
        if quantity is None or token.get('balance_evidence_retained') or token.get('metadata_evidence_retained'):
            uncertain.add(identity)
        if quantity is not None and quantity > 0:
            positions[identity] = (raw, quantity)
    for chain, coverage in chains.items():
        if coverage.get('environment') == 'testnet' or retired(chain):
            continue
        identity = (chain, 'native', 'native', '0')
        quantity = amount(coverage.get('native_balance'))
        if quantity is None:
            uncertain.add(identity)
        elif quantity > 0:
            positions[identity] = (None, quantity)
    complete = {chain for chain, c in chains.items() if c.get('rpc_status') == 'available'
                and (c.get('indexer_complete') is True or c.get('general_erc20_discovery') == 'indexer_checked')
                and not c.get('candidate_balance_errors') and not c.get('balance_errors')
                and not (c.get('candidate_scan') or {}).get('deferred')
                and not (c.get('mintclub_registry_scan') or {}).get('balance_errors')}
    native_checked = {chain for chain, c in chains.items() if amount(c.get('native_balance')) is not None}
    return {'wallet': value.get('wallet_address', '').lower(), 'positions': positions, 'uncertain': uncertain,
            'complete': complete, 'native_checked': native_checked, 'analysed_at': value.get('compiled_at')}


def quantities(root, snapshot_id, address):
    try:
        path = snapshot_path(root, snapshot_id)
        value = _quantities(str(path), signature(path))
        return value if value['wallet'] == address else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def same_amount(first, second):
    return first[0] == second[0] if first[0] is not None and second[0] is not None else first[1] == second[1]


def assess(root, entry, index=None, *, snapshot_id=None):
    address = entry['address_key']
    prior = (analysis_index(root) if index is None else index).get(address)
    current_id = snapshot_id or (entry.get('latest_snapshot') or {}).get('directory')
    current = quantities(root, current_id, address)
    previous = quantities(root, prior['snapshot_id'], address) if prior else None
    summary = {'status': 'not_analyzed', 'needs_analysis': bool(current), 'changed_count': 0,
               'last_analyzed_at': prior['analysed_at'] if prior else None,
               'snapshot_id': prior['snapshot_id'] if prior else None,
               'job_id': prior['job_id'] if prior else None}
    generation=entry.get('research_generation')
    if generation and snapshot_id is None:
        path=root/'jobs'/(generation+'.json')
        try:
            baseline=_job(str(path),signature(path))
            if baseline['state'] not in ('succeeded','partial') or not baseline['result']:
                summary.update(status='holdings_pending' if baseline['state'] in ('queued','running') else 'holdings_required',needs_analysis=False)
                return summary
        except (OSError,ValueError,TypeError):
            pass
    if not current:
        summary.update(status='holdings_required', needs_analysis=False)
    elif previous:
        changes = 0
        unknown = bool(current['uncertain'] & (current['positions'].keys() | previous['positions'].keys()))
        for identity in current['positions'].keys() | previous['positions'].keys():
            now, before = current['positions'].get(identity), previous['positions'].get(identity)
            if identity in current['uncertain']:
                unknown = True
            elif now is not None and before is not None:
                changes += not same_amount(now, before)
            elif now is not None:
                changes += 1
            elif identity[0] in (current['native_checked'] if identity[1] == 'native' else current['complete']):
                changes += 1
            else:
                unknown = True
        summary.update(status='changed' if changes else 'unverified' if unknown else 'current',
                       needs_analysis=bool(changes), changed_count=changes)
    return summary


def reuse_estimates(wallet, old_wallet, current, previous, summary):
    """Carry only equal-quantity quote fields, with their original timestamps."""
    old = {asset['id']: asset for asset in old_wallet['assets']}
    matched = {f'{key[0]}:{key[1]}' for key, value in current['positions'].items()
               if key not in current['uncertain'] and key in previous['positions']
               and same_amount(value, previous['positions'][key])}
    # The existing viewer has one row per contract. Never fold multiple NFT IDs
    # into a reusable full-balance quote for that row.
    from collections import Counter
    for positions in (current['positions'],previous['positions']):
        matched.difference_update(identity for identity,count in Counter(f'{key[0]}:{key[1]}' for key in positions).items() if count>1)
    for asset in wallet['assets']:
        prior = old.get(asset['id'])
        if not prior or asset['id'] not in matched or asset.get('is_native') or asset.get('quantity_retained'):
            continue
        # A newly saved quote wins. Unavailable old routes remain unknown too.
        if asset.get('sell_out') or not prior.get('sell_out'):
            continue
        for field in ('sell_out', 'exit_quote', 'burn_quote', 'cashout_eligibility', 'exit_route'):
            asset[field] = deepcopy(prior.get(field))
        asset['sell_analysis_provenance'] = {'snapshot_id': summary['snapshot_id'],
                                         'analyzed_at': summary['last_analyzed_at'], 'reused': True}
