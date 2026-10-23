"""Claude native sessions through the public Agent SDK and shared Kira transport."""
from pathlib import Path
import shutil
import sys
import time
from kira_jobs import JobError,identifier
from kira_native import NativeSession,ToolBridge


class ClaudeSession(NativeSession):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.active_cancel=None;self.pending_request=None;self.cancelled_requests=set()

    def receive_event(self,value):
        if value.get('type')=='input_cancelled':
            request=value.get('request_id');self.cancelled_requests.add(request)
            if request==self.pending_request and self.active_cancel:self.active_cancel.set()

    def start(self,cancel,instructions):
        from kira_agent import native_env
        cli=shutil.which('claude');node=shutil.which('node')
        if not cli or not node:raise JobError('cli_missing','Install Claude Code and Node.js before connecting.')
        self.bridge=ToolBridge()
        self.launch([node,str(Path(__file__).with_suffix('.mjs'))],native_env())
        self.send({'type':'initialize','cli':cli,'cwd':str(self.workspace),'model':self.config['model'],
            'retain_history':self.config['retain_history'],'thread_id':self.thread_id,'instructions':instructions,
            'python':sys.executable,'mcp':str(Path(__file__).with_name('kira_native_mcp.py')),
            'bridge_url':'http://127.0.0.1:'+str(self.bridge.server.server_port),'bridge_token':self.bridge.token},cancel)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            event=self.next(cancel,timeout=max(0,deadline-time.monotonic()))
            if event.get('type')=='ready':return
            if event.get('type')=='error':break
        raise JobError('native_unavailable','The Claude Agent SDK could not initialize the installed CLI. Check its account and configuration.')

    def run(self,message,cancel,tools,turn_id,notify,ask,instructions):
        if self.closed:raise JobError('native_stopped','Start a new conversation to reconnect Claude.')
        self.active_cancel=cancel;self.cancelled_requests.clear()
        try:
            if self.child is None:self.start(cancel,instructions)
            self.bridge.set(tools,turn_id)
            self.send({'type':'prompt','turn_id':turn_id,'message':message},cancel)
            while True:
                event=self.next(cancel,timeout=600);kind=event.get('type')
                if event.get('turn_id') not in (None,turn_id):continue
                if kind=='session':
                    self.thread_id=identifier(event['thread_id'])
                elif kind=='progress':notify(str(event.get('text','Kira is working…'))[:300])
                elif kind=='request':
                    key=identifier(event['request_id'])
                    if key in self.cancelled_requests:continue
                    self.pending_request=key
                    try:response=ask(event['request'],cancel)
                    finally:self.pending_request=None
                    self.send({'type':'respond','turn_id':turn_id,'request_id':key,'response':response},cancel)
                elif kind=='completed':
                    if event.get('success') is not True:raise JobError('native_turn_failed','The Claude task did not finish. Completed files and saved research jobs are preserved.')
                    answer=event.get('answer')
                    if not isinstance(answer,str) or not answer.strip():raise JobError('invalid_response','Claude completed without a final response.')
                    return answer
                elif kind=='error':raise JobError('native_unavailable','The Claude session could not finish. Check its account and retry.')
        except Exception:
            self.close();raise
        finally:
            self.pending_request=None;self.active_cancel=None
            if self.bridge:self.bridge.set(None)
