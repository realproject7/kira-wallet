'use strict';
const scenes=[
 {title:'A return, not a sticker price.',detail:'The full-balance burn quote returns USDC. Another token still needs a sell route.',line:'The recorded quote returns 110 USDC before gas. That is different from a token’s displayed market value.',context:'Sample: full-balance burn quote'},
 {title:'LOOK has a price, not a quote.',detail:'The other holding, LOOK, still needs a full-balance sell route and gas estimate. Its displayed price is not recoverable value.',line:'KIRA has a saved return quote. LOOK does not. I’ll keep that difference visible while we check its exit route.',context:'Sample: unquoted LOOK position'},
 {title:'Your account. Your context.',detail:'Connect your own Codex or Claude CLI. Choose which wallet facts may reach its model service.',line:'Connect your own AI account when you’re ready. You choose what I can see. Your keys stay with you.',context:'Sample: explicit permissions'}
];
let current=0,speechTimer;
function showScene(index){
 current=index;const scene=scenes[index],stage=document.querySelector('.stage');
 stage.dataset.scene=String(index);stage.classList.add('speaking');
 document.querySelector('#finding-title').textContent=scene.title;document.querySelector('#finding-detail').textContent=scene.detail;document.querySelector('#kira-line').textContent=scene.line;document.querySelector('#speech-context').textContent=scene.context;
 document.querySelectorAll('[data-scene]').forEach(button=>{if(button.tagName==='BUTTON')button.setAttribute('aria-pressed',String(Number(button.dataset.scene)===index));});
 document.querySelector('#kira-explaining').setAttribute('aria-hidden',String(index===1));document.querySelector('#kira-researching').setAttribute('aria-hidden',String(index!==1));
 clearTimeout(speechTimer);speechTimer=setTimeout(()=>stage.classList.remove('speaking'),4200);
}
document.querySelectorAll('button[data-scene]').forEach(button=>button.addEventListener('click',()=>showScene(Number(button.dataset.scene))));
document.querySelector('#next-line').addEventListener('click',()=>showScene((current+1)%scenes.length));
document.querySelector('#motion-toggle').addEventListener('click',event=>{const paused=document.body.classList.toggle('paused');event.currentTarget.setAttribute('aria-pressed',String(paused));event.currentTarget.textContent=paused?'Resume motion':'Pause motion';});
document.addEventListener('visibilitychange',()=>document.body.classList.toggle('hidden',document.hidden));
