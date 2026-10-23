"""Disposable product acceptance workspace. Never reads an operator portfolio.

Provider research workers are disabled. Human controls use synthetic records.
OWS uses a separate disposable test vault.
"""
import argparse
from copy import deepcopy
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT),str(PROJECT/'viewer')]
from kira_cli import sample, initialize
from kira_jobs import JobStore,atomic
from kira_ows import OwsStore
from kira_service import Application
import server

class FixtureHandler(server.Handler):
    def local_request(self):
        # Browser automation marks document navigation cross-site. Only this
        # synthetic HTML entry point is relaxed; API guards remain production code.
        if (self.command=='GET' and self.path=='/' and
                self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and
                not self.headers.get('Origin')):return True
        return super().local_request()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8801)
    parser.add_argument('--wallet-count',type=int,choices=range(1,13),default=1,
                        help='Number of independent synthetic wallets (1 to 12).')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='kira-product-fixture-') as directory:
        root=Path(directory)
        os.environ['KIRA_DATA_DIR']=str(root)
        os.environ.pop('KIRA_CONFIG',None);os.environ.pop('KIRA_RPC_ENV',None)
        initialize(root)
        shutil.copy(PROJECT/'networks.json',root/'networks.json');sample(root)
        registry=json.loads((root/'wallets.json').read_text());registry.pop('demo')
        entry=registry['wallets'][0];entry['tags']=['Synthetic wallet']
        path=root/entry['latest_snapshot']['result'];snapshot=json.loads(path.read_text())
        snapshot['tags']=entry['tags'][:]
        token=snapshot['tokens'][0];token.update({'symbol':'USDC','name':'Synthetic USD Coin'})
        token['dex_pools']=[{'venue':'uniswap-v3','pool':'0x'+str(i)*40,
            'paired_tokens':[{'symbol':'USDC','address':token['token_address']},
                             {'symbol':'WETH','address':'0x'+'9'*40}],
            'reported_liquidity':{'usd':100000/i,'base':1000,'quote':20},
            'reported_price_usd':'1.25','source_url':'https://example.com/synthetic-pool/'+str(i),
            'observed_at':snapshot['compiled_at']} for i in range(3,7)]
        atomic(path,snapshot)
        prices=json.loads((path.parent/'market-prices.json').read_text())
        for index in range(2,args.wallet_count+1):
            address=f'0x{index:040x}';folder=f'snapshots/synthetic-{index}/initial'
            wallet=deepcopy(entry);wallet.update(address=address,address_key=address,
                tags=[f'Synthetic wallet {index}'],
                latest_snapshot={'directory':folder,'result':folder+'/results.json'})
            observation=deepcopy(snapshot)
            observation.update(wallet_address=address,tags=wallet['tags'][:])
            observation['tokens'][0]['wallet_balance']=str(100*index)
            atomic(root/folder/'results.json',observation)
            atomic(root/folder/'market-prices.json',deepcopy(prices))
            registry['wallets'].append(wallet)
        atomic(root/'wallets.json',registry)
        atomic(root/'cache/token-images.json',{'tokens':{
            f"8453:{token['token_address']}":{'image_url':'https://fc.hunt.town/tokens/logo/8453/0x833589fcd6edb6e08f4c7c32d4f71b54bda02913/image'},
            '8453:0x'+'9'*40:{'image_url':'https://mint.club/assets/networks/ethereum@2x.png'}}})
        from kira_config import default_config,provider_config
        cfg=provider_config(default_config(),'alchemy','KIRA_FIXTURE_KEY');cfg['secret_env_file']=str(root/'fixture.env')
        atomic(root/'.kira.local.json',cfg);(root/'fixture.env').write_text('KIRA_FIXTURE_KEY=synthetic-preview-only\n')
        # All research admissions remain queued and observable. No RPC is called.
        JobStore.launch=lambda _:None
        server.ROOT=root
        http=ThreadingHTTPServer(('127.0.0.1',args.port),FixtureHandler)
        http.controls=True;http.session_token=secrets.token_urlsafe(32)
        http.daemon_threads=True
        http.application=Application(root);http.jobs=http.application.jobs
        http.ows=OwsStore(root,vault=root/'disposable-vault')
        print(f'Synthetic product acceptance: http://127.0.0.1:{args.port}',flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass
        finally:http.server_close()

if __name__=='__main__':main()
