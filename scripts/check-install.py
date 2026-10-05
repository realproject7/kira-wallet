"""Pack and install into a fresh private directory, with no operator settings."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='kira-install-check-') as directory:
        temp=Path(directory);env={k:v for k,v in os.environ.items() if not k.startswith(('KIRA_','ALCHEMY_'))}
        def run(command,expected=0,input=None):
            result=subprocess.run(command,cwd=temp,env=env,input=input,capture_output=True,text=True,timeout=90)
            if result.returncode!=expected:raise AssertionError(f'Command {command[0]} returned {result.returncode}, expected {expected}.')
            return result.stdout
        pack=json.loads(run(['npm','pack',str(ROOT),'--ignore-scripts','--json']))[0]
        package=temp/pack['filename']
        with tarfile.open(package) as archive:
            names=archive.getnames()
            assert not any('/snapshots/' in n or '/cache/' in n or '/jobs/' in n or n.endswith(('wallets.json','session.json','.env','.kira.local.json')) for n in names)
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith(('.py','.cjs','.md','.json','.js','.html','.css')):
                    body=archive.extractfile(member).read()
                    assert str(Path.home()).encode() not in body, member.name
        run(['npm','install','--global','--ignore-scripts','--prefix',str(temp/'installation'),str(package)])
        cli=str(temp/'installation/bin/kira');data=str(temp/'portfolio')
        doctor=json.loads(run([cli,'--data-dir',data,'doctor']))
        assert doctor['public_fallback'] is True and doctor['rpc_mode']=='public' and doctor['discovery']=='none' and not doctor['discovery_key_available']
        installed=temp/'installation/lib/node_modules/kira-wallet'
        ows=json.loads(run(['node',str(installed/'ows_bridge.cjs')],input=json.dumps({'action':'create','vault':str(temp/'disposable-ows'),'name':'Install-check-wallet','passphrase':'synthetic-disposable-check'})))
        assert ows['wallet']['accounts'] and not ows['recovered'] and 'mnemonic' not in ows['wallet']
        with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
        try:
            run([cli,'--data-dir',data,'demo','--port',str(port)])
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state') as response:state=json.load(response)
            assert state['demo'] is True and len(state['wallets'])==1 and state['dashboard']['known_value_usd']==125
            first=json.loads(run([cli,'--data-dir',data,'status']))
            run([cli,'--data-dir',data,'start','--port',str(port),'--read-only','--no-open'])
            assert json.loads(run([cli,'--data-dir',data,'status']))==first
            run([cli,'--data-dir',data,'start','--port',str(port),'--no-open'],expected=1)
            run([cli,'--data-dir',str(temp/'other-portfolio'),'start','--port',str(port),'--no-open'],expected=1)
            for path in ['/.kira.local.json','/wallets.json','/.rpc.env']:
                try:urllib.request.urlopen(f'http://127.0.0.1:{port}'+path)
                except urllib.error.HTTPError as error:assert error.code==404;error.close()
                else:raise AssertionError('Private file was exposed.')
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/kira.png') as response:assert response.headers['Content-Type']=='image/png'
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/kira-logo.png') as response:assert response.headers['Content-Type']=='image/png'
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/ows-logo.svg') as response:
                assert response.headers['Content-Type']=='image/svg+xml' and b'<svg' in response.read()
            for asset in ['chat-workspace.js','chat-workspace.css','selects.js','agent.js','ows.js','agent.css','watching.js','watching-model.js','workspace.js','workspace-model.js','workspace.css','kira-research.png','kira-explain.png','kira-review.png','kira-attention.png']:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/'+asset) as response:assert response.status==200 and len(response.read())>100
            transcript='\n'.join(json.dumps(item) for item in [
                {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                {'jsonrpc':'2.0','method':'notifications/initialized'},
                {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'portfolio_read','arguments':{}}}])+'\n'
            tools=[json.loads(line) for line in run([cli,'--data-dir',data,'tools'],input=transcript).splitlines()]
            assert tools[1]['result']['structuredContent']['data']['dashboard']['known_value_usd']==125
            assert json.loads(run([cli,'--data-dir',data,'jobs','list']))==[]
            run([cli,'--data-dir',data,'stop']);run([cli,'--data-dir',data,'start','--port',str(port),'--no-open'])
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/session') as response:session=json.load(response)
            assert session['controls'] is True
            headers={'Origin':f'http://127.0.0.1:{port}','Content-Type':'application/json','X-Kira-Session':session['token']}
            mutation={'schema_version':1,'operation':'wallet.setTags','input':{'wallet':'Demo wallet','tags':['Demo wallet','Install check']},'idempotency_key':'install-check-names'}
            denied=urllib.request.Request(f'http://127.0.0.1:{port}/api/operations',data=json.dumps(mutation).encode(),headers={'Content-Type':'application/json'},method='POST')
            try:urllib.request.urlopen(denied)
            except urllib.error.HTTPError as error:assert error.code==403;error.close()
            else:raise AssertionError('An unauthenticated browser action was accepted.')
            request=urllib.request.Request(f'http://127.0.0.1:{port}/api/operations',data=json.dumps(mutation).encode(),headers=headers,method='POST')
            with urllib.request.urlopen(request) as response:job=json.load(response)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if json.loads(run([cli,'--data-dir',data,'jobs','read',job['job_id']]))['state']=='succeeded':break
                time.sleep(.1)
            else:raise AssertionError('Installed synthetic names job did not complete.')
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state') as response:changed=json.load(response)
            assert 'Install check' in changed['wallets'][0]['tags'] and changed['dashboard']['known_value_usd']==125
            run([cli,'--data-dir',data,'start','--read-only','--no-open'],expected=1)
            run([cli,'--data-dir',data,'stop']);run([cli,'--data-dir',data,'start','--port',str(port),'--read-only','--no-open'])
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/session') as response:assert json.load(response)['controls'] is False
            run([cli,'--data-dir',data,'stop']);assert json.loads(run([cli,'--data-dir',data,'status']))['status']=='stopped'
        finally:
            subprocess.run([cli,'--data-dir',data,'stop'],cwd=temp,env=env,capture_output=True,timeout=10)
        print(f'Clean package installation and lifecycle passed; {len(names)} archive members; synthetic data only.')

if __name__=='__main__':main()
