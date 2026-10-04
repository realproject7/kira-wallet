'use strict';
// Loaded only by watching-preview.py. Not shipped in the npm package or normal viewer.
(function() {
  const A='0x'+'1'.repeat(40), B='0x'+'2'.repeat(40), C='0x'+'3'.repeat(40);
  let calls=0, mode='normal', deferred=null;
  function provider(result) {
    const listeners=new Map();
    return {
      on(event,listener) { if(!listeners.has(event))listeners.set(event,new Set());listeners.get(event).add(listener); },
      removeListener(event,listener) { listeners.get(event)?.delete(listener); },
      emit(event,value) { for(const listener of listeners.get(event)||[])listener(value); },
      request({method}) {
        calls++; document.getElementById('fixture-requests').textContent='Account requests: '+calls;
        if(method!=='eth_requestAccounts')return Promise.reject({code:4200});
        if(mode==='reject')return Promise.reject({code:4001});
        if(mode==='pending')return new Promise(resolve=>{deferred=()=>resolve(result);});
        return Promise.resolve(result);
      }
    };
  }
  const first=provider([B,C]), second=provider([A]);
  const rows=[
    {provider:first,info:{uuid:'11111111-1111-4111-8111-111111111111',name:'Synthetic wallet A',rdns:'test.synthetic.a',icon:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" onload="document.title=\'UNSAFE\'" width="32" height="32"><rect width="32" height="32" fill="%23745b95" /></svg>'}},
    {provider:second,info:{uuid:'22222222-2222-4222-8222-222222222222',name:'Synthetic <img src=x onerror=alert(1)>',rdns:'test.synthetic.b',icon:'https://remote.invalid/unsafe.png'}}
  ];
  const announce=()=>rows.forEach(detail=>window.dispatchEvent(new CustomEvent('eip6963:announceProvider',{detail})));
  window.addEventListener('eip6963:requestProvider',announce);
  const tools=document.createElement('div');tools.id='fixture-tools';
  tools.style.cssText='border-bottom:1px dashed #b6a0cb;padding:10px 0;margin-bottom:20px;font-size:12px';
  const label=document.createElement('strong');label.textContent='Synthetic fixture. No extension or RPC.';
  const metrics=document.createElement('p');metrics.innerHTML='<span id="fixture-requests">Account requests: 0</span> · <span id="fixture-jobs">Jobs: 0</span> · <span id="fixture-transport">Registration: normal</span>';
  tools.append(label,metrics);
  async function transport(command) {
    await fetch('/__fixture/transport',{method:'POST',body:command});
    document.getElementById('fixture-transport').textContent='Registration: '+command;
  }
  const controls=[['Normal access',()=>{mode='normal';}],['Decline access',()=>{mode='reject';}],['Delay response',()=>{mode='pending';}],
    ['Delay registration',()=>transport('hold')],
    ['Accept registration',()=>transport('accept')],
    ['Fail registration',()=>transport('reject')],
    ['Resolve response',()=>{deferred?.();deferred=null;}],['Change accounts',()=>first.emit('accountsChanged',[C])],
    ['Clear accounts',()=>first.emit('accountsChanged',[])],['Change network',()=>first.emit('chainChanged','0x2105')],
    ['Provider disconnect',()=>first.emit('disconnect',{code:4900})],['Announce again',announce],
    ['No providers after reload',()=>{sessionStorage.setItem('fixture-no-providers','1');location.reload();}],
    ['Hide fixture tools',()=>{tools.hidden=true;}]];
  for(const [name,action] of controls) {
    const button=document.createElement('button');button.type='button';button.textContent=name;button.className='quiet-button';
    button.style.cssText='font-size:11px;margin:3px;min-height:32px;padding:5px 8px';button.addEventListener('click',action);tools.append(button);
  }
  document.getElementById('wallet-form').prepend(tools);
  if(sessionStorage.getItem('fixture-no-providers'))sessionStorage.removeItem('fixture-no-providers');
  else announce();
  setInterval(async()=>{try{const response=await fetch('/__fixture/status');const data=await response.json();document.getElementById('fixture-jobs').textContent='Jobs: '+data.jobs;}catch{}},500);
})();
