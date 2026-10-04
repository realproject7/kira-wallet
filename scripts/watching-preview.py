"""Isolated Watching UI fixture. All providers are synthetic; no worker is launched."""
from http.server import ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT/'viewer'))
from kira_jobs import JobStore, atomic
import server
from model import load_state

class FixtureHandler(server.Handler):
    def do_GET(self):
        if not self.local_request(): return
        if self.path == '/__fixture.js':
            self.respond((PROJECT/'scripts/fixtures/watching-provider.js').read_bytes(), 'text/javascript; charset=utf-8'); return
        if self.path == '/__fixture/status':
            self.json({'jobs':len(self.server.jobs.list())}); return
        if self.path in ('/', '/index.html'):
            html = (server.STATIC/'index.html').read_text().replace('</head>', '<script src="/__fixture.js" defer></script></head>')
            self.respond(html.encode(), 'text/html; charset=utf-8'); return
        super().do_GET()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--demo', action='store_true')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='kira-watching-fixture-') as directory:
        root=Path(directory); server.ROOT=root
        server.load_state=lambda:load_state(root)
        shutil.copy(PROJECT/'networks.json',root/'networks.json')
        registry={'schema_version':1,'wallets':[{'address':'0x'+'1'*40,'address_key':'0x'+'1'*40,'tags':['Synthetic saved wallet']}],'research_runs':[]}
        if args.demo:registry['demo']=True
        atomic(root/'wallets.json',registry)
        http=ThreadingHTTPServer(('127.0.0.1',args.port),FixtureHandler)
        http.controls=True;http.session_token=secrets.token_urlsafe(32);http.jobs=JobStore(root)
        http.jobs.launch=lambda:None  # Never start a provider-consuming research process.
        print(f'Synthetic Watching preview: http://127.0.0.1:{args.port}',flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass
        finally:http.server_close()

if __name__=='__main__':main()
