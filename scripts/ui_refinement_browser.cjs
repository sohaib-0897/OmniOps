// Authored API fixtures exercise presentation only; no live data is changed.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = '.tmp_test/refinement';
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let status = 'planning';
    const workspace = { id: 'visual', name: 'Quarterly review' };
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let data = {};
      if (path.endsWith('/stream')) return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': fixture\n\n' });
      if (path.endsWith('/auth/refresh')) data = { token: { access_token: 'visual-fixture' } };
      else if (path.endsWith('/files')) data = [{ id: 'source', file_name: 'quarterly_report.pdf', modality: 'pdf', byte_size: 42800, processing_status: 'ready', created_at: '2026-09-23T00:00:00Z' }];
      else if (path.endsWith('/tables')) data = [];
      else if (path.endsWith('/evidence')) data = { nodes: [], edges: [] };
      else if (path.endsWith('/workspaces')) data = [workspace];
      else if (path.includes('/investigations/')) data = { id: 'run', status: status === 'failed' ? 'failed' : 'running', current_state: status, objective: 'Analyze this report and identify the major risks.', steps: [], failure_code: status === 'failed' ? 'PROVIDER_UNAVAILABLE' : null, failure_message: status === 'failed' ? 'The analysis provider is unavailable.' : null };
      else data = workspace;
      await route.fulfill({ json: { success: true, data } });
    });
    const capture = async (name, width) => {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(450);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: `${out}/${name}-${width}.png` });
    };
    await page.goto('http://localhost:3100/workspaces/visual');
    await page.getByRole('heading', { name: 'What do you want to investigate?' }).waitFor();
    for (const width of [1600, 768, 390]) await capture('empty', width);
    assert.equal(await page.locator('aside:visible').count(), 0);
    await page.setViewportSize({ width: 1600, height: 900 });
    assert.equal(await page.locator('aside:visible').count(), 1);
    const field = page.getByRole('textbox', { name: 'Investigation question' });
    const initialHeight = (await page.locator('.composer-frame').boundingBox()).height;
    assert.ok(initialHeight >= 110 && initialHeight <= 140, `Initial composer height ${initialHeight}`);
    await field.fill(Array(12).fill('A detailed question about this report.').join('\n'));
    assert.ok((await field.boundingBox()).height > 200);
    await field.fill('');
    assert.ok((await field.boundingBox()).height < 100);
    await page.getByRole('button', { name: 'Find risks', exact: true }).click();
    await field.press('Shift+Enter');
    assert.ok((await field.inputValue()).includes('\n'));
    await page.goto('http://localhost:3100/workspaces/visual?investigation=run');
    await page.locator('[data-stage-id="understand"]').waitFor();
    await capture('first-stage', 1600);
    for (const [next, stage] of [['executing', 'investigate'], ['verifying', 'verify'], ['synthesizing', 'prepare']]) {
      status = next;
      await page.locator(`[data-stage-id="${stage}"]`).waitFor();
      await capture(stage, 1600);
    }
    await page.getByRole('button', { name: 'Activity', exact: true }).last().click();
    await page.getByRole('dialog', { name: 'Investigation activity' }).waitFor();
    await capture('activity', 1600);
    await page.keyboard.press('Escape');
    await capture('stage-mobile', 390);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    status = 'verifying';
    await page.locator('[data-stage-id="verify"]').waitFor();
    assert.equal(await page.locator('.investigation-stage-window').evaluate(el => el.getAnimations({ subtree: true }).length), 0);
    status = 'failed';
    await page.getByRole('button', { name: 'Try again' }).waitFor();
    await capture('failure', 390);
    assert.equal(await page.locator('.stage-next').count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ pass: true, initialComposerHeight: initialHeight, pageErrors: errors.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
