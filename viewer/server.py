"""Loopback viewer with explicitly enabled, session-protected local controls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import threading
import secrets
import sys
import signal
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kira_jobs import JobStore, JobError
from kira_service import Application
from kira_ows import OwsStore
from model import ROOT, within
from token_images import IMAGE_HOSTS

STATIC=Path(__file__).resolve().parent/'static'
lock=threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def application(self):
        with lock:
            if not hasattr(self.server,'application'):
                self.server.application=Application(ROOT)
                if hasattr(self.server,'jobs'):self.server.application.jobs=self.server.jobs
                else:self.server.jobs=self.server.application.jobs
            return self.server.application

    def local_request(self):
        expected='127.0.0.1:'+str(self.server.server_port)
        # A link or desktop launcher can navigate to the public HTML shell.
        # Its subsequent data requests still require the exact local origin.
        entry_navigation=(self.command=='GET' and urlparse(self.path).path in ('/','/index.html')
                          and self.headers.get('Sec-Fetch-Dest')=='document'
                          and self.headers.get('Sec-Fetch-Mode')=='navigate')
        if self.headers.get('Host')!=expected or self.headers.get('Origin', 'http://'+expected)!='http://'+expected or (self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site') and not entry_navigation):
            self.send_error(403,'Local origin required.');return False
        return True

    def authenticated(self):
        if not getattr(self.server,'controls',False):self.send_error(403,'Local controls are disabled.');return False
        if not secrets.compare_digest(self.headers.get('X-Kira-Session','').encode(),self.server.session_token.encode()):self.send_error(403,'Local session required.');return False
        return True

    def json(self,value,status=200):
        self.respond(json.dumps(value).encode(),'application/json; charset=utf-8',status=status)

    def do_POST(self):
        if not self.local_request():return
        if not getattr(self.server,'controls',False):self.send_error(501,'Local controls are disabled.');return
        if not self.authenticated():return
        expected='http://127.0.0.1:'+str(self.server.server_port)
        if self.headers.get('Origin')!=expected:self.send_error(403,'Same origin required.');return
        if self.headers.get('Content-Type')!='application/json':self.send_error(415);return
        path=urlparse(self.path).path
        if path not in ('/api/operations','/api/ui-context','/api/ows/connect','/api/ows/create','/api/ows/disconnect'):self.send_error(404);return
        try:
            self.connection.settimeout(5)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:self.send_error(413);return
            request=json.loads(self.rfile.read(length),parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(request,dict):raise ValueError()
            if path.startswith('/api/ows/'):
                if json.loads((ROOT/'wallets.json').read_text()).get('demo'):raise JobError('demo_read_only','Use OWS only in a personal workspace.')
                if path=='/api/ows/disconnect':
                    if request:raise ValueError()
                    result=self.server.ows.disconnect()
                else:result=self.server.ows.submit(request,create=path=='/api/ows/create')
                self.json(result);return
            if path=='/api/ui-context':self.json(self.application().select(request));return
            job=self.application().submit(request)
            self.json(job,202)
        except JobError as error:self.json({'error':{'code':error.code,'message':str(error)}},409 if error.code=='idempotency_conflict' else 400)
        except (ValueError,TypeError):self.json({'error':{'code':'invalid_request','message':'Expected a valid operation request.'}},400)
        except OSError:self.json({'error':{'code':'unavailable','message':'Local storage is temporarily unavailable.'}},503)

    def do_GET(self):
        if not self.local_request():return
        path=urlparse(self.path).path
        try:
            if path=='/api/health':
                self.json({'api_version':2,'instance':os.environ.get('KIRA_INSTANCE_ID'),'read_only':not getattr(self.server,'controls',False),'controls':getattr(self.server,'controls',False)});return
            if path=='/api/session':
                self.json({'controls':getattr(self.server,'controls',False),'token':self.server.session_token if getattr(self.server,'controls',False) else None});return
            query=parse_qs(urlparse(self.path).query)
            def text(name,default=None):
                values=query.get(name,[default])
                if len(values)!=1:raise JobError('invalid_query','Use one value per query field.')
                return values[0]
            def integer(name,default=None):
                try:return int(text(name,default)) if text(name,default) is not None else None
                except (ValueError,TypeError):raise JobError('invalid_query','Expected numeric query fields.') from None
            def filters():
                testnets=text('include_testnets','1')
                if testnets not in ('0','1'):raise JobError('invalid_query','Use 0 or 1 for include_testnets.')
                return {'query':text('query',''),'chain_id':integer('chain_id'),
                    'minimum_value_usd':text('minimum_value_usd','0'),'sort':text('sort','value'),
                    'pricing':text('pricing','all'),'include_testnets':testnets=='1'}
            if path in ('/api/state','/api/status','/api/wallet','/api/token','/api/network','/api/holdings'):
                app=self.application()
                if path=='/api/state':
                    body,etag=app.views.summary()
                    if self.headers.get('If-None-Match')=='"'+etag+'"':
                        self.send_response(304);self.send_header('ETag','"'+etag+'"');self.send_header('Cache-Control','no-cache');self.end_headers();return
                    self.respond(body,'application/json; charset=utf-8',etag);return
                if path=='/api/status':
                    self.json(app.status() if getattr(self.server,'controls',False) else {'schema_version':1,'data_revision':app.views.data_revision(),'jobs_revision':'','active_job_count':0,'active_jobs':[]});return
                if path=='/api/wallet':result=app.views.wallet(text('wallet'),integer('offset',0),integer('limit',100),**filters())
                elif path=='/api/token':result=app.views.token(integer('chain_id'),text('address'))
                elif path=='/api/network':result=app.views.network(integer('chain_id'))
                else:result=app.views.holdings(integer('offset',0),integer('limit',100),**filters())
                self.json(result);return
            if path.startswith('/api/jobs') or path in ('/api/job-history','/api/onboarding','/api/snapshots','/api/snapshot','/api/compare','/api/settings','/api/ows'):
                if not self.authenticated():return
                app=self.application()
                if path=='/api/jobs':result=app.jobs.page(integer('offset',0),integer('limit',50))['jobs']
                elif path=='/api/job-history':result=app.jobs.page(integer('offset',0),integer('limit',20),text('state','all'),text('wallet'))
                elif path.startswith('/api/jobs/'):result=app.jobs.get(path.removeprefix('/api/jobs/'))
                elif path=='/api/snapshots':result=app.jobs.snapshots(text('wallet',''))
                elif path=='/api/snapshot':result=app.jobs.snapshot(text('id',''))
                elif path=='/api/compare':result=app.jobs.compare(text('before',''),text('after',''))
                elif path=='/api/ows':result={'available':False,'wallets':[],'connection':None,'note':'OWS connections are available in your personal workspace.'} if json.loads((ROOT/'wallets.json').read_text()).get('demo') else self.server.ows.status()
                elif path=='/api/onboarding':
                    from onboarding import readiness
                    result=readiness()
                elif path=='/api/settings':result=app.settings()
                else:self.send_error(404);return
                self.json(result);return
            if path.startswith('/api/report/'):
                key=path.removeprefix('/api/report/')
                registry=json.loads((ROOT/'wallets.json').read_text())
                entry=next((w for w in registry['wallets'] if w['address_key']==key),None)
                if not entry or not entry.get('latest_snapshot',{}).get('report'):self.send_error(404);return
                body=within(ROOT,entry['latest_snapshot']['report']).read_bytes()
                self.respond(body,'text/plain; charset=utf-8');return
            files={**{f'/explorers/{name}':f'explorers/{name}' for name in ('etherscan.png',)},**{f'/venues/{name}':f'venues/{name}' for name in ('mintclub.png','uniswap.svg','aerodrome.svg')},'/alchemy-guide.html':'alchemy-guide.html','/alchemy-guide.css':'alchemy-guide.css','/alchemy-create-app.png':'alchemy-create-app.png','/':'index.html','/index.html':'index.html','/app.js':'app.js','/jobs.js':'jobs.js','/workspace.js':'workspace.js','/workspace-model.js':'workspace-model.js','/workspace.css':'workspace.css','/ows.js':'ows.js','/selects.js':'selects.js','/report.js':'report.js','/report.css':'report.css','/watching.js':'watching.js','/watching-model.js':'watching-model.js','/style.css':'style.css','/favicon.svg':'favicon.svg','/kira-logo.png':'kira-logo.png','/ows-logo.svg':'ows-logo.svg'}
            if path not in files:self.send_error(404);return
            file=STATIC/files[path]
            content={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','svg':'image/svg+xml','png':'image/png'}[file.suffix[1:]]
            self.respond(file.read_bytes(),content)
        except JobError as error:self.json({'error':{'code':error.code,'message':str(error)}},400)
        except JobError as error:self.json({'error':{'code':error.code,'message':str(error)}},400)
        except (ValueError,OSError,TypeError,KeyError):self.send_error(503,'Research data is being updated. Try again shortly.')

    def respond(self,body,content,etag=None,status=200):
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        image_origins=' '.join('https://'+host for host in IMAGE_HOSTS)
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: "+image_origins+"; connect-src 'self'; frame-ancestors 'none'")
        if etag:self.send_header('ETag','"'+etag+'"')
        self.end_headers();self.wfile.write(body)

    def log_message(self,*args): pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--controls',action='store_true');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.controls=args.controls;server.session_token=secrets.token_urlsafe(32)
    server.daemon_threads=True
    server.application=Application(ROOT);server.jobs=server.application.jobs
    if args.controls:server.ows=OwsStore(ROOT)
    if args.controls:server.jobs.reconcile_idle()
    def stop_viewer(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop_viewer)
    print(f'Wallet viewer: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
