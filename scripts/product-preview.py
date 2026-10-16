"""Disposable product acceptance workspace. Never reads an operator portfolio.

Provider research workers are disabled. --native-provider exercises the installed
CLI with synthetic context only. OWS uses a separate disposable test vault.
"""
import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time
import uuid

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT),str(PROJECT/'viewer')]
from kira_cli import sample
from kira_jobs import JobStore,atomic
from kira_agent import AgentStore,capabilities,run_native
from kira_ows import OwsStore
from model import load_state
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
    parser.add_argument('--native-provider',choices=['codex','claude'])
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='kira-product-fixture-') as directory:
        root=Path(directory)
        os.environ['KIRA_DATA_DIR']=str(root)
        os.environ.pop('KIRA_CONFIG',None);os.environ.pop('KIRA_RPC_ENV',None)
        atomic(root/'wallets.json',{'schema_version':1,'wallets':[]})
        shutil.copy(PROJECT/'networks.json',root/'networks.json');sample(root)
        registry=json.loads((root/'wallets.json').read_text());registry.pop('demo')
        entry=registry['wallets'][0];entry['tags']=['Synthetic wallet']
        atomic(root/'wallets.json',registry)
        path=root/entry['latest_snapshot']['result'];snapshot=json.loads(path.read_text())
        token=snapshot['tokens'][0];token.update({'symbol':'USDC','name':'Synthetic USD Coin'})
        token['dex_pools']=[{'venue':'uniswap-v3','pool':'0x'+str(i)*40,
            'paired_tokens':[{'symbol':'USDC','address':token['token_address']},
                             {'symbol':'WETH','address':'0x'+'9'*40}],
            'reported_liquidity':{'usd':100000/i,'base':1000,'quote':20},
            'reported_price_usd':'1.25','source_url':'https://example.com/synthetic-pool/'+str(i),
            'observed_at':snapshot['compiled_at']} for i in range(3,7)]
        atomic(path,snapshot)
        atomic(root/'cache/token-images.json',{'tokens':{
            f"8453:{token['token_address']}":{'image_url':'https://fc.hunt.town/tokens/logo/8453/0x833589fcd6edb6e08f4c7c32d4f71b54bda02913/image'},
            '8453:0x'+'9'*40:{'image_url':'https://mint.club/assets/networks/ethereum@2x.png'}}})
        # All research admissions remain queued and observable. No RPC is called.
        JobStore.launch=lambda _:None
        server.ROOT=root;server.last_good=None;server.load_state=lambda:load_state(root)
        http=ThreadingHTTPServer(('127.0.0.1',args.port),FixtureHandler)
        http.controls=True;http.session_token=secrets.token_urlsafe(32)
        http.jobs=JobStore(root);http.ows=OwsStore(root,vault=root/'disposable-vault')
        def simulated(config,prompt,cancel):
            if 'Generic connection test' in prompt:return 'Kira connection ready.'
            return ('Your synthetic wallet has **100 USDC**, recorded at **$1.25** each, '
                'for **$125.00 in spot value**. Four USDC / WETH pools are recorded.\n\n'
                '| Quantity | Unit price | Spot value | Sale output |\n| --- | --- | --- | --- |\n'
                '| 100 USDC | $1.25 | $125.00 | Unknown, no execution quote |\n\n'
                'Transfer history is unavailable, so inactivity is unconfirmed. '
                'Gas, fees and price impact need an executable quote. These are synthetic test records.')
        detector=capabilities if args.native_provider else lambda:[{'id':p,'installed':True,'supported':True,'logged_in':True,'version':'fixture'} for p in ('codex','claude')]
        http.agent=AgentStore(root,runner=run_native if args.native_provider else simulated,detector=detector)
        config={'provider':args.native_provider or 'codex','model':'','scope':'portfolio','wallet':None,
                'retain_history':False,'trust_native_cli':True,'wallet_tools':True}
        turn=http.agent.start({'config':config,'idempotency_key':str(uuid.uuid4())},test=True)
        deadline=time.monotonic()+200
        while http.agent.read(turn['id'])['state']=='running' and time.monotonic()<deadline:time.sleep(.1)
        if http.agent.read(turn['id'])['state']!='succeeded':raise RuntimeError('Synthetic-context CLI readiness failed.')
        http.agent.configure(config)
        print(f'Synthetic product acceptance: http://127.0.0.1:{args.port}',flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass
        finally:http.agent.shutdown();http.server_close()

if __name__=='__main__':main()
