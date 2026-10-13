"""Durable discovery frontiers with immutable, bounded candidate segments."""
import hashlib
import json
import os
from pathlib import Path
import re

SEGMENT_SIZE = 512
SEGMENT_FIELDS = ('contracts', 'tokens', 'completed_ranges', 'pending_ranges', 'blocked_ranges', 'seen_cursors')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def identity(state, wallet, chain_id, provider):
    if (not isinstance(state, dict) or state.get('wallet') != wallet.lower()
            or type(state.get('chain_id')) is not int or state['chain_id'] != chain_id
            or state.get('provider', provider) != provider):
        raise ValueError('Discovery checkpoint identity mismatch.')


def load(path, wallet, chain_id, provider):
    path = Path(path)
    if not path.exists():
        return None
    if path.stat().st_size > 4_000_000:
        raise ValueError('Discovery manifest exceeds its supported size.')
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError('Invalid discovery checkpoint.')
    if 'storage_version' not in manifest:
        # Version 0.1.10 used inline candidates. Migrate on the next saved page.
        identity(manifest, wallet, chain_id, provider)
        return manifest
    if type(manifest.get('storage_version')) is not int or manifest['storage_version'] != 1 or not isinstance(manifest.get('sections'), dict):
        raise ValueError('Unsupported discovery storage version.')
    state = manifest.get('state')
    identity(state, wallet, chain_id, provider)
    state = dict(state)
    for field, descriptors in manifest['sections'].items():
        if field not in SEGMENT_FIELDS or not isinstance(descriptors, list):
            raise ValueError('Invalid discovery segment manifest.')
        values = []
        for descriptor in descriptors:
            if (not isinstance(descriptor, dict) or not isinstance(descriptor.get('sha256'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', descriptor['sha256'])
                    or type(descriptor.get('count')) is not int or not 1 <= descriptor['count'] <= SEGMENT_SIZE):
                raise ValueError('Invalid discovery segment reference.')
            chunk = path.parent / (path.stem + '.chunks') / (descriptor['sha256'] + '.json')
            if chunk.stat().st_size > 1_000_000:
                raise ValueError('Discovery segment exceeds its supported size.')
            content = chunk.read_bytes()
            if hashlib.sha256(content).hexdigest() != descriptor['sha256']:
                raise ValueError('Discovery segment digest mismatch.')
            part = json.loads(content)
            if not isinstance(part, list) or len(part) != descriptor['count']:
                raise ValueError('Invalid discovery segment contents.')
            values.extend(part)
        state[field] = values
    return state


def save(path, state, wallet, chain_id, provider):
    path = Path(path)
    identity(state, wallet, chain_id, provider)
    header = {**state, 'provider': provider}
    sections = {}
    for field in SEGMENT_FIELDS:
        if field not in header:
            continue
        values = header.pop(field)
        if not isinstance(values, list):
            raise ValueError('Discovery segment must be a list.')
        sections[field] = []
        for offset in range(0, len(values), SEGMENT_SIZE):
            part = values[offset:offset + SEGMENT_SIZE]
            content = encoded(part)
            if len(content) > 1_000_000:
                raise ValueError('Discovery segment exceeds its supported size.')
            digest = hashlib.sha256(content).hexdigest()
            chunk = path.parent / (path.stem + '.chunks') / (digest + '.json')
            if chunk.exists():
                if hashlib.sha256(chunk.read_bytes()).hexdigest() != digest:
                    raise ValueError('Existing discovery segment digest mismatch.')
            else:
                atomic(chunk, part)
            sections[field].append({'sha256': digest, 'count': len(part)})
    manifest = {'storage_version': 1, 'state': header, 'sections': sections}
    if len(encoded(manifest)) > 4_000_000:
        raise ValueError('Discovery manifest exceeds its supported size.')
    # Chunks are durable before the manifest advances. An interrupted write can
    # leave an unused chunk, never a frontier referring to an unsaved page.
    atomic(path, manifest)
