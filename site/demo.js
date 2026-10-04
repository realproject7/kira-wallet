'use strict';
const video=document.getElementById('kira-demo-video'),toggle=document.getElementById('demo-toggle');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');let manuallyPaused=false,inView=true;
function label(){toggle.textContent=video.paused?'Play demo':'Pause demo';toggle.setAttribute('aria-label',toggle.textContent);}
function sync(){if(reduced.matches||manuallyPaused||document.hidden||!inView)video.pause();else video.play().catch(()=>label());label();}
toggle.addEventListener('click',()=>{if(video.paused){manuallyPaused=false;video.play().catch(()=>label());}else{manuallyPaused=true;video.pause();}label();});
video.addEventListener('play',label);video.addEventListener('pause',label);document.addEventListener('visibilitychange',sync);reduced.addEventListener('change',sync);
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;sync();},{threshold:.15}).observe(video);
sync();
