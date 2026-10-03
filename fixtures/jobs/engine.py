"""Deterministic financial fixtures and process failures, with no network."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from kira_jobs import atomic
root=Path(os.environ['KIRA_DATA_DIR']);folder=root/os.environ['KIRA_JOB_SNAPSHOT']
lock=os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']),'a');fcntl.flock(lock,fcntl.LOCK_EX)
with (root/'invocations').open('a') as file:file.write('engine\n')
registry=json.loads((root/'wallets.json').read_text());wallet=registry['wallets'][0]
atomic(folder/'run.json',{'wallet_address':wallet['address'],'status':'running'})
print(json.dumps({'stage':'chain','chain_id':1,'block_number':123,'endpoint_index':0,'status':'partial','registry':10,'checked':8,'held':1}),flush=True)
if sys.argv[1]=='wait':
    subprocess.Popen([sys.executable,'-c',"import signal,time,pathlib,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);p=pathlib.Path(sys.argv[1]);\nwhile True: p.write_text(str(time.time()));time.sleep(.05)",str(root/'heartbeat')])
    time.sleep(30)
else:
    time.sleep(.6)
    atomic(folder/'results.json',{'schema_version':1,'wallet_address':wallet['address'],'compiled_at':'2026-10-03T00:00:00Z','status':'completed_with_coverage_gaps','coverage':[],'tokens':[]})
    wallet['latest_snapshot']={'directory':os.environ['KIRA_JOB_SNAPSHOT']};atomic(root/'wallets.json',registry)
    if sys.argv[1]=='publish-wait':
        atomic(root/'published-marker',{'published':True});time.sleep(30)
    atomic(folder/'run.json',{'wallet_address':wallet['address'],'completed_at':'2026-10-03T00:00:00Z'})
    print(json.dumps({'stage':'published','status':'completed_with_coverage_gaps'}),flush=True)
