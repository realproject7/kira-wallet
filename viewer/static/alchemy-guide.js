'use strict';
const guideCopy=document.getElementById('guide-copy'),guideStatus=document.getElementById('guide-copy-status');
guideCopy.addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText('kira connect alchemy');guideStatus.textContent='Command copied. Run it in your terminal.';}
  catch{guideStatus.textContent='Select the command above to copy it.';}
});
