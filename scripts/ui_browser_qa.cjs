// Browser QA against the current production build and the Phase 6 HTTPS stack.
// Test account secrets remain in the ignored .ui-qa directory, never in evidence.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const out = path.join(root, 'frontend-ui-evidence');
const privateDir = path.join(root, '.ui-qa');
fs.mkdirSync(out, { recursive: true });
const results = { environment: 'Local Next.js production build, HTTPS ingress, production-mode Phase 6 backend/PostgreSQL', browser: 'Microsoft Edge / Playwright', checks: [], screenshots: [], pageErrors: [] };
const record = (name, detail = 'PASS') => { results.checks.push({ name, detail }); fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify(results, null, 2)); console.log(name, detail); };
let browser, page, context;
const capture = async (name, width = 1440, height = 900) => {
  await page.setViewportSize({ width, height }); await page.waitForTimeout(250);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  const file = `${name}-${width}.png`; await page.screenshot({ path: path.join(out, file), fullPage: false });
  results.screenshots.push({ file, width, height, horizontalOverflow: overflow });
  assert.equal(overflow, false, `Horizontal overflow: ${file}`);
};
async function main() {
  browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  page = await context.newPage(); page.on('pageerror', error => results.pageErrors.push(error.message));
  await page.goto('https://localhost:13000');
  await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
  for (const [width, height] of [[1440, 900], [1280, 800], [768, 900], [390, 844]]) await capture('sign-in', width, height);
  await page.setViewportSize({ width: 1440, height: 900 });
  const accountPath = path.join(privateDir, 'account.json');
  let account;
  if (fs.existsSync(accountPath)) account = JSON.parse(fs.readFileSync(accountPath));
  else {
    account = { email: `ui-qa-${crypto.randomBytes(5).toString('hex')}@example.com`, password: crypto.randomBytes(18).toString('base64url') + '!aA1' };
    await page.getByRole('button', { name: 'Create an account', exact: true }).click();
    await page.getByLabel('Full name', { exact: true }).fill('Interface QA');
  }
  await page.getByLabel('Email', { exact: true }).fill(account.email);
  await page.getByLabel('Password', { exact: true }).fill(account.password);
  console.log('Auth button labels:', await page.getByRole('button').allTextContents());
  const [authResponse] = await Promise.all([
    page.waitForResponse(response => /\/auth\/(login|register)$/.test(response.url()) && response.request().method() === 'POST'),
    page.getByRole('button', { name: fs.existsSync(accountPath) ? 'Sign in' : 'Create account', exact: true }).click().then(() => console.log('Auth submitted')),
  ]);
  assert.equal(authResponse.status(), 200, 'Browser auth must succeed');
  const auth = (await authResponse.json()).data;
  fs.writeFileSync(accountPath, JSON.stringify(account));
  await page.getByRole('heading', { name: 'Your workspaces' }).waitFor(); record('Browser sign-in / registration');
  for (const [width, height] of [[1440,900],[1280,800],[768,900],[390,844]]) await capture('dashboard', width, height);
  await page.getByLabel('Search workspaces').fill('no-match-polish-qa');
  await page.getByText('No matching workspaces', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Clear search' }).click();
  record('Workspace search and clear');
  await page.reload();
  await page.getByRole('heading', { name: 'Your workspaces' }).waitFor();
  const cookies = await context.cookies();
  assert.ok(cookies.some(cookie => cookie.httpOnly && cookie.secure && cookie.name.includes('refresh')));
  assert.equal(await page.evaluate(() => localStorage.length), 0);
  record('Session restoration with Secure HttpOnly cookie and no localStorage');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Create workspace', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Create workspace', exact: true });
  await dialog.getByLabel('Workspace name').fill('Operating review · UI QA');
  for (let index = 0; index < 8; index++) await page.keyboard.press('Tab');
  assert.ok(await page.evaluate(() => document.activeElement.closest('dialog') !== null));
  record('Dialog keyboard focus containment');
  await dialog.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await page.waitForURL(/\/workspaces\//); await page.getByRole('heading', { name: 'What do you need to understand?' }).waitFor();
  const workspaceId = new URL(page.url()).pathname.split('/').pop();
  fs.writeFileSync(path.join(privateDir, 'context.json'), JSON.stringify({ workspaceId, userId: auth.user.id }));
  await capture('workspace-empty');
  await page.locator('input[type=file]').setInputFiles([{ name: 'operating-review-qa.txt', mimeType: 'text/plain', buffer: Buffer.from('INTERFACE QA TEST DATA ONLY.\nQuarterly operations review.\nThe support team recorded 24 resolved requests in the sample week.\nNo production business conclusions may be drawn from this test source.') }, { name: 'quarterly-costs-qa.csv', mimeType: 'text/csv', buffer: Buffer.from('quarter,cost,team\nQ1,1200,Support\nQ2,1350,Support\nQ3,1280,Support\n') }]);
  await page.getByText('Upload queue · 2').waitFor(); await capture('upload');
  await page.getByRole('button', { name: 'operating-review-qa.txt', exact: false }).first().waitFor({ timeout: 60000 });
  await page.waitForFunction(() => document.querySelector('#panel-sources')?.textContent.includes('Ready'), { timeout: 60000 });
  record('Actual TXT / CSV upload and processing states');
  await capture('workspace-sources'); await capture('workspace-sources', 1280, 800);
  await page.getByRole('button', { name: 'operating-review-qa.txt', exact: false }).first().click();
  await page.getByRole('dialog', { name: 'operating-review-qa.txt', exact: true }).waitFor();
  await page.getByText('INTERFACE QA TEST DATA ONLY.', { exact: false }).first().waitFor();
  await capture('source-preview', 1280, 800);
  await page.keyboard.press('Escape');
  assert.ok(await page.getByRole('button', { name: 'operating-review-qa.txt', exact: false }).first().evaluate(element => element === document.activeElement));
  await page.getByRole('button', { name: 'operating-review-qa.txt', exact: false }).first().click();
  await capture('source-preview', 390, 844);
  await page.keyboard.press('Escape'); assert.equal(await page.locator('dialog[open]').count(), 0); record('Source inspection / Escape / focus return');
  for (const [width, height] of [[1024, 800], [768, 900], [390, 844]]) {
    await page.setViewportSize({ width, height });
    if (width < 1024) await page.getByRole('button', { name: /^Sources/ }).click();
    await capture('workspace-sources', width, height);
    await page.getByRole('button', { name: 'Investigation', exact: true }).click();
    await capture('composer', width, height);
    await page.getByRole('button', { name: /^Trace/ }).click(); await capture('trace-empty', width, height);
  }
  record('Responsive sources / investigation / trace navigation');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByLabel('Investigation objective', { exact: true }).fill('Interface QA: summarize the test operating review and cite only the uploaded test sources.');
  const created = page.waitForResponse(response => /\/workspaces\/[^/]+\/investigations$/.test(response.url()) && response.request().method() === 'POST');
  await page.getByLabel('Investigation objective', { exact: true }).press('Control+Enter');
  const createdResponse = await created; assert.equal(createdResponse.status(), 200);
  const investigation = (await createdResponse.json()).data;
  await page.waitForFunction(() => document.body.textContent.includes('Investigation failed'), { timeout: 60000 });
  await capture('provider-failure');
  record('Investigation creation shortcut / honest provider-unavailable failure', investigation.id);
  const streamRequests = [];
  page.on('request', request => { if (request.url().endsWith('/stream')) streamRequests.push({ queryToken: /[?&]token=/.test(request.url()), bearer: Boolean(request.headers().authorization) }); });
  await page.reload(); await page.getByText('No final report produced', { exact: true }).waitFor();
  assert.ok(page.url().includes(investigation.id));
  record('Investigation restored from URL without fabricated completion');
  await page.goto('https://localhost:13000/wallboard'); await page.getByRole('heading', { name: 'Your workspaces' }).waitFor();
  record('Legacy workspace directory route');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await page.getByRole('heading', { name: 'Welcome back' }).waitFor(); await page.reload(); await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
  record('Logout persists across reload');
  await page.goto('https://localhost:13000/missing-ui-qa-route'); await page.getByRole('heading', { name: 'Page not found' }).waitFor();
  await capture('not-found'); await capture('not-found', 390, 844); record('Consistent not-found route');
  assert.equal(results.pageErrors.length, 0, 'No browser runtime errors');
  record('Live functional browser pass');
}
main().catch(async error => { results.failure = error.message; if (page) await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {}); console.error(error.message); process.exitCode = 1; }).finally(async () => { fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify(results, null, 2)); await browser?.close(); });
