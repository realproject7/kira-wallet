"""Historical files remain readable without restoring an embedded agent."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from kira_archive import conversation_read,conversations,workspace_path,workspace_list,artifacts,read_artifact
from kira_jobs import JobError

class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'data';self.root.mkdir();(self.root/'conversations').mkdir()
        self.identity=str(uuid.uuid4());self.file=self.root/'conversations'/(self.identity+'.json')
        self.value={'schema_version':1,'conversation_id':self.identity,'config':{'scope':'wallet','wallet':'removed-wallet'},'messages':[{'role':'user','text':'Saved question'},{'role':'assistant','text':'Saved answer'}],'updated_at':'2026-10-01T00:00:00Z'}
        self.file.write_text(json.dumps(self.value));self.workspace=workspace_path(self.root,self.identity);self.workspace.mkdir(parents=True)
    def test_history_does_not_resolve_old_wallet_or_restore_runtime(self):
        result=conversation_read(self.root,self.identity)
        self.assertEqual(result['messages'],self.value['messages']);self.assertNotIn('config',result)
        self.assertEqual(conversations(self.root)[0]['conversation_id'],self.identity)
        self.assertEqual(workspace_list(self.root),[self.identity])
    def test_malformed_links_fifo_and_oversize_are_bounded(self):
        self.file.write_text('['*3000)
        with self.assertRaises((JobError,ValueError)):conversation_read(self.root,self.identity)
        self.file.unlink();outside=self.root/'outside';outside.write_text(json.dumps(self.value));self.file.symlink_to(outside)
        with self.assertRaises(OSError):conversation_read(self.root,self.identity)
        self.file.unlink();os.mkfifo(self.file)
        with self.assertRaises(JobError):conversation_read(self.root,self.identity)
        self.file.unlink();self.file.write_bytes(b' '*500001)
        with self.assertRaises(JobError):conversation_read(self.root,self.identity)
        self.file.unlink();(self.root/'conversations').rmdir();(self.root/'conversations').symlink_to(self.workspace)
        with self.assertRaises(OSError):conversation_read(self.root,self.identity)
    def test_artifact_listing_and_read_reject_escape_links_and_pipes(self):
        (self.workspace/'report.csv').write_text('token,value\nDEMO,125\n')
        self.assertEqual(artifacts(self.root,self.identity),[{'path':'report.csv','size':21}])
        self.assertEqual(read_artifact(self.root,self.identity,'report.csv'),b'token,value\nDEMO,125\n')
        (self.workspace/'link').symlink_to(self.file);os.mkfifo(self.workspace/'pipe')
        for name in ('../outside',str(self.file),'link','pipe',''):
            with self.assertRaises((JobError,OSError)):read_artifact(self.root,self.identity,name)
        folder=self.workspace/'folder';folder.symlink_to(self.root)
        with self.assertRaises(JobError):read_artifact(self.root,self.identity,'folder/outside')
    def test_replaced_workspace_parents_are_not_followed(self):
        (self.workspace/'report.csv').write_text('saved')
        moved=self.workspace.with_name(self.identity+'-old');self.workspace.rename(moved);self.workspace.symlink_to(moved)
        with self.assertRaises(JobError):read_artifact(self.root,self.identity,'report.csv')
        self.workspace.unlink();moved.rename(self.workspace)
        parent=self.workspace.parent;movedparent=parent.with_name('moved');parent.rename(movedparent);parent.symlink_to(movedparent)
        with self.assertRaises(JobError):read_artifact(self.root,self.identity,'report.csv')
