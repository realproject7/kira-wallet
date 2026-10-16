"""Bounded native model metadata. No inference, threads or credential copying."""
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

MODEL = re.compile(r'[a-zA-Z0-9._:/-]{1,100}')

def clean_catalog(rows):
    result=[]; seen=set()
    if not isinstance(rows,list):return result
    for row in rows[:100]:
        if not isinstance(row,dict) or row.get('hidden'):continue
        model=row.get('model') or row.get('id')
        if not isinstance(model,str) or not MODEL.fullmatch(model) or model in seen:continue
        name=row.get('displayName') or model
        if not isinstance(name,str):name=model
        name=' '.join(name.split())[:100]
        result.append({'id':model,'name':name or model});seen.add(model)
        if len(result)==40:break
    return result

def codex_catalog(path, env, *, timeout=8):
    from kira_agent import CODEX_DISABLED
    argv=[path,'app-server','--listen','stdio://','-c','analytics.enabled=false',
          '-c','history.persistence="none"','-c','mcp_servers={}', '-c','model_provider="openai"']
    for feature in CODEX_DISABLED:argv+=['-c',f'features.{feature}=false']
    with tempfile.TemporaryDirectory(prefix='kira-models-') as cwd:
        child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                               cwd=cwd,env=env,start_new_session=True)
        selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
        def send(value):
            child.stdin.write((json.dumps(value)+'\n').encode());child.stdin.flush()
        try:
            send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'kira_model_picker','version':'0.1.5'}}})
            deadline=time.monotonic()+timeout;buffer=b'';received=0;requested=False
            while time.monotonic()<deadline:
                for key,_ in selector.select(min(.2,max(0,deadline-time.monotonic()))):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk:raise ValueError('Catalog ended.')
                    received+=len(chunk)
                    if received>262144:raise ValueError('Catalog too large.')
                    buffer+=chunk
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1)
                        try:message=json.loads(line)
                        except ValueError:continue
                        if not isinstance(message,dict):continue
                        if message.get('id')==1 and not requested:
                            if 'error' in message:raise ValueError('Initialization failed.')
                            requested=True
                            send({'method':'initialized'})
                            send({'id':2,'method':'model/list','params':{'limit':100,'includeHidden':False}})
                        elif message.get('id')==2 and requested:
                            if 'error' in message:raise ValueError('Catalog unavailable.')
                            result=message.get('result')
                            return clean_catalog(result.get('data')) if isinstance(result,dict) else []
            raise TimeoutError('Catalog timed out.')
        finally:
            selector.close()
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                child.wait()
            child.stdin.close();child.stdout.close()

def catalog(provider):
    from kira_agent import native_env
    if provider=='claude':
        return {'models':[{'id':'sonnet','name':'Sonnet'}, {'id':'opus','name':'Opus'}, {'id':'haiku','name':'Haiku'}],
                'note':'Claude CLI model choices. Check a response to verify access for your account.'}
    if provider!='codex':raise ValueError('Unsupported provider.')
    try:
        path=shutil.which('codex')
        models=codex_catalog(path,native_env()) if path else []
    except (OSError,ValueError,TypeError,TimeoutError):models=[]
    return {'models':models,'note':'CLI catalog choices. Check a response to verify account access.' if models else
            'Model choices are unavailable. Use the default model, recheck, or enter an ID under Advanced.'}
