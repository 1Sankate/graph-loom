const { chromium } = require('playwright');

const SCHEMA = {
  nodes: [
    { id: 'ceo', label: 'CEO', group: 'executive' },
    { id: 'cfo', label: 'CFO', group: 'finance' },
    { id: 'marketing', label: 'Marketing', group: 'marketing' }
  ],
  edges: [
    { source: 'ceo', target: 'cfo', label: 'oversees finance' },
    { source: 'ceo', target: 'marketing', label: 'oversees marketing' },
    { source: 'cfo', target: 'marketing', label: 'approves marketing budget' }
  ]
};

const STUB = {
  departments: {
    ceo: { name: 'CEO', leader_present: true, recommended_title: null },
    cfo: { name: 'CFO', leader_present: true, recommended_title: null },
    marketing: { name: 'Marketing', leader_present: false, recommended_title: 'CMO' }
  },
  gaps: ['marketing'],
  summary: { departments: 3, gaps: 1, coverage_pct: 67 }
};

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1000, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  await page.route('**/api/detect_phantoms', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STUB) }));

  await page.goto('file://' + process.cwd() + '/index.html');
  await page.click('#btn-edit');
  await page.fill('#json-input', JSON.stringify(SCHEMA));
  await page.click('#btn-apply-json');
  await page.waitForTimeout(4000);

  await page.click('#btn-detect-phantom');
  await page.waitForTimeout(2000);

  const first = await page.evaluate(() => {
    const labels = [...document.querySelectorAll('#scene text')].map(t => t.textContent);
    const dashed = document.querySelectorAll('#scene line[stroke-dasharray]').length;
    return { labels, dashed };
  });

  const ghostCount = first.labels.filter(l => l.includes('suggested')).length;
  console.log('ghost nodes (want 1):', ghostCount, '|', first.labels.filter(l => l.includes('suggested')));
  console.log('dashed edges (want 3):', first.dashed);
  console.log('message:', await page.textContent('#json-error'));

  await page.click('#btn-detect-phantom');
  await page.waitForTimeout(2000);
  const second = await page.evaluate(() =>
    [...document.querySelectorAll('#scene text')].map(t => t.textContent)
      .filter(l => l.includes('suggested')).length);
  console.log('ghost nodes after 2nd click (want 1):', second);
  console.log('page errors (want none):', errors);

  const wrap = await page.$('.canvas-wrap'); await wrap.screenshot({ path: 'tests/ghosts.png' });

  const ok = ghostCount === 1 && first.dashed === 3 && second === 1 && errors.length === 0;
  console.log(ok ? 'PASS' : 'FAIL');
  await browser.close();
  process.exit(ok ? 0 : 1);
})();
