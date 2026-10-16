"""Aggregate setup readiness. Never return credential values or wallet identities."""
from kira_config import load_config, secret_values


def readiness():
    config = load_config()
    discovery = config['discovery']
    configured = discovery['provider'] != 'none'
    local_available = bool(secret_values(config).get(discovery['key_env']))
    available = configured and local_available
    public = discovery.get('public',True) and not (config['rpc']['mode']=='custom' and config['rpc'].get('allow_public_fallback',True) is False)
    return {'public_discovery':public, 'rpc_mode': config['rpc']['mode'],
            'discovery_provider': discovery['provider'],
            'discovery_configured': configured,
            'discovery_key_available': bool(available),
            'local_key_available': local_available}
