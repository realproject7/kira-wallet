'use strict';
// Areas: everything, a folder or one wallet, each with Overview, All tokens and Activity,
// seen whole or through one platform. Wallet holdings are one list across networks.
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('viewer/static/app.js','utf8'),html=fs.readFileSync('viewer/static/index.html','utf8');
const slice=(from,to)=>source.slice(source.indexOf(from),source.indexOf(to));
const W='0x'+'a'.repeat(40),V='0x'+'b'.repeat(40),U='0x'+'c'.repeat(40);

function harness({folder=null}={}){
 const nodes=new Map();
 const node=id=>{if(!nodes.has(id)){const n={id,value:'',hidden:false,textContent:'',innerHTML:'',dataset:{},attrs:{},
  setAttribute(k,v){this.attrs[k]=String(v);},removeAttribute(k){delete this.attrs[k];},getAttribute(k){return this.attrs[k]??null;},hasAttribute(k){return k in this.attrs;},
  querySelector:sel=>node(id+' '+sel),querySelectorAll:sel=>sel==='[data-tab]'?tabs:[],closest:sel=>node(id+'<'+sel),addEventListener(){}};nodes.set(id,n);}return nodes.get(id);};
 const tabs=['overview','tokens','activity'].map(tab=>Object.assign(node('tab-'+tab),{dataset:{tab}}));
 const FolderUI={id:folder,route(parts){if(parts[0]==='folder'&&parts[1]){this.id=parts[1];return parts.slice(2).length?parts.slice(2):['home'];}this.id=null;return parts;},
  view:()=>ctx.state,path(tail='home'){return '#/'+(this.id?'folder/'+this.id+(tail==='home'?'':'/'+tail):tail);},walletPath(key){return this.id?this.path('wallet/'+key):'#/wallet/'+key;},
  breadcrumb(){return this.id?[{label:'Portfolio',href:'#/home'},{label:'Folder',href:'#/folder/'+this.id}]:[{label:'Portfolio',href:'#/home'}];},wallets:()=>ctx.state?.wallets||[]};
 const ctx=vm.createContext({$:node,FolderUI,KiraView:require('./viewer/static/workspace-model.js'),URLSearchParams,Intl,
  localStorage:{getItem:()=>null,setItem(){}},location:{hash:'#/home',origin:'http://localhost'},window:{scrollTo(){}},document:{getElementById:id=>node(id),querySelectorAll:()=>[],title:''},
  renderHomeCoverage(){},bindImages(){},policyNotice:()=>'',policyBadge:()=>'',policyActions:()=>'',renderView(){},loadRoute(){}});
 vm.runInContext(source.slice(0,source.indexOf('async function readAPI(')),ctx);
 for(const [from,to] of [['function currentWallet()','function renderWallets(){'],['function progress(','function renderWalletHeader('],['function icon(asset){','function bindImages('],['function saleValue(','function timeRange(']])vm.runInContext(slice(from,to),ctx);
 ctx.FolderUI.id=folder;
 // Values cross from the page's realm as plain data.
 const setState=value=>{ctx.state=value;ctx.__state=value;vm.runInContext('state=__state',ctx);};
 return {ctx,node,tabs,setState,run:code=>vm.runInContext(code,ctx),data:code=>JSON.parse(vm.runInContext('JSON.stringify('+code+')',ctx))};
}
const group=(id,name,value,positions=0,extra={})=>({id,name,value_usd:value,position_count:positions,unpriced_count:0,percent:null,...extra});
function portfolio(){
 const wallets=[
  {key:W,address:W,name:'Lanes',analysed_at:'2026-11-15',mainnet_asset_count:3,mainnet_unpriced_count:0,assets:[],chains:[],sell_out_summary:{value_usd:5},capital_allocation:{known_value_usd:40,groups:[group('wallet','Wallet tokens',10),group('aeromax','Aeromax',30,2)]}},
  {key:V,address:V,name:'Curves',analysed_at:'2026-11-15',mainnet_asset_count:4,mainnet_unpriced_count:1,assets:[],chains:[],sell_out_summary:{value_usd:70},capital_allocation:{known_value_usd:80,groups:[group('mintclub','Mint Club',80)]}},
  {key:U,address:U,name:'Small lanes',analysed_at:'2026-11-15',mainnet_asset_count:1,mainnet_unpriced_count:0,assets:[],chains:[],sell_out_summary:{value_usd:1},capital_allocation:{known_value_usd:5,groups:[group('aeromax','Aeromax',5,1)]}}];
 const allocation={known_value_usd:125,position_count:3,groups:[group('mintclub','Mint Club',80,0,{percent:64}),group('aeromax','Aeromax',35,3,{percent:28,logo:'/venues/aeromax.png'}),group('wallet','Wallet tokens',10,0,{percent:8}),group('uniswap','Uniswap',null)]};
 return {paged:true,data_revision:'r1',wallets,details:{networks:[{id:8453,name:'Base'},{id:1,name:'Ethereum'}]},
  dashboard:{wallet_count:3,analysed_wallet_count:3,chain_count:2,unique_asset_count:8,priced_count:8,unpriced_count:0,known_value_usd:125,capital_allocation:allocation,sell_out_summary:{value_usd:76},
   networks:[{id:8453,name:'Base',value_usd:115,position_count:6,capital_allocation:{known_value_usd:115,groups:[group('aeromax','Aeromax',35,3),group('mintclub','Mint Club',80)]}},{id:1,name:'Ethereum',value_usd:10,position_count:1,capital_allocation:{known_value_usd:10,groups:[group('wallet','Wallet tokens',10)]}}]}};
}

test('routes name the area, its tab and the platform it is seen through',()=>{
 const h=harness();
 const read=hash=>{h.ctx.location.hash=hash;h.run('readRoute()');return h.data('({view:selectedView,tab:walletTab,area:areaWallet,platform:selectedPlatform,folder:FolderUI.id})');};
 assert.deepEqual(read('#/wallet/'+W+'/tokens?platform=mintclub'),{view:'wallet',tab:'tokens',area:W,platform:'mintclub',folder:null});
 assert.deepEqual(read('#/wallet/'+W.toUpperCase().replace('0X','0x')),{view:'wallet',tab:'overview',area:W,platform:null,folder:null});
 assert.deepEqual(read('#/wallet/'+W+'/activity'),{view:'activity',tab:'overview',area:W,platform:null,folder:null});
 assert.deepEqual(read('#/folder/f1/activity'),{view:'activity',tab:'overview',area:null,platform:null,folder:'f1'});
 assert.deepEqual(read('#/tokens?platform=lptoken'),{view:'tokens',tab:'overview',area:null,platform:'lptoken',folder:null});
 assert.equal(read('#/home?platform=%3Cscript%3E').platform,null,'An unknown platform name is ignored.');
 // Choosing a platform keeps the list filters; opening another page resets them.
 read('#/wallet/'+W+'/tokens');h.run("selectedChain='8453';minimum=5;walletOffset=100");
 read('#/wallet/'+W+'/tokens?platform=mintclub');assert.deepEqual(h.data('[selectedChain,minimum,walletOffset]'),['8453',5,0]);
 read('#/wallet/'+W);assert.deepEqual(h.data('[selectedChain,minimum]'),['all',0]);
});

test('each area links its own Overview, All tokens and Activity',()=>{
 const h=harness();
 assert.deepEqual(['overview','tokens','activity'].map(tab=>h.ctx.areaHref(tab)),['#/home','#/tokens','#/activity']);
 h.run("selectedPlatform='aeromax'");
 assert.deepEqual(['overview','tokens','activity'].map(tab=>h.ctx.areaHref(tab)),['#/home?platform=aeromax','#/tokens?platform=aeromax','#/activity'],'Activity has no platform view.');
 h.run("FolderUI.id='f1';selectedPlatform=null");
 assert.deepEqual(['overview','tokens','activity'].map(tab=>h.ctx.areaHref(tab)),['#/folder/f1','#/folder/f1/tokens','#/folder/f1/activity']);
 h.run('areaWallet='+JSON.stringify(W));
 assert.deepEqual(['overview','tokens','activity'].map(tab=>h.ctx.areaHref(tab)),['#/folder/f1/wallet/'+W,'#/folder/f1/wallet/'+W+'/tokens','#/folder/f1/wallet/'+W+'/activity']);
 assert.equal(h.ctx.areaHref('overview',null),'#/folder/f1/wallet/'+W);
});

test('the area bar marks the open tab, counts the area and offers its platforms',()=>{
 const h=harness();h.setState(portfolio());h.run("selectedView='home'");h.ctx.renderAreaBar();
 assert.equal(h.node('area-bar').dataset.area,'portfolio');
 assert.equal(h.tabs[0].attrs['aria-current'],'page');assert.equal(h.tabs[1].attrs['aria-current'],undefined);
 assert.equal(h.node('all-token-count').textContent,'8');
 const options=h.node('platform-filter').innerHTML;
 assert.match(options,/<option value="">All platforms<\/option><option value="mintclub">Mint Club<\/option><option value="aeromax" data-logo="\/venues\/aeromax.png">Aeromax<\/option><option value="wallet">Wallet tokens<\/option>$/);
 assert.doesNotMatch(options,/uniswap/,'A platform with nothing recorded is not offered.');
 assert.equal(h.node('platform-lens').hidden,false);
 h.run("selectedView='activity'");h.ctx.renderAreaBar();assert.equal(h.node('platform-lens').hidden,true);assert.equal(h.tabs[2].attrs['aria-current'],'page');
 // A wallet area counts the wallet's tokens on every tab and offers the wallet's platforms.
 h.run("selectedView='wallet';walletTab='tokens';selectedWallet="+JSON.stringify(W)+";areaWallet=selectedWallet");h.ctx.renderAreaBar();
 assert.equal(h.node('area-bar').dataset.area,'wallet');assert.equal(h.tabs[1].attrs['aria-current'],'page');
 assert.equal(h.node('all-token-count').textContent,'3');assert.match(h.node('platform-filter').innerHTML,/Aeromax/);assert.doesNotMatch(h.node('platform-filter').innerHTML,/Mint Club/);
 h.run("selectedView='token';areaWallet=null");h.ctx.renderAreaBar();assert.equal(h.node('area-bar').dataset.area,'detail');assert.equal(h.tabs.some(t=>t.attrs['aria-current']),false);
});

test('a breadcrumb lists only the places that lead to the page',()=>{
 const h=harness();h.run("areaWallet="+JSON.stringify(W));
 h.ctx.renderBreadcrumb([{label:'Portfolio',href:'#/home'},{label:'Folder',href:'#/folder/f1'},{label:'Lanes'}]);
 assert.equal(h.node('breadcrumbs').innerHTML,'<ol><li><a href="#/home" title="Portfolio">Portfolio</a></li><li><a href="#/folder/f1" title="Folder">Folder</a></li></ol>');
 assert.equal(h.node('breadcrumbs').hidden,false);
 h.run("areaWallet=null;selectedView='home'");h.ctx.renderBreadcrumb([{label:'Portfolio',href:'#/home'},{label:'Folder'}]);
 assert.equal(h.node('breadcrumbs').hidden,true,'The portfolio heading names its folder itself.');
});

test('a platform view shows its value, the wallets and networks holding it',()=>{
 const h=harness();h.setState(portfolio());h.run("selectedView='home';selectedPlatform='aeromax'");h.ctx.renderHome();
 assert.equal(h.node('home-value-label').textContent,'Aeromax');assert.equal(h.node('home-total').textContent,'$35.00');
 const meta=h.node('home-meta').innerHTML;
 assert.match(meta,/<strong>28\.0%<\/strong> of portfolio/);assert.match(meta,/<strong>2<\/strong> wallets/);assert.match(meta,/<strong>3<\/strong> positions/);assert.match(meta,/href="#\/home">All platforms/);
 const cards=h.node('wallet-cards').innerHTML;
 assert.ok(cards.indexOf('Lanes')<cards.indexOf('Small lanes'));assert.doesNotMatch(cards,/Curves/);assert.match(cards,/2 positions/);assert.match(cards,/\$30\.00/);
 assert.equal(h.node('home-wallet-total').textContent,'2');assert.equal(h.node('home-wallet-sort').hidden,true);
 const networks=h.node('network-allocation').innerHTML;assert.match(networks,/Base/);assert.doesNotMatch(networks,/Ethereum/);assert.match(networks,/\$35\.00/);
 assert.equal(h.node('home-sell-out').innerHTML,'','Positions have no sell-out estimate.');
 // Mint Club tokens are wallet tokens: their view carries their own sell-out sum.
 h.run("selectedPlatform='mintclub';routeData={page:{platform_sell_out_summary:{value_usd:60,position_count:4,missing_count:0}}}");h.ctx.renderHome();
 assert.match(h.node('home-sell-out').innerHTML,/≈ \$60\.00/);
});

test('wallets order by sell-out estimate when asked',()=>{
 const h=harness();h.setState(portfolio());h.run("selectedView='home';homeWalletSort='sell_out'");h.ctx.renderHome();
 const cards=h.node('wallet-cards').innerHTML;
 assert.ok(cards.indexOf('Curves')<cards.indexOf('Lanes')&&cards.indexOf('Lanes')<cards.indexOf('Small lanes'));
 assert.match(cards,/<strong>≈ \$70\.00<\/strong>/);assert.equal(h.node('home-wallet-sort').hidden,false);
 h.run("homeWalletSort='value'");h.ctx.renderHome();const byValue=h.node('wallet-cards').innerHTML;
 assert.ok(byValue.indexOf('Curves')<byValue.indexOf('Lanes'));assert.match(byValue,/<strong>\$80\.00<\/strong>/);
});

test('wallet holdings are one list across networks, each token marked with its network',()=>{
 const h=harness(),asset=(i,chain,value,sale)=>({id:chain+':0x'+String(i).repeat(40),chain_id:chain,address:'0x'+String(i).repeat(40),symbol:'T'+i,name:'Token '+i,environment:'mainnet',balance:'1',value_usd:value,price:{usd:value,basis:'DEX market'},sell_out:{value_usd:sale,output_amount:'1',output_symbol:'USDC'}});
 const wallet={key:W,address:W,name:'Lanes',analysed_at:'2026-11-15',asset_count:6,unpriced_count:0,chains:[{id:8453,name:'Base',environment:'mainnet'},{id:1,name:'Ethereum',environment:'mainnet'}],
  assets:[asset(1,8453,9,1),asset(2,1,8,7),asset(3,8453,7,6),asset(4,1,6,5),asset(5,8453,5,4),asset(6,1,4,9)]};
 h.setState({paged:false,details:{networks:[{id:8453,name:'Base'},{id:1,name:'Ethereum'}]}});h.run('currentWallet=()=>globalThis.wallet');h.ctx.wallet=wallet;
 h.run("selectedView='wallet';walletTab='tokens';areaWallet="+JSON.stringify(W)+";walletSort='value';selectedChain='all';minimum=0;walletStatus='portfolio'");h.ctx.renderHoldings();
 const list=h.node('asset-groups').innerHTML;
 assert.equal((list.match(/<table/g)||[]).length,1,'One table, not one per network.');
 assert.deepEqual([...list.matchAll(/class="symbol" title="(T\d)"/g)].map(m=>m[1]),['T1','T2','T3','T4','T5','T6']);
 assert.equal((list.match(/class="coin-chain" title="Base"/g)||[]).length,3);assert.equal((list.match(/class="coin-chain" title="Ethereum"/g)||[]).length,3);
 assert.match(list,/Token 2<span class="token-chain"> · Ethereum<\/span>/);
 assert.match(list,/data-sort-column="value" aria-sort="descending"><button type="button" class="sort-header" data-sort-list="wallet" data-sort="value">Value/);
 assert.equal(h.node('holdings-label').textContent,'Holdings');assert.equal(h.node('visible-count').textContent,'6');
 h.run("walletSort='sell_out'");h.ctx.renderHoldings();
 assert.deepEqual([...h.node('asset-groups').innerHTML.matchAll(/class="symbol" title="(T\d)"/g)].map(m=>m[1]),['T6','T2','T3','T4','T5','T1']);
 assert.match(h.node('asset-groups').innerHTML,/data-sort-column="sell_out" aria-sort="descending"/);
 // Overview shows the five largest, then a link to the whole list.
 h.run("walletTab='overview';walletSort='value'");h.ctx.renderHoldings();
 assert.equal(h.node('holdings-label').textContent,'Top tokens');assert.equal(h.node('visible-count').textContent,'5 of 6');
 assert.equal((h.node('asset-groups').innerHTML.match(/class="symbol"/g)||[]).length,5);
 assert.equal(h.node('wallet-view-all').hidden,false);assert.equal(h.node('wallet-view-all').href,'#/wallet/'+W+'/tokens');
});

test('the page puts global tools on top and each area\'s sections under its heading',()=>{
 const top=html.slice(html.indexOf('<header class="topbar global-bar">'),html.indexOf('</header>',html.indexOf('<header class="topbar global-bar">')));
 assert.match(top,/id="open-wallet-finder"/);assert.match(top,/id="open-connection"/);assert.doesNotMatch(top,/breadcrumb|data-tab|workspace-tabs/);
 const area=html.slice(html.indexOf('<section id="area-bar"'),html.indexOf('<div id="route-status"'));
 for(const part of ['id="breadcrumbs"','id="home-heading"','id="wallet-header"','data-tab="overview"','data-tab="tokens"','data-tab="activity"','id="platform-filter"'])assert.ok(area.includes(part),part);
 assert.ok(area.indexOf('id="home-heading"')<area.indexOf('data-tab="overview"'),'The area heading sits above its tabs.');
 assert.equal((html.match(/data-tab="overview"/g)||[]).length,1,'One set of section tabs.');
});
