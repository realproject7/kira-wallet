'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
function el(id){if(!nodes.has(id))nodes.set(id,{value:'',checked:false,disabled:false,textContent:'',addEventListener(type,fn){this[type]=fn;}});return nodes.get(id);}
const value=(enabled,status,version=null)=>({enabled,status,version,installed:status==='available',install_prompt:'Install @h402/cli from npm.'});
let saved=value(false,'disabled'),submissions=[],receiptState='succeeded',failRead=false,clipboard='';
const context=vm.createContext({$:el,setTimeout:fn=>fn(),Promise,Error,encodeURIComponent,
  localAPI:async path=>{if(failRead)throw Error('Disconnected');return path==='/api/settings'?{integrations:{h402:saved}}:{state:receiptState};},
  submitOperation:async(operation,input)=>{submissions.push({operation,input});saved=value(input.enabled,input.enabled?'not_installed':'disabled');return {job_id:'synthetic-job'};},
  navigator:{clipboard:{writeText:async text=>{clipboard=text;}}},toast:()=>{}});
vm.runInContext(fs.readFileSync('viewer/static/integrations.js','utf8'),context);
const submit=()=>el('h402-form').submit({preventDefault(){}});
(async()=>{
  await context.loadH402Settings();
  assert.equal(el('h402-enabled').checked,false);assert.equal(el('h402-fields').disabled,false);
  assert.match(el('h402-summary').textContent,/Not enabled/);
  await el('h402-copy').click();assert.equal(clipboard,saved.install_prompt);assert.equal(submissions.length,0);assert.equal(el('h402-copy').textContent,'Copied');

  el('h402-enabled').checked=true;
  await el('h402-recheck').click();assert.equal(el('h402-enabled').checked,true,'checking installation keeps an unsaved preference');
  await submit();assert.equal(submissions.length,1);assert.equal(submissions[0].operation,'settings.h402');
  assert.equal(submissions[0].input.enabled,true);assert.match(el('h402-summary').textContent,/not found/);
  assert.equal(el('h402-status').textContent,'Preference saved.');
  saved=value(true,'available','0.1.8');await el('h402-recheck').click();
  assert.match(el('h402-summary').textContent,/Available · h402 0.1.8/);
  saved=value(true,'unavailable');await el('h402-recheck').click();
  assert.match(el('h402-summary').textContent,/version check failed/);
  assert.equal(submissions.length,1,'status checks cannot submit calls or install software');

  receiptState='queued';el('h402-enabled').checked=false;await submit();
  assert.match(el('h402-error').textContent,/still queued/);assert.equal(submissions.length,2);
  receiptState='succeeded';await submit();assert.equal(submissions.length,2,'a pending save checks its existing receipt');
  assert.equal(el('h402-enabled').checked,false);
  receiptState='failed';el('h402-enabled').checked=true;await submit();
  assert.match(el('h402-error').textContent,/not saved/);

  receiptState='succeeded';const read=context.localAPI;let lostStatus=true;
  context.localAPI=async path=>{if(path==='/api/settings'&&lostStatus){lostStatus=false;throw Error('Status response lost');}return read(path);};
  await submit();const savedCount=submissions.length;
  assert.match(el('h402-error').textContent,/Status response lost/);
  await submit();assert.equal(submissions.length,savedCount,'a lost status after commit keeps the accepted receipt');
  context.localAPI=read;
  context.navigator.clipboard.writeText=async()=>{throw Error('Clipboard unavailable');};
  await el('h402-copy').click();assert.match(el('h402-copy').textContent,/Select the prompt/);

  failRead=true;await context.loadH402Settings();
  assert.equal(el('h402-fields').disabled,true);assert.match(el('h402-error').textContent,/Could not check/);
  const count=submissions.length;await submit();assert.equal(submissions.length,count);
  failRead=false;receiptState='succeeded';await context.loadH402Settings();assert.equal(el('h402-fields').disabled,false);

  let oldResolve;
  const oldLoad=context.loadH402Settings(false,new Promise(resolve=>{oldResolve=resolve;}));
  await context.loadH402Settings(false,Promise.resolve({integrations:{h402:value(true,'available','0.2.0')}}));
  oldResolve({integrations:{h402:value(false,'disabled')}});await oldLoad;
  assert.equal(el('h402-enabled').checked,true);assert.match(el('h402-summary').textContent,/0.2.0/);
  console.log('h402 preferences, install handoff, local availability, retries and stale responses verified.');
})().catch(error=>{console.error(error);process.exitCode=1;});
