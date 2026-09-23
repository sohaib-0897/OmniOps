// Capture the actual local investigation. No response fixtures or provider mocks.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const account = JSON.parse(fs.readFileSync('.tmp_test/design-live/account.json'));
    const ids = JSON.parse(fs.readFileSync('.tmp_test/design-live/context.json'));
    await page.goto('http://localhost');
    await page.getByLabel('Email', { exact: true }).fill(account.email);
    await page.getByLabel('Password', { exact: true }).fill(account.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.getByRole('heading', { name: 'Your workspaces' }).waitFor();
    await page.locator(`a[href="/workspaces/${ids.workspaceId}"]`).first().click();
    await page.getByRole('heading', { name: 'What do you want to investigate?' }).waitFor();
    await page.evaluate(id => { history.pushState(null, '', `${location.pathname}?investigation=${id}`); dispatchEvent(new PopStateEvent('popstate')); }, ids.investigationId);
    await page.getByRole('button', { name: 'Try again' }).waitFor();
    await page.screenshot({ path: `.tmp_test/design-live/${process.env.UI_PHASE || 'before'}-real-failure.png` });
    await page.getByRole('button', { name: /Activity|View technical activity/ }).last().click();
    await page.getByRole('dialog', { name: 'Investigation activity' }).waitFor();
    await page.screenshot({ path: `.tmp_test/design-live/${process.env.UI_PHASE || 'before'}-real-activity.png` });
    console.log('Actual report investigation and persisted failure captured.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
