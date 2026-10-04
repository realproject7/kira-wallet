'use strict';
// Deliberately small Markdown subset. Raw HTML and links remain escaped text.
(function(root) {
  const escape = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function inline(text) {
    return String(text).split(/(`[^`\n]+`)/g).map(part => part.startsWith('`') && part.endsWith('`')
      ? '<code>' + escape(part.slice(1,-1)) + '</code>'
      : escape(part).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>')).join('');
  }
  const cells = line => line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>c.trim());
  const divider = line => cells(line).length > 1 && cells(line).every(c=>/^:?-{3,}:?$/.test(c));
  function render(input) {
    const lines = String(input).slice(0,100000).replace(/\r\n?/g,'\n').split('\n'), output=[];
    for(let i=0;i<lines.length;) {
      const line=lines[i];
      if(!line.trim()){i++;continue;}
      if(/^\s*```/.test(line)) {
        const code=[];i++;
        while(i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i++]);
        if(i<lines.length)i++;
        output.push('<pre><code>'+escape(code.join('\n'))+'</code></pre>');continue;
      }
      if(line.includes('|')&&i+1<lines.length&&divider(lines[i+1])) {
        const headers=cells(line).slice(0,12),rows=[];i+=2;
        while(i<lines.length&&lines[i].trim()&&lines[i].includes('|'))rows.push(cells(lines[i++]));
        output.push('<div class="markdown-table"><table><thead><tr>'+headers.map(c=>'<th scope="col">'+inline(c)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+headers.map((_,c)=>'<td>'+inline(row[c]||'')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>');continue;
      }
      const heading=line.match(/^#{1,6}\s+(.+)$/);
      if(heading){output.push('<h3>'+inline(heading[1])+'</h3>');i++;continue;}
      const list=line.match(/^\s*(?:([-*+])|\d+\.)\s+(.+)$/);
      if(list) {
        const ordered=!list[1],items=[];
        while(i<lines.length){const row=lines[i].match(ordered?/^\s*\d+\.\s+(.+)$/:/^\s*[-*+]\s+(.+)$/);if(!row)break;items.push('<li>'+inline(row[1])+'</li>');i++;}
        output.push('<'+(ordered?'ol':'ul')+'>'+items.join('')+'</'+(ordered?'ol':'ul')+'>');continue;
      }
      if(/^>\s?/.test(line)){output.push('<blockquote>'+inline(line.replace(/^>\s?/,''))+'</blockquote>');i++;continue;}
      const paragraph=[inline(line)];i++;
      while(i<lines.length&&lines[i].trim()&&!/^\s*(?:```|#{1,6}\s|[-*+]\s|\d+\.\s|>)/.test(lines[i])&&!(i+1<lines.length&&lines[i].includes('|')&&divider(lines[i+1])))paragraph.push(inline(lines[i++]));
      output.push('<p>'+paragraph.join('<br>')+'</p>');
    }
    return output.join('');
  }
  const api={render};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.KiraMarkdown=api;
})(typeof globalThis!=='undefined'?globalThis:this);
