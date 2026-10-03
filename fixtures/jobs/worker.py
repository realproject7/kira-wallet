"""Synthetic subprocess harness. Never packaged or used by the real service."""
from pathlib import Path
import signal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from kira_jobs import JobStore

class SyntheticStore(JobStore):
    def engine_command(self,job):
        return [sys.executable,str(Path(__file__).with_name('engine.py')),sys.argv[2]]

signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
SyntheticStore(sys.argv[1]).worker()
