'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('viewer/static/jobs.js','utf8');
const nodes=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,open:false,disabled:false,showModal(){this.open=true;},textContent:'',hidden:false,addEventListener(type,fn){this[type]=fn;}});return nodes.get(id);};
const old={rpc:{mode:'public',priority:'public_first',allow_public_fallback:true,chains:{}},discovery:{provider:'none',key_env:'ALCHEMY_API_KEY'}};
const fresh={rpc:{mode:'custom',priority:'public_first',allow_public_fallback:true,chains:{8453:{url_env:'EXISTING_KEY',alchemy_network:'base-mainnet'}}},discovery:{provider:'alchemy',key_env:'EXISTING_KEY'}};
const ctx=vm.createContext({$:el,jobList:[],connectionWallet:null,selectedView:'home',localSession:{controls:true},settingSaving:false,pendingSetting:null,connectionRevision:1,connectionConfig:old,connectionReadiness:null,settingSaved:false,settingFailed:false,Promise,localAPI:async path=>path==='/api/settings'?fresh:{local_key_available:true}});
vm.runInContext(source.slice(source.indexOf('function connectionSummary(config)'),source.indexOf('function renderConnectionForm()')),ctx);
vm.runInContext(source.slice(source.indexOf('function renderConnectionForm()'),source.indexOf('async function openWorkspaceSettings()')),ctx);
vm.runInContext(source.slice(source.indexOf('async function openDataConnections('),source.indexOf('async function saveConnectionSetting(')),ctx);
vm.runInContext(source.slice(source.indexOf('async function saveConnectionSetting('),source.indexOf("$('open-settings').addEventListener")),ctx);
vm.runInContext(source.slice(source.indexOf("$('provider-recheck').addEventListener"),source.indexOf("$('settings-refresh').addEventListener")),ctx);
function reset(){el('provider-recheck').disabled=false;ctx.connectionConfig=structuredClone(old);el('settings-dialog').open=true;el('data-provider').value='alchemy';el('discovery-key').value='ALCHEMY_API_KEY';el('rpc-mode').value='public';el('rpc-priority').value='public_first';el('rpc-references').value='';el('rpc-custom-only').checked=false;el('new-wallet-address').value='untouched-wallet-draft';}
(async()=>{
 reset();el('data-provider').value='public';await el('provider-recheck').click();
 assert.equal(el('data-provider').value,'alchemy');
 assert.equal(el('discovery-key').value,'EXISTING_KEY');assert.equal(el('provider-save').disabled,false);
 assert.match(el('provider-status').textContent,/Saved connection: Alchemy selected/);
 assert.equal(el('rpc-mode').value,'custom');assert.equal(el('new-wallet-address').value,'untouched-wallet-draft');
 reset();el('discovery-key').value='EDITED_KEY';el('rpc-references').value='8453 PERSONAL_RPC';el('rpc-priority').value='custom_first';
 await el('provider-recheck').click();
 assert.equal(el('data-provider').value,'alchemy');assert.equal(el('discovery-key').value,'EDITED_KEY');assert.equal(el('rpc-references').value,'8453 PERSONAL_RPC');assert.equal(el('rpc-priority').value,'custom_first');assert.equal(el('provider-save').disabled,true);

 reset();let resolveOld;let reads=0;
 const saved={rpc:{mode:'custom',priority:'custom_first',allow_public_fallback:true,chains:{8453:{url_env:'PERSONAL_RPC'}}},discovery:{provider:'none',key_env:'ALCHEMY_API_KEY'}};
 ctx.localAPI=async path=>{if(path==='/api/settings' && reads++===0)return await new Promise(resolve=>{resolveOld=resolve;});if(path.startsWith('/api/jobs/'))return {state:'succeeded'};return path==='/api/settings'?saved:{local_key_available:false};};
 ctx.submitOperation=async()=>({job_id:'saved-request'});
 const checking=el('provider-recheck').click();
 el('rpc-mode').value='custom';el('rpc-priority').value='custom_first';el('rpc-references').value='8453 PERSONAL_RPC';
 await ctx.saveConnectionSetting('settings.rpc',saved.rpc);
 resolveOld(old);await checking;
 assert.equal(ctx.connectionConfig.rpc.priority,'custom_first');
 assert.equal(el('provider-recheck').disabled,false);
 assert.equal(el('provider-status').textContent,'Connection saved. Refresh holdings to check the new coverage.');
 assert.equal(el('rpc-mode').value,'custom');assert.equal(el('rpc-priority').value,'custom_first');assert.equal(el('rpc-references').value,'8453 PERSONAL_RPC');

 reset();ctx.connectionConfig=null;let resolveOpening;let openingReads=0;
 ctx.localAPI=async path=>{if(path==='/api/settings'){openingReads++;return await new Promise(resolve=>{resolveOpening=resolve;});}return {local_key_available:false};};
 const opening=ctx.openDataConnections();
 assert.equal(el('provider-recheck').disabled,true);await el('provider-recheck').click();assert.equal(openingReads,1);
 resolveOpening(old);await opening;assert.equal(el('provider-recheck').disabled,false);
 assert.equal(ctx.connectionConfig.discovery.provider,'none');
 console.log('Connection recheck reconciles imported references and preserves user edits.');
})().catch(e=>{console.error(e);process.exitCode=1;});
