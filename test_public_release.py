"""Synthetic regressions for private file boundaries and release provenance."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parent/'scripts'/filename)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

checker=module('public_checker','check-public.py')
release=module('release_preparer','prepare-release.py')

class PublicReleaseTest(unittest.TestCase):
    def test_forced_runtime_config_and_transcripts_are_rejected(self):
        for path in ('.kira-agent.json','.kira.local.json','subdir/.kira-agent.json','conversations/synthetic.json','site/.vercel/project.json'):
            self.assertIn('private runtime file',checker.check(path,b'{}',set(),set()))
        self.assertEqual(checker.check('kira_agent.py',b'public source',set(),set()),[])

    def test_dirty_source_cannot_claim_committed_release_head(self):
        with patch.object(release.subprocess,'check_output',return_value=b' M kira_agent.py\n'):
            with self.assertRaisesRegex(SystemExit,'Commit and review'):release.clean_head()
        with patch.object(release.subprocess,'check_output',side_effect=[b'', 'synthetic-head\n']):
            self.assertEqual(release.clean_head(),'synthetic-head')

if __name__=='__main__':unittest.main()
