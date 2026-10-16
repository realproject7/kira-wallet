"""Private provider configuration. Public RPC is independent of discovery."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

ASSETS = Path(__file__).resolve().parent

def data_root():
    # Direct historical scripts keep their workspace. The supported CLI sets this.
    return Path(os.environ.get('KIRA_DATA_DIR', ASSETS)).expanduser().resolve()

def config_path():
    return Path(os.environ.get('KIRA_CONFIG', data_root()/'.kira.local.json')).expanduser()

def default_config():
    return {'schema_version':1,'rpc':{'mode':'public','allow_public_fallback':True,'chains':{}},
            'discovery':{'provider':'none','key_env':'ALCHEMY_API_KEY','explorers':False}}

def provider_config(config, provider, key_env):
    """One settings transition. Preserve explicit fallback and custom overrides."""
    result={**config,'rpc':{**config['rpc'],'chains':{cid:dict(row) for cid,row in config['rpc']['chains'].items()}},
            'discovery':{**config['discovery'],'provider':'alchemy' if provider=='alchemy' else 'none','key_env':key_env}}
    result['rpc']['mode']='custom' if provider=='alchemy' else 'public'
    if provider=='alchemy':
        from wallet import ALCHEMY
        for cid,network in ALCHEMY.items():
            previous=result['rpc']['chains'].get(str(cid))
            if not previous or previous.get('alchemy_network'):
                result['rpc']['chains'][str(cid)]={'url_env':key_env,'alchemy_network':network}
    return result

def load_config():
    path=config_path()
    if not path.exists():return default_config()
    try:cfg=json.loads(path.read_text())
    except (OSError,ValueError):raise ValueError('Kira configuration is unreadable or malformed.') from None
    if not isinstance(cfg,dict) or cfg.get('schema_version')!=1:raise ValueError('Unsupported Kira configuration version.')
    if set(cfg)-{'schema_version','rpc','discovery','secret_env_file'}:raise ValueError('Unknown Kira configuration fields.')
    rpc=cfg.get('rpc'); discovery=cfg.get('discovery')
    if not isinstance(rpc,dict) or rpc.get('mode') not in ('public','custom') or type(rpc.get('allow_public_fallback')) is not bool or not isinstance(rpc.get('chains'),dict):
        raise ValueError('Invalid RPC configuration.')
    if not isinstance(discovery,dict) or discovery.get('provider') not in ('none','alchemy') or type(discovery.get('explorers',False)) is not bool:
        raise ValueError('Invalid discovery configuration.')
    if set(rpc)-{'mode','allow_public_fallback','chains'} or set(discovery)-{'provider','key_env','explorers'}:raise ValueError('Unknown provider configuration fields.')
    if any(not isinstance(row,dict) or set(row)-{'url_env','alchemy_network'} for row in rpc['chains'].values()):raise ValueError('Unknown RPC endpoint fields.')
    for name in [discovery.get('key_env'),*[row.get('url_env') if isinstance(row,dict) else None for row in rpc['chains'].values()]]:
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Credentials must use valid environment references.')
    if any(not str(cid).isdigit() or int(cid)<=0 for cid in rpc['chains']):raise ValueError('Invalid RPC chain ID.')
    if 'secret_env_file' in cfg and not isinstance(cfg['secret_env_file'],str):raise ValueError('Invalid secret file reference.')
    return cfg

def secret_values(cfg=None):
    cfg=cfg or load_config();values={}
    file=os.environ.get('KIRA_RPC_ENV') or cfg.get('secret_env_file')
    if file:
        try:lines=Path(file).expanduser().read_text().splitlines()
        except FileNotFoundError:lines=[]
        except OSError:raise ValueError('Configured secret file cannot be read.') from None
        for line in lines:
            match=re.fullmatch(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*',line)
            if match:values[match[1]]=match[2].strip('\"\x27')
    refs={cfg['discovery']['key_env'],'ALCHEMY_API_KEY','ALCHEMY_CUSTOM_APY_KEY'}
    refs.update(row['url_env'] for row in cfg['rpc']['chains'].values())
    values.update({name:os.environ[name] for name in refs if name in os.environ})
    key=values.get(cfg['discovery']['key_env'])
    if cfg['discovery']['provider']=='alchemy' and key:values['ALCHEMY_CUSTOM_APY_KEY']=key
    return values

def redact(value):
    text=str(value)
    try:values=secret_values().values()
    except ValueError:values=[]
    for secret in sorted(set(values),key=len,reverse=True):
        if secret:text=text.replace(secret,'[redacted]')
    # Provider diagnostics can contain keys in paths, queries, userinfo or headers.
    text=re.sub(r'https?://[^\s\"<>]+','[RPC URL]',text)
    text=re.sub(r'(?i)(bearer\s+)[^\s,;\"<>]+',r'\1[redacted]',text)
    return re.sub(r'(?i)(authorization|api[-_]?key|bearer)([\s:=]+)[^\s,;\"<>]+',r'\1\2[redacted]',text)

def endpoints(network,cfg=None):
    cfg=cfg or load_config();rpc=cfg['rpc'];urls=[]
    if rpc['mode']=='custom':
        row=rpc['chains'].get(str(network['chain_id']))
        if row:
            try: url=secret_values(cfg).get(row['url_env'])
            except ValueError: url=None
            if url:
                if row.get('alchemy_network'):
                    if not isinstance(row['alchemy_network'],str) or not re.fullmatch(r'[a-z0-9-]+',row['alchemy_network']):raise ValueError('Invalid Alchemy network reference.')
                    url=f"https://{row['alchemy_network']}.g.alchemy.com/v2/{url}"
                try:u=urlparse(url);valid=u.scheme in ('https','http') and bool(u.hostname) and (u.scheme=='https' or u.hostname in ('localhost','127.0.0.1','::1'))
                except ValueError:valid=False
                if valid:urls.append(url)
        # New setups default to automatic fallback. Preserve an explicit existing
        # opt-out for operators who require custom providers only.
        if not rpc['allow_public_fallback']:return urls
    urls.extend(network.get('public_rpc') or [])
    return list(dict.fromkeys(urls))

def runtime():
    cfg=load_config();networks=json.loads((ASSETS/'sources/rpc-candidates.json').read_text())
    try: values=secret_values(cfg)
    except ValueError: values={}
    return {'endpoints':{str(n['chain_id']):endpoints(n,cfg) for n in networks},
            'secrets':list(values.values()),'data_root':str(data_root())}

if __name__=='__main__':
    # Internal child-process channel only. The user CLI never emits this payload.
    try:print(json.dumps(runtime()))
    except ValueError as error:
        import sys
        print(str(error),file=sys.stderr);sys.exit(1)
