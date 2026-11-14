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
 for(const helper of ['const infoTip =','const integer ='])vm.runInContext(source.split('\n').find(line=>line.startsWith(helper)),ctx);
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
 assert.match(sale,/≈ \$80/);assert.match(sale,/2 missing/);assert.match(sale,/1 limited routes/);assert.match(sale,/<details class="info-tip">[\s\S]*Includes 3 native or stable spot references/);
 assert.doesNotMatch(sale,/spot references<\/span>|Independent estimates/,'The method sits behind the info tip.');
 const rows=h.$('wallet-cards').innerHTML;
 assert.deepEqual([...rows.matchAll(/<strong>(Small|Large|Unchecked)<\/strong>/g)].map(m=>m[1]),['Large','Small','Unchecked']);
 assert.match(rows,/value="90" max="100" aria-label="Large share of priced value"/);assert.match(rows,/Not checked[\s\S]*class="allocation-empty"[\s\S]*<strong>—<\/strong>/);
 assert.equal((rows.match(/class="rank-row"/g)||[]).length,3);assert.doesNotMatch(rows,/wallet-card|Sell-out est\. sum/);
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
