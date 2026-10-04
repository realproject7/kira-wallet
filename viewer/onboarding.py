"""Aggregate setup readiness. Never return credential values or wallet identities."""
from kira_config import load_config, secret_values


def readiness():
    config = load_config()
    discovery = config['discovery']
    configured = discovery['provider'] != 'none'
    available = configured and bool(secret_values(config).get(discovery['key_env']))
    return {'rpc_mode': config['rpc']['mode'],
            'discovery_provider': discovery['provider'],
            'discovery_configured': configured,
            'discovery_key_available': bool(available)}
