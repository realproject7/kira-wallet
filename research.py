"""Read-only helpers for wallet liquidity research. Never print RPC credentials."""
from pathlib import Path
import datetime
import json
import re
import urllib.request
import urllib.error
from kira_config import ASSETS, data_root, secret_values, redact

ROOT = data_root()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def secrets():
    return secret_values()

def fetch(url, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'wallet-research'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        return {'transport_error': {'status': error.code, 'message': redact(error.read().decode())[:2500]}}
    except Exception as error:
        return {'transport_error': {'type': type(error).__name__, 'message': redact(str(error))[:500]}}

def rpc(url, method, params):
    return fetch(url, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')

def alchemy_url(network):
    key = secrets()['ALCHEMY_CUSTOM_APY_KEY']
    return f'https://{network}.g.alchemy.com/v2/{key}'
