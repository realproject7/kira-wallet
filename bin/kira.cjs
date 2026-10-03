#!/usr/bin/env node
// Keep the existing read-only Python engine and ship its Node dependency here.
const {spawnSync}=require('node:child_process');
const path=require('node:path');
const result=spawnSync(process.env.KIRA_PYTHON || 'python3',
  [path.join(__dirname,'../kira_cli.py'),...process.argv.slice(2)],{stdio:'inherit'});
if(result.error){console.error('Kira needs Python 3.11 or newer. Set KIRA_PYTHON to its executable.');process.exitCode=1;}
else process.exitCode=result.status ?? 1;
