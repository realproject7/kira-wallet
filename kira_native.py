"""Native Codex sessions with scoped Kira MCP tools and interactive approvals."""
from __future__ import annotations
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import select
import stat
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from kira_jobs import JobError


def workspace_path(root,conversation):
    from kira_jobs import identifier
    identifier(conversation)
    root=Path(root).resolve()
    key=hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return root.parent/'kira-agent-workspaces'/key/conversation


def artifacts(root,conversation):
    workspace=workspace_path(root,conversation)
    if not workspace.is_dir() or any(p.is_symlink() for p in (workspace,workspace.parent,workspace.parent.parent)):return []
    result=[];count=0
    for folder,dirs,files in os.walk(workspace,followlinks=False):
        count+=1
        if count>200:return result
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(folder)/d).is_symlink()][:50]
        for name in files:
            count+=1
            if count>200:return result
            path=Path(folder)/name
            try:
                info=path.lstat()
                if name.startswith('.') or not stat.S_ISREG(info.st_mode) or info.st_size>20_000_000:continue
                result.append({'path':str(path.relative_to(workspace)),'size':info.st_size})
            except OSError:continue
    return result


def read_artifact(root,conversation,name):
    if not isinstance(name,str) or len(name)>2000 or Path(name).is_absolute() or '..' in Path(name).parts:raise JobError('invalid_file','Choose a file in this conversation workspace.')
    workspace=workspace_path(root,conversation)
    # Walk open directories so concurrent symlink replacement cannot redirect a download.
    parent=Path(root).resolve().parent
    descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        parts=(*workspace.relative_to(parent).parts,*Path(name).parts)
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=descriptor)
    except OSError:
        raise JobError('invalid_file','Choose a regular file in this conversation workspace.') from None
    finally:os.close(descriptor)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>20_000_000:raise JobError('invalid_file','Choose a regular file under 20 MB.')
        return stream.read(20_000_001)


def tool_descriptors():
    from kira_research_tools import CATALOG
    result=[]
    for tool in CATALOG:
        if tool['name']=='records_read':continue
        properties={}
        for name,description in {**tool['arguments'],**tool.get('optional_arguments',{})}.items():
            kind='integer' if name in ('chain_id','offset','limit') else 'string'
            properties[name]={'type':kind,'description':description}
        result.append({'name':tool['name'],'description':tool['description'],
            'inputSchema':{'type':'object','properties':properties,'required':list(tool['arguments']),'additionalProperties':False},
            'annotations':{'readOnlyHint':not tool['name'].endswith('_refresh'),'destructiveHint':False}})
    return result


class ToolBridge:
    """Private per-session transport; all domain work stays in ResearchTools."""
    def __init__(self):
        self.token=secrets.token_urlsafe(32);self.tools=None;self.turn=None;self.lock=threading.RLock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                try:
                    if self.path!='/' or self.headers.get('Origin') or not secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+owner.token):
                        self.send_error(403);return
                    self.connection.settimeout(5)
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=65536:raise ValueError()
                    value=json.loads(self.rfile.read(length))
                    with owner.lock:
                        tools,turn=owner.tools,owner.turn
                    if tools is None:raise JobError('inactive_turn','Wallet tools are unavailable outside an active authorized turn.')
                    name=value['name'];arguments=value.get('arguments',{})
                    # Identical mutations within a turn share the existing durable receipt.
                    key=str(uuid.uuid5(uuid.UUID(turn),json.dumps([name,arguments],sort_keys=True)))
                    with tools.guard():result=tools.call(name,arguments,key)
                    body={'result':result}
                except JobError as error:body={'error':{'code':error.code,'message':str(error)}}
                except Exception:body={'error':{'code':'invalid_tool','message':'The wallet tool request could not be completed.'}}
                encoded=json.dumps(body,allow_nan=False).encode()
                if len(encoded)>2_000_000:encoded=b'{"error":{"code":"result_too_large","message":"Use a more focused wallet query."}}'
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers()
                try:self.wfile.write(encoded)
                except OSError:pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def set(self,tools,turn=None):
        with self.lock:self.tools=tools;self.turn=turn

    def close(self):
        self.set(None);self.server.shutdown();self.server.server_close()


class NativeSession:
    def __init__(self,root,conversation,config,thread_id=None):
        self.root=Path(root);self.config=config;self.thread_id=thread_id;self.child=None;self.bridge=None
        self.events=queue.Queue(maxsize=256);self.sequence=0;self.closed=False
        self.reader=None;self.close_lock=threading.Lock()
        # Generated files are separate from wallet records and credential references.
        self.workspace=workspace_path(self.root,conversation)
        self.workspace.mkdir(parents=True,exist_ok=True,mode=0o700)

    def send(self,message,cancel=None):
        body=memoryview((json.dumps(message,ensure_ascii=False)+'\n').encode())
        deadline=time.monotonic()+30
        while body:
            if cancel is not None and cancel.is_set():raise JobError('cancelled','Response stopped.')
            if self.closed:raise JobError('native_stopped','The native agent stopped.')
            if time.monotonic()>deadline:raise JobError('native_timeout','The native agent stopped accepting requests.')
            try:
                if select.select([], [self.child.stdin], [], .1)[1]:body=body[os.write(self.child.stdin.fileno(),body):]
            except BlockingIOError:continue
            except (OSError,ValueError):raise JobError('native_stopped','The native agent stopped accepting requests.') from None

    def next(self,cancel,timeout=120):
        started=time.monotonic()
        while True:
            if cancel.is_set():raise JobError('cancelled','Response stopped. Completed files remain in the workspace.')
            try:
                value=self.events.get(timeout=.1)
                if value is None:raise JobError('native_stopped','The native agent stopped. Retry or start a new conversation.')
                return value
            except queue.Empty:
                if time.monotonic()-started>timeout:raise JobError('native_timeout','The native agent stopped reporting progress. Retry or stop the task.')

    def rpc(self,method,params,cancel,timeout=120):
        self.sequence+=1;key='kira-'+str(self.sequence)
        self.send({'id':key,'method':method,'params':params},cancel)
        deadline=time.monotonic()+timeout
        while True:
            if time.monotonic()>=deadline:raise JobError('native_timeout','The native agent did not acknowledge the request.')
            value=self.next(cancel,timeout=max(0,deadline-time.monotonic()))
            if value.get('id')==key and 'method' not in value:
                if 'error' in value:raise JobError('native_request_failed','The native agent could not start this request. Check its account and configuration.')
                return value.get('result',{})
            if 'id' in value and 'method' in value:
                self.send({'id':value['id'],'error':{'code':-32601,'message':'No active turn is available to approve this request.'}},cancel)

    def receive_event(self,value):
        """Provider adapters may observe cancellation before a pending input returns."""
        pass

    def launch(self,command,env):
        self.child=subprocess.Popen(command,cwd=self.workspace,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,start_new_session=True)
        os.set_blocking(self.child.stdin.fileno(),False)
        os.set_blocking(self.child.stdout.fileno(),False)
        def receive():
            buffer=b''
            try:
                while not self.closed:
                    if not select.select([self.child.stdout],[],[],.1)[0]:continue
                    chunk=os.read(self.child.stdout.fileno(),65536)
                    if not chunk:break
                    buffer+=chunk
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1)
                        if len(line)>2_000_000:raise ValueError()
                        value=json.loads(line)
                        if not isinstance(value,dict):raise ValueError()
                        self.receive_event(value)
                        while not self.closed:
                            try:self.events.put(value,timeout=.1);break
                            except queue.Full:pass
                    if len(buffer)>2_000_000:break
            except (OSError,ValueError):pass
            finally:
                try:self.events.put_nowait(None)
                except queue.Full:pass
        self.reader=threading.Thread(target=receive,daemon=True);self.reader.start()

    def start(self,cancel,instructions):
        from kira_agent import native_env
        path=shutil.which('codex')
        if not path:raise JobError('cli_missing','Install the official Codex CLI first.')
        self.bridge=ToolBridge()
        self.launch([path,'app-server'],native_env())
        self.rpc('initialize',{'clientInfo':{'name':'kira_wallet','version':'0.1.20'},'capabilities':{'experimentalApi':False}},cancel)
        self.send({'method':'initialized'})
        bridge=self.bridge
        config={'web_search':'live','features.code_mode_host':True,
            'mcp_servers.kira_wallet':{'command':sys.executable,'args':[str(Path(__file__).with_name('kira_native_mcp.py'))],
                'env':{'KIRA_TOOL_URL':'http://127.0.0.1:'+str(bridge.server.server_port),'KIRA_TOOL_TOKEN':bridge.token},'required':True}}
        params={'cwd':str(self.workspace),'approvalPolicy':'on-request','approvalsReviewer':'user','sandbox':'workspace-write',
            'developerInstructions':instructions,'config':config,'ephemeral':not self.config['retain_history']}
        if self.config['model']:params['model']=self.config['model']
        if self.thread_id:
            params.pop('ephemeral');params.update(threadId=self.thread_id,excludeTurns=True)
            response=self.rpc('thread/resume',params,cancel)
        else:response=self.rpc('thread/start',params,cancel)
        self.thread_id=response['thread']['id']

    def run(self,message,cancel,tools,turn_id,notify,ask,instructions):
        if self.closed:raise JobError('native_stopped','Start a new conversation to reconnect the native agent.')
        try:
            if self.child is None:self.start(cancel,instructions)
            self.bridge.set(tools,turn_id)
            response=self.rpc('turn/start',{'threadId':self.thread_id,'input':[{'type':'text','text':message}]},cancel)
            native_turn=response['turn']['id'];finals=[];comments=[];items={}
            while True:
                event=self.next(cancel,timeout=600)
                method=event.get('method','');params=event.get('params',{})
                foreign=params.get('threadId') not in (None,self.thread_id) or params.get('turnId') not in (None,native_turn)
                if foreign:
                    if 'id' in event and method:self.send({'id':event['id'],'error':{'code':-32602,'message':'This request is outside the active turn.'}},cancel)
                    continue
                if 'id' in event and method:
                    if method=='item/fileChange/requestApproval':params={**params,'changes':items.get(params.get('itemId'),{}).get('changes',[])}
                    result=self.approval(method,params,ask,cancel)
                    self.send({'id':event['id'],'result':result},cancel)
                    continue
                if params.get('turnId') and params['turnId']!=native_turn:continue
                if method=='item/started':
                    item=params.get('item',{});kind=item.get('type','');items[item.get('id')]=item
                    labels={'webSearch':'Searching the web…','commandExecution':'Running a command…','fileChange':'Updating workspace files…','mcpToolCall':'Using connected tools…','agentMessage':'Writing a response…','reasoning':'Working through the request…'}
                    notify(labels.get(kind,'Kira is working…'))
                elif method=='item/completed':
                    item=params.get('item',{})
                    if item.get('type')=='agentMessage':
                        (finals if item.get('phase')=='final_answer' else comments).append(item.get('text',''))
                elif method=='turn/completed':
                    turn=params.get('turn',{})
                    if turn.get('id')!=native_turn:continue
                    if turn.get('status')!='completed':
                        raise JobError('native_turn_failed','The native task did not finish. Completed files and saved research jobs are preserved.')
                    answer='\n\n'.join(finals) or (comments[-1] if comments else '')
                    if not answer:raise JobError('invalid_response','The native agent completed without a final response.')
                    return answer
        except Exception:
            self.close();raise
        finally:
            if self.bridge:self.bridge.set(None)

    @staticmethod
    def approval(method,params,ask,cancel):
        if method in ('item/commandExecution/requestApproval','item/fileChange/requestApproval'):
            result=ask({'kind':'approval','method':method,'details':params},cancel)
            decision=result.get('decision','decline')
            if decision not in ('accept','decline'):decision='decline'
            available=params.get('availableDecisions')
            if available and decision not in available:decision='decline'
            return {'decision':decision}
        if method=='item/tool/requestUserInput':
            if any(q.get('isSecret') for q in params.get('questions',[])):raise JobError('secret_input','Complete secret entry through the native integration, outside chat.')
            result=ask({'kind':'input','method':method,'details':params},cancel)
            answers=result.get('answers',{})
            return {'answers':{q['id']:{'answers':[str(answers.get(q['id'],''))[:8000]]} for q in params.get('questions',[])}}
        if method=='item/permissions/requestApproval':
            result=ask({'kind':'permissions','method':method,'details':params},cancel)
            return {'permissions':params.get('permissions',{}) if result.get('decision')=='accept' else {},'scope':'turn'}
        if method=='mcpServer/elicitation/request':
            # Preserve the approval boundary for integrations requiring unsupported forms.
            ask({'kind':'notice','method':method,'details':{'message':'This integration needs an external input form. It was not approved. Use its native client to complete setup.'}},cancel)
            return {'action':'decline','content':None}
        raise JobError('unsupported_native_request','This native integration requested an unsupported interaction. No approval was granted.')

    def close(self):
        with self.close_lock:
            if self.closed:return
            self.closed=True
            if self.bridge:self.bridge.set(None)
            if self.child:
                try:os.killpg(self.child.pid,signal.SIGTERM)
                except OSError:pass
                try:self.child.wait(timeout=2)
                except subprocess.TimeoutExpired:pass
                # An exited leader can leave descendants holding the output pipe open.
                try:os.killpg(self.child.pid,signal.SIGKILL)
                except OSError:pass
                try:self.child.wait(timeout=2)
                except subprocess.TimeoutExpired:pass
                if self.reader:self.reader.join(timeout=1)
                for stream in (self.child.stdin,self.child.stdout):
                    try:stream.close()
                    except OSError:pass
            if self.bridge:self.bridge.close();self.bridge=None
