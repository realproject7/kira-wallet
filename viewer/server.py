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
from kira_agent import AgentStore, read_history_file
from kira_ows import OwsStore
from model import ROOT, load_state, within
from token_images import IMAGE_HOSTS

STATIC=Path(__file__).resolve().parent/'static'
lock=threading.Lock()
last_good=None

class Handler(BaseHTTPRequestHandler):
    def local_request(self):
        expected='127.0.0.1:'+str(self.server.server_port)
        if self.headers.get('Host')!=expected or self.headers.get('Origin', 'http://'+expected)!='http://'+expected or self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site'):
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
        if path not in ('/api/operations','/api/agent/test','/api/agent/settings','/api/chat/send','/api/chat/reset','/api/chat/cancel','/api/chat/open','/api/ows/connect','/api/ows/create','/api/ows/disconnect'):self.send_error(404);return
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
            if path!='/api/operations':
                if path in ('/api/agent/test','/api/chat/send') and json.loads((ROOT/'wallets.json').read_text()).get('demo'):
                    raise JobError('demo_read_only','The synthetic demo does not contact model services. Run kira setup with your personal data directory.')
                if path=='/api/agent/test':result=self.server.agent.start(request,test=True)
                elif path=='/api/agent/settings':result=self.server.agent.configure(request)
                elif path=='/api/chat/send':result=self.server.agent.start(request)
                elif path=='/api/chat/open':
                    if set(request)!={'id'}:raise ValueError()
                    result=self.server.agent.open_history(request['id'])
                elif path=='/api/chat/reset':
                    if request:raise ValueError()
                    result=self.server.agent.reset()
                else:
                    if set(request)!={'id'}:raise ValueError()
                    result=self.server.agent.cancel(request['id'])
                self.json(result,202 if path in ('/api/agent/test','/api/chat/send') else 200);return
            if json.loads((ROOT/'wallets.json').read_text()).get('demo'):
                operation=request.get('operation')
                if operation=='job.resume' and isinstance(request.get('input'),dict):
                    operation=self.server.jobs.get(request['input'].get('job_id'))['operation']
                if operation in ('wallet.add','wallet.refresh','prices.refresh'):
                    raise JobError('demo_read_only','Sample research cannot contact providers. Use a separate personal data directory.')
            job=self.server.jobs.submit(request)
            if job['state']=='queued':self.server.jobs.launch()
            self.json(job,202)
        except JobError as error:self.json({'error':{'code':error.code,'message':str(error)}},409 if error.code=='idempotency_conflict' else 400)
        except (ValueError,TypeError):self.json({'error':{'code':'invalid_request','message':'Expected a valid operation request.'}},400)
        except OSError:self.json({'error':{'code':'unavailable','message':'Local storage is temporarily unavailable.'}},503)

    def do_GET(self):
        global last_good
        if not self.local_request():return
        path=urlparse(self.path).path
        try:
            if path=='/api/health':
                self.json({'instance':os.environ.get('KIRA_INSTANCE_ID'),'read_only':not getattr(self.server,'controls',False),'controls':getattr(self.server,'controls',False)});return
            if path=='/api/session':
                self.json({'controls':getattr(self.server,'controls',False),'token':self.server.session_token if getattr(self.server,'controls',False) else None});return
            if path.startswith('/api/jobs') or path.startswith('/api/chat/turn/') or path in ('/api/agent','/api/chat','/api/chat/history','/api/onboarding','/api/snapshots','/api/snapshot','/api/compare','/api/settings','/api/ows'):
                if not self.authenticated():return
                query=parse_qs(urlparse(self.path).query)
                if path in ('/api/agent','/api/chat'):
                    if json.loads((ROOT/'wallets.json').read_text()).get('demo'):
                        self.json({'config':None,'providers':[],'conversation_id':None,'messages':[],'active_turn':None})
                    else:self.json(self.server.agent.status(query.get('recheck')==['1']))
                elif path.startswith('/api/chat/turn/'):self.json(self.server.agent.read(path.removeprefix('/api/chat/turn/')))
                elif path=='/api/chat/history':self.json(self.server.agent.history(query.get('id',[None])[0]))
                elif path=='/api/jobs':self.json(self.server.jobs.list())
                elif path.startswith('/api/jobs/'):self.json(self.server.jobs.get(path.removeprefix('/api/jobs/')))
                elif path=='/api/snapshots':self.json(self.server.jobs.snapshots(query.get('wallet',[''])[0]))
                elif path=='/api/snapshot':self.json(self.server.jobs.snapshot(query.get('id',[''])[0]))
                elif path=='/api/compare':self.json(self.server.jobs.compare(query.get('before',[''])[0],query.get('after',[''])[0]))
                elif path=='/api/ows':
                    self.json({'available':False,'wallets':[],'connection':None,'note':'OWS connections are available in your personal workspace.'} if json.loads((ROOT/'wallets.json').read_text()).get('demo') else self.server.ows.status())
                elif path=='/api/onboarding':
                    from onboarding import readiness
                    self.json(readiness())
                elif path=='/api/settings':
                    from kira_config import load_config
                    config=load_config();self.json({key:config[key] for key in ('schema_version','rpc','discovery')})
                else:self.send_error(404)
                return
            if path=='/api/state':
                with lock:
                    try:
                        _,body,etag=load_state();last_good=(body,etag)
                    except (json.JSONDecodeError,FileNotFoundError):
                        if last_good is None:raise
                        body,etag=last_good
                if self.headers.get('If-None-Match')=='"'+etag+'"':
                    self.send_response(304);self.send_header('ETag','"'+etag+'"');self.send_header('Cache-Control','no-cache');self.end_headers();return
                self.respond(body,'application/json; charset=utf-8',etag);return
            if path.startswith('/api/report/'):
                key=path.removeprefix('/api/report/')
                registry=json.loads((ROOT/'wallets.json').read_text())
                entry=next((w for w in registry['wallets'] if w['address_key']==key),None)
                if not entry or not entry.get('latest_snapshot',{}).get('report'):self.send_error(404);return
                body=within(ROOT,entry['latest_snapshot']['report']).read_bytes()
                self.respond(body,'text/plain; charset=utf-8');return
            files={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/jobs.js':'jobs.js','/workspace.js':'workspace.js','/workspace-model.js':'workspace-model.js','/workspace.css':'workspace.css','/agent.js':'agent.js','/ows.js':'ows.js','/agent.css':'agent.css','/chat-workspace.css':'chat-workspace.css','/chat-workspace.js':'chat-workspace.js','/selects.js':'selects.js','/markdown.js':'markdown.js','/report.js':'report.js','/report.css':'report.css','/watching.js':'watching.js','/watching-model.js':'watching-model.js','/style.css':'style.css','/favicon.svg':'favicon.svg','/kira.png':'kira.png','/kira-logo.png':'kira-logo.png',**{f'/kira-{pose}.png':f'kira-{pose}.png' for pose in ('research','explain','review','attention')}}
            if path not in files:self.send_error(404);return
            file=STATIC/files[path]
            content={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','svg':'image/svg+xml','png':'image/png'}[file.suffix[1:]]
            self.respond(file.read_bytes(),content)
        except JobError as error:self.json({'error':{'code':error.code,'message':str(error)}},400)
        except (ValueError,OSError,json.JSONDecodeError):self.send_error(503,'Research data is being updated. Try again shortly.')

    def respond(self,body,content,etag=None,status=200):
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        image_origins=' '.join('https://'+host for host in IMAGE_HOSTS)
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: "+image_origins+"; connect-src 'self'; frame-ancestors 'none'")
        if etag:self.send_header('ETag','"'+etag+'"')
        self.end_headers();self.wfile.write(body)

    def log_message(self,*args): pass

def restore_upgrade_chat(agent,root):
    """Consume a private one-use upgrade receipt only after validating exact permissions."""
    resume=Path(root)/'.kira-agent-resume.json'
    agent.restore_runtime(read_history_file(resume,private=True))
    resume.unlink()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--controls',action='store_true');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.controls=args.controls;server.session_token=secrets.token_urlsafe(32)
    if args.controls:server.jobs=JobStore(ROOT);server.agent=AgentStore(ROOT);server.ows=OwsStore(ROOT)
    if args.controls and os.environ.get('KIRA_CHAT_RESUME')=='1':restore_upgrade_chat(server.agent,ROOT)
    def stop_viewer(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop_viewer)
    print(f'Wallet viewer: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if args.controls:server.agent.shutdown()
        server.server_close()
