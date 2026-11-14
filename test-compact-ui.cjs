'use strict';
// Compact presentation: one number per question, state as chips, method behind info tips.
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('viewer/static/app.js','utf8'),design=fs.readFileSync('viewer/static/workspace-design.js','utf8');
const html=fs.readFileSync('viewer/static/index.html','utf8'),css=fs.readFileSync('viewer/static/compact.css','utf8');
const slice=(from,to)=>source.slice(source.indexOf(from),source.indexOf(to));
function harness(){
 const nodes=new Map();
 const $=id=>{if(!nodes.has(id))nodes.set(id,{id,value:'',hidden:false,textContent:'',innerHTML:'',dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},hasAttribute(k){return k in this.attrs;},querySelectorAll:()=>[],addEventListener(){}});return nodes.get(id);};
 const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ctx=vm.createContext({$,escapeHTML,money:v=>v==null?'—':'$'+v,stamp:String,shortAddress:a=>a.slice(0,6)+'…'+a.slice(-4),walletGlyph:'<svg></svg>',arrowGlyph:'',
  KiraView:require('./viewer/static/workspace-model.js'),networkHref:id=>'#/network/'+id,renderBreadcrumb(){},renderHomeCoverage(){},bindImages(){},chainIcon:()=>'<i class="chain-icon"></i>',
  selectedView:'home',selectedWallet:null,jobList:[],state:null,window:{addEventListener(){}},clearTimeout(){}});
 for(const helper of ['const infoTip =','const integer =','const walletAvatar =','const ratioBar =','const walletTokenValue ='])vm.runInContext(source.split('\n').find(line=>line.startsWith(helper)),ctx);
 for(const [from,to] of [['function progress(','function chainIcon('],['function renderWallets(){','function renderView(){'],['function renderHome(){','function renderWallet(){'],['function sellSummary(','function sellOutNote('],['function policyNotice(','function policyButton(']])vm.runInContext(slice(from,to),ctx);
 vm.runInContext(design,ctx);
 return {ctx,$};
}
const chain=(gap=false)=>({id:1,name:'Ethereum',environment:'mainnet',complete:!gap,rpc_available:true,assets:1});
const wallet=(index,name,value,extra={})=>({key:'0x'+String(index).repeat(40),address:'0x'+String(index).repeat(40),name,tags:[name],analysed_at:'2026-11-13',known_value_usd:value,unpriced_count:1,mainnet_asset_count:index,mainnet_unpriced_count:1,assets:[],chains:[chain()],sell_out_summary:{value_usd:value},...extra});

test('Home shows one total, state as chips, and wallets ranked by value',()=>{
 const h=harness(),wallets=[wallet(1,'Small',10),wallet(2,'Large',90),wallet(3,'Unchecked',null,{analysed_at:null})];
 h.ctx.state={wallets,dashboard:{wallet_count:3,analysed_wallet_count:2,chain_count:1,unique_asset_count:1234,priced_count:1,unpriced_count:0,known_value_usd:100,
  capital_allocation:{known_value_usd:100,position_count:0},sell_out_summary:{value_usd:80,missing_count:2,reference_count:3,limited_count:1},asset_policy_summary:{review_count:1,excluded_count:2},
  networks:[{id:1,name:'Ethereum',value_usd:100,position_count:5},{id:2,name:'Quiet',value_usd:null,position_count:1}]}};
 h.ctx.renderHome();
 assert.equal(h.$('home-total').textContent,'$100');
 const meta=h.$('home-meta').innerHTML;
 assert.match(meta,/<strong>3<\/strong> wallets/);assert.match(meta,/href="#\/tokens"><strong>1,234<\/strong> tokens/);assert.match(meta,/class="chip warn">1 awaiting analysis/);
 assert.match(meta,/data-policy-list="review"[^>]*>1 needs review/);assert.match(meta,/data-policy-list="excluded"[^>]*>2 hidden/);
 const sale=h.$('home-sell-out').innerHTML;
 assert.match(sale,/≈ \$80/);assert.match(sale,/value="80" max="100"[^>]*>80%<\/progress><small>80%<\/small>/,'The estimate shows how much of the wallet tokens it reaches.');assert.match(sale,/2 missing/);assert.match(sale,/1 limited routes/);assert.match(sale,/<details class="info-tip">[\s\S]*Includes 3 native or stable spot references/);
 assert.doesNotMatch(sale,/spot references<\/span>|Independent estimates/,'The method sits behind the info tip.');
 const rows=h.$('wallet-cards').innerHTML;
 assert.deepEqual([...rows.matchAll(/<strong>(Small|Large|Unchecked)<\/strong>/g)].map(m=>m[1]),['Large','Small','Unchecked']);
 assert.match(rows,/value="90" max="100" aria-label="Large share of priced value"/);assert.match(rows,/Not checked[\s\S]*class="allocation-empty"[\s\S]*<strong>—<\/strong>/);
 assert.equal((rows.match(/class="rank-row"/g)||[]).length,3);assert.equal((rows.match(/<svg class="wallet-avatar"/g)||[]).length,3);assert.doesNotMatch(rows,/wallet-card|Sell-out est\. sum/);
 const networks=h.$('network-allocation').innerHTML;
 assert.match(networks,/Quiet[\s\S]*class="allocation-empty"[\s\S]*<small>Unpriced<\/small>/);
 assert.equal(h.$('home-wallet-total').textContent,'3');assert.equal(h.$('home-network-more').hidden,true);
});

test('long wallet lists open with the largest rows; search always shows every match',()=>{
 const h=harness(),wallets=Array.from({length:12},(_,i)=>({key:'0x'+String(i).padStart(40,'0'),address:'0x'+String(i).padStart(40,'0'),name:i===11?'Treasury':'Wallet '+i,tags:[]}));
 h.ctx.state={wallets};const rows=wallets.map(w=>({dataset:{wallet:w.key},hidden:false}));
 h.$('wallet-cards').querySelectorAll=()=>rows;
 h.ctx.filterHomeWallets();
 assert.deepEqual(rows.map(r=>r.hidden),[...Array(8).fill(false),...Array(4).fill(true)]);
 assert.equal(h.$('home-wallet-more').hidden,false);assert.equal(h.$('home-wallet-more').textContent,'Show all 12');assert.equal(h.$('home-wallet-more').attrs['aria-expanded'],'false');
 h.$('home-wallet-search').value='treasury';h.ctx.filterHomeWallets();
 assert.deepEqual(rows.map(r=>r.hidden),[...Array(11).fill(true),false]);assert.equal(h.$('home-wallet-more').hidden,true);assert.equal(h.$('home-wallet-empty').hidden,true);
 h.$('home-wallet-search').value='';vm.runInContext('homeWalletsExpanded=true',h.ctx);h.ctx.filterHomeWallets();
 assert.equal(rows.every(r=>!r.hidden),true);assert.equal(h.$('home-wallet-more').textContent,'Show top 8');
});

test('the sidebar marks routine status with a dot and names only what needs attention',()=>{
 const h=harness(),saved=wallet(1,'Saved'),gaps=wallet(2,'Gaps',5,{chains:[chain(true)]}),fresh=wallet(3,'Fresh',null,{analysed_at:null});
 h.ctx.state={wallets:[saved,gaps,fresh]};h.ctx.renderWallets();
 const list=h.$('wallet-list').innerHTML,row=name=>list.slice(list.indexOf('aria-label="Select '+name+'"')).split('</button>')[0];
 assert.match(row('Saved'),/data-mode="saved"/);assert.doesNotMatch(row('Saved'),/wallet-nav-address/);
 assert.match(row('Gaps'),/data-mode="partial" title="Saved · gaps"/);assert.doesNotMatch(row('Gaps'),/wallet-nav-address/);
 assert.match(row('Fresh'),/<span class="wallet-nav-address">Not checked<\/span>/);
 assert.match(row('Gaps'),/title="0x2{40} · Saved with gaps"/,'The full status stays available on hover.');
 assert.equal(h.$('wallet-count').textContent,3);
});

test('page structure keeps one summary card and no repeated taglines',()=>{
 for(const removed of ['Your saved balances, in one place.','ACROSS YOUR WALLETS','RESEARCH HISTORY','WALLET OVERVIEW','Follow your research at a glance.','50 rows per page.','home-stats','class="home-summary"','portfolio-scope-bar'])assert.equal(html.includes(removed),false,removed);
 assert.match(html,/<section id="home-summary" class="hero"/);assert.match(html,/<section class="hero wallet-summary"/);
 assert.match(html,/<link rel="stylesheet" href="\/ui\.css"><link rel="stylesheet" href="\/compact\.css">/,'The compact layer loads last.');
 assert.equal((html.match(/<th scope="col">Value<\/th>/g)||[]).length,2);assert.doesNotMatch(html,/Known value/);
 // Phones get a sheet for info tips and two-line token rows without repeated labels.
 assert.match(css,/@media\(max-width:640px\)[\s\S]*\.info-pop \{ position:fixed;/);assert.match(css,/#content \.token-table \.mobile-label \{ display:none; \}/);
 assert.doesNotMatch(source,/function marketLinks\(|holding-markets|Where your assets are/);
 // Narrow screens: a name keeps its own line instead of breaking beside buttons or values.
 const phone=css.slice(css.indexOf('@media(max-width:640px)'));
 assert.match(phone,/\.wallet-header \.wallet-identity \{ flex:1 1 100%; \}/);assert.match(phone,/\.wallet-header #address \{[^}]*text-overflow:ellipsis; \}/);
 assert.match(phone,/\.holdings-toolbar \.token-search \{ flex:1 1 100%; \}/);
 assert.match(css,/\.holder-name \{ display:flex; flex-wrap:nowrap;/);assert.match(css,/\.holder-table-token \.holder-balance \{ grid-column:1 \/ -1; grid-row:2; justify-self:start;/);
 assert.doesNotMatch(fs.readFileSync('viewer/static/report.css','utf8'),/\.account-card-heading \{ flex-wrap:wrap/,'An older phone rule dropped long wallet names under their icon.');
 assert.match(css,/\.sell-figure \+ \.figure:last-child \{ grid-column:span 2; \}/);
});

test('rebuilding a token page keeps its allocation panel',()=>{
 const h=harness(),listeners=[];let panels=0;
 const pools=Array.from({length:7},(_,i)=>({pool:'0x'+String(i).repeat(40),venue:'Uniswap',pair:[{symbol:'AAA'},{symbol:'BBB'}],url:'https://example.com/pool/'+i,liquidity_usd:100,observed_at:'2026-11-13T00:00:00Z'}));
 const token={id:'1:0x'+'a'.repeat(40),symbol:'AAA',name:'Token A',chain_id:1,address:'0x'+'a'.repeat(40),environment:'mainnet',balance:'5',value_usd:10,unpriced_count:0,wallet_count:0,wallets:[],links:[],market_pools:pools,network:{id:1,name:'Ethereum'},analysis_times:null,price_times:null,sell_out_summary:null};
 Object.assign(h.ctx,{state:{paged:true,wallets:[],details:{networks:[]}},routeData:{token},routeLoading:false,selectedView:'token',selectedToken:token.id,selectedNetwork:null,document:{title:''},
  coinIcon:()=>'<i></i>',venueMark:()=>'',policyBadge:()=>'',policyPanel:()=>'',unitPrice:String,quantity:String,compactQuantity:String,safeURL:url=>url,timeRange:()=>'Not recorded',CapitalUI:{render:()=>{panels++;}}});
 h.$('detail-view').querySelectorAll=selector=>selector==='[data-token-pool-page]'?['prev','next'].map(direction=>({dataset:{tokenPoolPage:direction},addEventListener:(type,handler)=>listeners.push([direction,handler])})):[];
 h.$('detail-view').querySelector=()=>null;
 vm.runInContext(slice('function venueMark(','function aggregateRow('),h.ctx);vm.runInContext(slice('function explorerLink(','async function poll(){'),h.ctx);
 h.ctx.renderDetail();assert.equal(panels,1);assert.match(h.$('detail-view').innerHTML,/1–5 of 7/);
 listeners.find(([direction])=>direction==='next')[1]();
 assert.equal(panels,2,'Paging markets rebuilds the view and restores the panel.');assert.match(h.$('detail-view').innerHTML,/6–7 of 7/);
 assert.match(h.$('detail-view').innerHTML,/<section class="hero detail-hero"/);assert.doesNotMatch(h.$('detail-view').innerHTML,/TOKEN OVERVIEW|record-address|page-footer/);
});

test('each wallet has a stable face from its address; bars state how far an estimate reaches',()=>{
 const h=harness(),run=code=>vm.runInContext(code,h.ctx);
 const first=run("walletAvatar('0x"+'1a'.repeat(20)+"')"),again=run("walletAvatar('0X"+'1A'.repeat(20)+"')"),other=run("walletAvatar('0x"+'c4'.repeat(20)+"')");
 assert.equal(first,again,'The same address always draws the same face.');assert.notEqual(first,other);
 const near=Array.from({length:6},(_,i)=>run("walletAvatar('0x"+String(i+1).padStart(40,'0')+"')"));
 assert.equal(new Set(near).size,6,'Addresses that differ in one digit still get different faces.');
 assert.match(first,/^<svg class="wallet-avatar" viewBox="-1 -1 7 7" aria-hidden="true"/);assert.doesNotMatch(first,/style=/,'The page allows no inline styles.');
 for(const address of ['0x'+'1a'.repeat(20),'0x'+'c4'.repeat(20),'0x'+'7e'.repeat(20),'','not-an-address']){
  const cells=[...run('walletAvatar('+JSON.stringify(address)+')').matchAll(/<rect x="(\d)" y="(\d)" width="1" height="1"\/>/g)].map(m=>m[1]+':'+m[2]);
  assert.ok(cells.length>0,'Every wallet draws at least one cell.');
  for(const cell of cells){const [x,y]=cell.split(':').map(Number);assert.ok(cells.includes((4-x)+':'+y),'The pattern mirrors left to right.');}
 }
 assert.match(run("ratioBar(91,100,'Reach')"),/<span class="ratio" title="Reach"><progress class="allocation-progress" value="91" max="100" aria-label="Reach">91%<\/progress><small>91%<\/small><\/span>/);
 assert.match(run("ratioBar(0.001,100,'Reach')"),/<small>< 1%<\/small>/);assert.match(run("ratioBar(150,100,'Reach')"),/value="100" max="100"[^>]*>100%/,'A bar never passes its base.');
 assert.equal(run("ratioBar(null,100,'Reach')"),'');assert.equal(run("ratioBar(5,0,'Reach')"),'');assert.equal(run("ratioBar(5,null,'Reach')"),'');
 assert.equal(run("walletTokenValue({groups:[{id:'wallet',value_usd:10},{id:'mintclub',value_usd:5},{id:'uniswap',value_usd:99},{id:'wallet',value_usd:null}]},1)"),15,'Platform positions are not part of the base.');
 assert.equal(run("walletTokenValue(null,7)"),7);assert.equal(run("walletTokenValue({groups:[{id:'uniswap',value_usd:3}]},undefined)"),null);
});
test('lists start with priced holdings and name what they leave out in one line',()=>{
 const h=harness(),run=code=>vm.runInContext(code,h.ctx);
 for(const helper of ['const valueFilter=','const unpricedNote='])vm.runInContext(source.split('\n').find(line=>line.startsWith(helper)),h.ctx);
 assert.match(html,/aria-label="Token value filter"><button data-min="all" aria-pressed="false">All<\/button><button data-min="0" aria-pressed="true">Priced<\/button><button data-min="5"/);
 assert.match(source,/\[null,0,5,10\]\.map\(n=>`<button data-min="\$\{n\?\?'all'\}"/,'The network list offers the same four choices.');
 assert.equal(run('unpricedNote(0)'),'','Nothing hidden, nothing said.');
 assert.equal(run('unpricedNote(1317)'),'<span>1,317 unpriced hidden</span><button type="button" class="quiet-button" data-clear-value-filter>Show all</button>');
 assert.equal(run("valueFilter('all')"),null);assert.equal(run("valueFilter('0')"),0);assert.equal(run("valueFilter('10')"),10);
 assert.match(css,/\.holdings-filter-note \{ flex-direction:row; align-items:center; justify-content:flex-start;[^}]*padding:0; border:0;/,'The count is a quiet line, not a card.');
 assert.match(css,/@media\(max-width:640px\) \{ \.holdings-filter-note \.quiet-button \{ min-height:40px;/,'The button stays easy to tap on a phone.');
});
