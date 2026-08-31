// end-to-end: real Python server (127.0.0.1:8899), no stub
const { chromium } = require('playwright');
const SCHEMA = { actors: [
    {id:'ceo',name:'CEO',category:'executive',external:false},
    {id:'cfo',name:'CFO',category:'finance',external:false},
    {id:'marketing',name:'Marketing',category:'marketing',external:false},
    {id:'sales',name:'Sales',category:'sales',external:false}],
  relationships: [
    {source:'ceo',target:'cfo',label:'oversees finance',type:'gov'},
    {source:'ceo',target:'marketing',label:'oversees marketing',type:'gov'},
    {source:'cfo',target:'marketing',label:'approves marketing budget',type:'flow'}]};

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1000, height: 800 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  // point the page's relative /api call at the real local Python server
  await page.route('**/api/detect_phantoms', async route => {
    const res = await fetch('http://127.0.0.1:8903/api/detect_phantoms',
      { method: 'POST', headers: {'Content-Type':'application/json'}, body: route.request().postData() });
    route.fulfill({ status: res.status, contentType: 'application/json', body: await res.text() });
  });

  await page.goto('file://' + process.cwd() + '/index.html');
  await page.click('#btn-edit');
  await page.fill('#json-input', JSON.stringify(SCHEMA));
  await page.click('#btn-apply-json');
  await page.waitForTimeout(4000);
  await page.click('#btn-detect-phantom');
  await page.waitForTimeout(2500);

  const ghosts = await page.evaluate(() => [...document.querySelectorAll('#scene text')]
    .map(t => t.textContent).filter(l => l.includes('suggested')).sort());
  console.log('ghosts:', ghosts);
  console.log('message:', await page.textContent('#json-error'));

  // hover a ghost, check its box explains itself
  const box = await page.evaluate(() => {
    for (const g of document.querySelectorAll('#scene g g'))
      if (g.querySelector('text').textContent.includes('CMO')) {
        g.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:200, clientY:200}));
        return document.getElementById('node-hover-box').innerText;
      }
  });
  console.log('--- ghost hover box ---\n' + box);
  const wrap = await page.$('.canvas-wrap'); await wrap.screenshot({ path: 'tests/e2e.png' });

  const ok = ghosts.length === 2 && errors.length === 0;
  console.log('page errors:', errors);
  console.log(ok ? 'PASS' : 'FAIL');
  await browser.close(); process.exit(ok ? 0 : 1);
})();
