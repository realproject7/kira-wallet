'use strict';
// Native selects remain the data source. The visible control and popup are custom.
const KiraSelect=(()=>{
  const entries=new Map();let opened=null,search='',searchTimer;
  function close(focus=false){if(!opened)return;opened.popup.hidden=true;opened.button.setAttribute('aria-expanded','false');opened.button.removeAttribute('aria-activedescendant');if(focus)opened.button.focus();opened=null;}
  function refresh(){for(const entry of entries.values()){const option=entry.select.selectedOptions[0];entry.label.textContent=option?.textContent||'Choose';entry.button.disabled=entry.select.disabled;}}
  function focusOption(index){if(!opened)return;const options=[...opened.popup.querySelectorAll('[role="option"]')];if(!options.length)return;opened.index=(index+options.length)%options.length;for(const [i,node] of options.entries())node.classList.toggle('highlighted',i===opened.index);const node=options[opened.index];opened.button.setAttribute('aria-activedescendant',node.id);node.scrollIntoView({block:'nearest'});}
  function open(entry){close();refresh();opened=entry;const options=[...entry.select.options].filter(o=>!o.disabled);
    entry.popup.innerHTML=options.map((o,i)=>`<div role="option" id="${entry.select.id}-option-${i}" aria-selected="${String(o.selected)}" data-value="${escapeHTML(o.value)}">${escapeHTML(o.textContent)}<span aria-hidden="true">${o.selected?'✓':''}</span></div>`).join('');
    (entry.select.closest('dialog')||document.body).append(entry.popup);entry.popup.hidden=false;entry.button.setAttribute('aria-expanded','true');
    const rect=entry.button.getBoundingClientRect(),height=Math.min(280,entry.popup.scrollHeight),below=innerHeight-rect.bottom-10;
    entry.popup.style.width=Math.min(Math.max(rect.width,180),innerWidth-20)+'px';entry.popup.style.left=Math.max(10,Math.min(rect.left,innerWidth-entry.popup.offsetWidth-10))+'px';
    entry.popup.style.top=(below<height&&rect.top>height?rect.top-height-6:Math.min(rect.bottom+6,innerHeight-height-10))+'px';
    focusOption(Math.max(0,options.findIndex(o=>o.selected)));
  }
  function choose(value){if(!opened)return;const select=opened.select;select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));close(true);refresh();}
  function enhance(){for(const select of document.querySelectorAll('select')){
    if(entries.has(select)||!select.id)continue;
    const wrapper=document.createElement('div');wrapper.className='kira-select';select.before(wrapper);wrapper.append(select);select.classList.add('custom-select-source');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    const label=document.createElement('span'),button=document.createElement('button');button.type='button';button.className='kira-select-trigger';button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');button.setAttribute('aria-label',select.closest('label')?.querySelector('span')?.textContent||select.closest('label')?.childNodes[0]?.textContent?.trim()||'Choose an option');
    button.append(label);button.insertAdjacentHTML('beforeend','<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>');wrapper.append(button);
    const popup=document.createElement('div');popup.className='kira-select-popup';popup.id=select.id+'-listbox';popup.setAttribute('role','listbox');popup.setAttribute('aria-label',button.getAttribute('aria-label'));popup.hidden=true;document.body.append(popup);button.setAttribute('aria-controls',popup.id);
    const entry={select,label,button,popup,index:0};entries.set(select,entry);
    button.addEventListener('click',()=>opened===entry?close():open(entry));select.addEventListener('change',refresh);
    select.addEventListener('invalid',event=>{event.preventDefault();button.focus();});
    popup.addEventListener('click',event=>{const option=event.target.closest('[role="option"]');if(option)choose(option.dataset.value);});
    button.addEventListener('keydown',event=>{
      if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape','Tab'].includes(event.key)){
        if(event.key==='Tab'){close();return;}event.preventDefault();
        if(event.key==='Escape'){close(true);return;}
        if(!opened||opened!==entry){open(entry);if(event.key==='Enter'||event.key===' ')return;}
        const count=entry.popup.children.length;
        if(event.key==='ArrowDown')focusOption(entry.index+1);else if(event.key==='ArrowUp')focusOption(entry.index-1);else if(event.key==='Home')focusOption(0);else if(event.key==='End')focusOption(count-1);else choose(entry.popup.children[entry.index]?.dataset.value);
      }else if(event.key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
        if(opened!==entry)open(entry);clearTimeout(searchTimer);search+=event.key.toLowerCase();const index=[...entry.popup.children].findIndex(n=>n.textContent.toLowerCase().startsWith(search));if(index>=0)focusOption(index);searchTimer=setTimeout(()=>search='',500);
      }
    });
  }refresh();}
  document.addEventListener('pointerdown',event=>{if(opened&&!opened.button.contains(event.target)&&!opened.popup.contains(event.target))close();});
  document.addEventListener('close',()=>close(),true);
  window.addEventListener('resize',()=>close());window.addEventListener('scroll',event=>{if(opened&&!opened.popup.contains(event.target))close();},true);
  new MutationObserver(records=>{if(records.some(r=>r.target.tagName==='SELECT'||r.target.closest?.('select')||[...r.addedNodes].some(n=>n.nodeType===1&&(n.matches?.('select')||n.querySelector?.('select')))))enhance();}).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
  enhance();return {refresh,close};
})();
