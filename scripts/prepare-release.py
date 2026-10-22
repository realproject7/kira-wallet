"""Prepare a reviewed public tarball. This script never publishes to a registry."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def clean_head():
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():
        raise SystemExit('Commit and review all source changes before preparing a release.')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--private-data-dir',action='append',default=[])
    args=parser.parse_args()
    head=clean_head()
    package=json.loads((ROOT/'package.json').read_text())
    if package.get('private') is not False:raise SystemExit('Package must be explicitly prepared for public release.')
    if any(k in package.get('scripts',{}) for k in ('prepublishOnly','publish','postpublish','preinstall','install','postinstall')):
        raise SystemExit('Unexpected release or installation hook. Review before packing.')
    spec=importlib.util.spec_from_file_location('public_check',ROOT/'scripts/check-public.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    identifiers,secrets=checker.private_values(args.private_data_dir)
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    # npm pack replaces a same-named archive. Validate in a private staging
    # directory, then atomically reserve the final name without overwriting it.
    with tempfile.TemporaryDirectory(prefix='.prepare-',dir=output) as staging:
        result=subprocess.run(['npm','pack','--ignore-scripts','--pack-destination',staging,'--json'],cwd=ROOT,capture_output=True,text=True,check=True)
        record=json.loads(result.stdout)[0];archive_path=output/record['filename']
        staged=Path(staging)/record['filename']
        findings=[]
        with tarfile.open(staged) as archive:
            for member in archive.getmembers():
                if not member.isfile():continue
                path=member.name.removeprefix('package/')
                reasons=checker.check(path,archive.extractfile(member).read(),identifiers,secrets)
                if reasons:findings.append({'path':path,'reasons':reasons})
        if findings:
            print(json.dumps({'findings':findings},indent=2));raise SystemExit('Tarball privacy scan failed. Do not publish.')
        digest=hashlib.sha256(staged.read_bytes()).hexdigest()
        if clean_head()!=head:raise SystemExit('Source changed during packing. Prepare the release again.')
        try:os.link(staged,archive_path)
        except FileExistsError:
            raise SystemExit('This release archive already exists. Preserve it and choose a new package version.') from None
    manifest={'name':package['name'],'version':package['version'],'source_head':head,'archive':record['filename'],'sha256':digest,'files':record['entryCount'],'registry_published':False}
    (output/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
    print('Operator command from project root: npm publish ./dist/'+record['filename']+' --access public')

if __name__=='__main__':main()
