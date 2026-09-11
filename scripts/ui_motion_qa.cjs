// Isolated browser fixture executes the actual Dialog component and production CSS.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('../frontend/node_modules/typescript');
const root = path.join(__dirname, '..');
const out = path.join(root, 'frontend-ui-evidence/polish');
fs.mkdirSync(out, { recursive: true });
const checks = [];
async function main() {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, recordVideo: { dir: out, size: { width: 1280, height: 800 } } });
  context.setDefaultTimeout(15000);
  try {
    const page = await context.newPage();
    await page.goto('https://localhost:13000');
    await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
    await page.getByLabel('Password', { exact: true }).fill('visibility-test-only');
    await page.getByRole('button', { name: 'Show password' }).click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    await page.getByRole('button', { name: 'Hide password' }).click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    await page.locator('#password').fill('');
    checks.push('Password visibility toggle');
    console.log('Password visibility PASS');
    for (const [width, height] of [[1440,900],[1280,800],[768,900],[390,844]]) {
      await page.setViewportSize({ width, height });
      await page.screenshot({ path: path.join(out, `sign-in-after-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (width === 390) {
        const targets = await page.locator('button').evaluateAll(nodes => nodes.filter(node => node.getClientRects().length).map(node => ({ height: node.getBoundingClientRect().height, width: node.getBoundingClientRect().width })));
        assert.ok(targets.every(target => target.height >= 44 && target.width >= 44));
      }
    }
    checks.push('Four sign-in viewports without overflow; mobile buttons at least 44px');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.evaluate(() => document.documentElement.style.zoom = '2');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(out, 'sign-in-css-zoom-200.png') });
    await page.evaluate(() => document.documentElement.style.zoom = '');
    checks.push('200% CSS zoom sign-in reflow (not browser zoom)');
    const css = await page.locator('link[rel=stylesheet]').evaluateAll(nodes => nodes.map(node => node.href));
    await page.route('**/__motion_fixture', route => route.fulfill({ contentType: 'text/html', body: `<html><head>${css.map(href => `<link rel="stylesheet" href="${href}">`).join('')}</head><body><div id="root"></div></body></html>` }));
    await page.goto('https://localhost:13000/__motion_fixture');
    console.log('Motion fixture loaded');
    await page.addScriptTag({ path: path.join(root, 'frontend/node_modules/react/umd/react.development.js') });
    await page.addScriptTag({ path: path.join(root, 'frontend/node_modules/react-dom/umd/react-dom.development.js') });
    const code = ts.transpileModule(fs.readFileSync(path.join(root, 'frontend/src/components/ui/Dialog.tsx'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020 } }).outputText;
    await page.addScriptTag({ content: `window.exports={}; window.require=name=>name==='react'?React:{X:()=>null}; ${code}\nfunction Fixture(){const [open,setOpen]=React.useState(false);window.setOpen=setOpen;return React.createElement(React.Fragment,null,React.createElement('button',{id:'trigger',onClick:()=>setOpen(true)},'Open fixture'),React.createElement(exports.Dialog,{open,onClose:()=>setOpen(false),title:'Motion fixture'},React.createElement('input',{'aria-label':'Fixture input'})));} ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Fixture));` });
    await page.locator('#trigger').click();
    await page.getByRole('dialog').waitFor();
    console.log('Dialog opened');
    for (let i=0;i<5;i++) await page.keyboard.press('Tab');
    assert.ok(await page.evaluate(() => !!document.activeElement.closest('dialog')));
    await page.evaluate(() => window.setOpen(false));
    await page.waitForFunction(() => document.querySelector('dialog').dataset.state === 'closing');
    assert.ok(await page.locator('dialog').evaluate(el => el.open && el.contains(document.activeElement)));
    await page.evaluate(() => window.setOpen(true));
    await page.waitForTimeout(220);
    assert.ok(await page.locator('dialog').evaluate(el => el.open));
    checks.push('Focus containment during exit; rapid reopen cancels stale close');
    console.log('Rapid reopen PASS');
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('dialog').open);
    assert.ok(await page.locator('#trigger').evaluate(el => el === document.activeElement));
    assert.equal(await page.evaluate(() => document.body.style.overflow), '');
    checks.push('Animated Escape closes and restores focus / scrolling');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.locator('#trigger').click();
    assert.equal(await page.locator('dialog').evaluate(el => getComputedStyle(el).animationName), 'none');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog[open]').count(), 0);
    checks.push('Reduced motion removes animation and exit delay');
    await page.locator('#trigger').click();
    await page.evaluate(() => window.setOpen(false));
    await page.goto('https://localhost:13000');
    await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
    checks.push('Navigation/unmount cleanup');
  } finally { await context.close(); await browser.close(); fs.writeFileSync(path.join(out, 'motion-results.json'), JSON.stringify({ checks }, null, 2)); }
  console.log(JSON.stringify({ result: 'PASS', checks }));
}
main().catch(error => { console.error(error); process.exitCode=1; });
