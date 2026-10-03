"""Start the local viewer in the background, or reuse an existing instance."""
from pathlib import Path
import subprocess
import time
import urllib.request
import json
import sys

root=Path(__file__).resolve().parent
url='http://127.0.0.1:8765'
def running():
    try:
        with urllib.request.urlopen(url+'/api/state',timeout=1) as response:
            data=json.load(response)
            return 'wallets' in data and data.get('currency')=='USD'
    except Exception:return False

if running():print(url);sys.exit(0)
with (root/'server.log').open('ab') as log:
    process=subprocess.Popen([sys.executable,str(root/'server.py'),'--port','8765'],stdout=log,stderr=log,start_new_session=True)
    (root/'server.pid').write_text(str(process.pid)+'\n')
for _ in range(20):
    if running():print(url);break
    if process.poll() is not None:raise SystemExit('Viewer did not start. Check viewer/server.log.')
    time.sleep(.1)
else:raise SystemExit('Viewer has not responded yet. Check viewer/server.log.')
