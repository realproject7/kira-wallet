'use strict';
// Presentation helpers only. Reads and navigation never submit research.
let networkPanelKey=null,networkPanel='tokens';
const workspaceDisclosures=new Map();
function matchingWallets(wallets,query=''){
  const text=String(query||'').trim().toLocaleLowerCase();
  return text?wallets.filter(w=>[w.name,w.address,w.key,...(w.tags||[])].some(v=>String(v||'').toLocaleLowerCase().includes(text))):wallets;
}
function setSettingsSection(section='data',focus=false){
  if(!['data','rpc','tools'].includes(section))section='data';
  for(const key of ['data','rpc','tools']){
    const active=key===section,button=$('settings-tab-'+key);
    button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
    $('settings-panel-'+key).hidden=!active;
  }
  if(focus)$('settings-tab-'+section).focus();
}
function networkPanels(network,tokens,wallets){
  if(networkPanelKey!==network.id){networkPanelKey=network.id;networkPanel='tokens';}
  return `<div class="record-tabs" role="tablist" aria-label="Network views"><button type="button" role="tab" id="network-tab-tokens" data-network-panel="tokens" aria-selected="${networkPanel==='tokens'}" aria-controls="network-panel-tokens" tabindex="${networkPanel==='tokens'?0:-1}">Tokens <span>${network.unique_asset_count}</span></button><button type="button" role="tab" id="network-tab-wallets" data-network-panel="wallets" aria-selected="${networkPanel==='wallets'}" aria-controls="network-panel-wallets" tabindex="${networkPanel==='wallets'?0:-1}">By wallet <span>${network.wallet_count}</span></button></div><div id="network-panel-tokens" role="tabpanel" aria-labelledby="network-tab-tokens" ${networkPanel==='tokens'?'':'hidden'}>${tokens}</div><div id="network-panel-wallets" role="tabpanel" aria-labelledby="network-tab-wallets" ${networkPanel==='wallets'?'':'hidden'}>${wallets}</div>`;
}
function setNetworkPanel(panel,focus=false){
  if(!['tokens','wallets'].includes(panel))return;networkPanel=panel;
  for(const key of ['tokens','wallets']){
    const button=$('network-tab-'+key);if(!button)return;
    const active=key===panel;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
    $('network-panel-'+key).hidden=!active;
  }
  if(focus)$('network-tab-'+panel).focus();
}
function savedDisclosures(element){
  for(const node of element.querySelectorAll('[data-disclosure-key]'))workspaceDisclosures.set(node.dataset.disclosureKey,node.open);
  while(workspaceDisclosures.size>250)workspaceDisclosures.delete(workspaceDisclosures.keys().next().value);
  return new Map(workspaceDisclosures);
}
function restoreDisclosures(element,values){for(const node of element.querySelectorAll('[data-disclosure-key]'))if(values.has(node.dataset.disclosureKey))node.open=values.get(node.dataset.disclosureKey);}
function clearCatalogFilters(){
  clearTimeout(catalogTimer);catalogPage=1;catalogMinimum=0;
  for(const [id,value] of Object.entries({'all-token-search':'','all-token-network':'all','all-token-pricing':'all','all-token-sort':'value'}))$(id).value=value;
  $('all-token-testnets').checked=false;
  if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  state?.paged?loadRoute():renderCatalog();
}
function filterHomeWallets(){
  if(!state)return;
  const keys=new Set(matchingWallets(state.wallets,$('home-wallet-search').value).map(w=>w.key));
  for(const row of $('wallet-cards').querySelectorAll('[data-wallet]'))row.hidden=!keys.has(row.dataset.wallet);
  $('home-wallet-empty').hidden=keys.size>0;
}
function moveSectionTab(event,selector,keys,select){
  const button=event.target.closest(selector);if(!button)return;
  const current=keys.indexOf(button.dataset.settingsSection||button.dataset.networkPanel);
  const next=event.key==='Home'?0:event.key==='End'?keys.length-1:event.key==='ArrowRight'||event.key==='ArrowDown'?(current+1)%keys.length:event.key==='ArrowLeft'||event.key==='ArrowUp'?(current+keys.length-1)%keys.length:null;
  if(next!==null){event.preventDefault();select(keys[next],true);}
}
function initWorkspaceDesign(){
  const mobile=window.matchMedia('(max-width: 980px)'),navigation=$('wallet-navigation');
  const resize=()=>{navigation.open=!mobile.matches;};resize();mobile.addEventListener('change',resize);
  const compactSettings=window.matchMedia('(max-width: 640px)');
  const settingsOrientation=()=>document.querySelector('.settings-navigation').setAttribute('aria-orientation',compactSettings.matches?'horizontal':'vertical');
  settingsOrientation();compactSettings.addEventListener('change',settingsOrientation);
  $('wallet-nav-search').addEventListener('input',()=>{if(state)renderWallets();});
  $('home-wallet-search').addEventListener('input',filterHomeWallets);
  navigation.addEventListener('click',event=>{if(mobile.matches&&event.target.closest('[data-wallet]'))navigation.open=false;});
  navigation.addEventListener('keydown',event=>{if(mobile.matches&&event.key==='Escape'){event.preventDefault();navigation.open=false;navigation.querySelector('summary').focus();}});
  $('workspace-settings-dialog').addEventListener('click',event=>{const button=event.target.closest('[data-settings-section]');if(button)setSettingsSection(button.dataset.settingsSection);});
  $('workspace-settings-dialog').addEventListener('keydown',event=>moveSectionTab(event,'[data-settings-section]',['data','rpc','tools'],setSettingsSection));
  $('detail-view').addEventListener('click',event=>{const button=event.target.closest('[data-network-panel]');if(button)setNetworkPanel(button.dataset.networkPanel);});
  $('detail-view').addEventListener('keydown',event=>moveSectionTab(event,'[data-network-panel]',['tokens','wallets'],setNetworkPanel));
  $('catalog-clear').addEventListener('click',clearCatalogFilters);
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-copy-record],[data-copy-command]');if(!button)return;
    const value=button.dataset.copyRecord||button.dataset.copyCommand;
    try{await navigator.clipboard.writeText(value);toast(button.dataset.copyRecord?'Token address copied':'Command copied');}
    catch{toast('Select the text to copy it.');}
  });
}
window.addEventListener('DOMContentLoaded',initWorkspaceDesign);
