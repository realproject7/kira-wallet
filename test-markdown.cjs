const assert=require('node:assert/strict');
const {render}=require('./viewer/static/markdown.js');
const html=render('# Known facts\n\n**Unknown is not zero.**\n\n| Token | Price |\n| --- | ---: |\n| DEMO | Unknown |\n\n- Check coverage\n- Keep your keys\n\n```js\n<script>alert(1)</script>\n```');
assert.match(html,/<h3>Known facts<\/h3>/);assert.match(html,/<table>/);assert.match(html,/<td>Unknown<\/td>/);assert.match(html,/<ul>/);
assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
for(const input of ['<img src=x onerror=alert(1)>','[click](javascript:alert(1))','![pixel](https://example.com/private)','<svg onload=alert(1)>','**<iframe src=x>**','`<script>`']){
 const safe=render(input);assert.doesNotMatch(safe,/<(?:script|img|svg|iframe|a)\b/i);
}
assert.match(render('before\n```\nunclosed <tag>'),/&lt;tag&gt;/);
assert.match(render('1. first\n2. second'),/<ol>/);
assert.match(render('| A | B |\n|---|---|\n| one |'),/<td><\/td>/);
console.log('Safe Markdown, table, code and raw HTML/link boundaries passed.');
