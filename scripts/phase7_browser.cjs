// Real production-image browser audit with local test-only HTTPS ingress.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const fs=require('node:fs'), path=require('node:path'), https=require('node:https'), http=require('node:http');
const root=path.join(__dirname,'..'), out=path.join(root,'phase7-evidence/browser');fs.mkdirSync(out,{recursive:true});
const contextData=JSON.parse(fs.readFileSync(path.join(root,'phase7-evidence/extended-browser-context.json'))).browser_context;
const results={checks:[],screenshots:[],pageErrors:[],xssDialogs:0,fixture:contextData.fixture_label};
const record=(name,value)=>{results.checks.push({name,value});fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));console.log(name,JSON.stringify(value));};
let browser,context,page;
const streams=new Set();
const server=https.createServer({key:fs.readFileSync(path.join(root,'.ui-qa/localhost.key')),cert:fs.readFileSync(path.join(root,'.ui-qa/localhost.crt'))},(req,res)=>{
  if(req.url==='/__phase7/disconnect'&&req.method==='POST'){for(const s of streams)s.destroy();res.end('AUDIT_DISCONNECT');return;}
  if(req.url.endsWith('/stream')){streams.add(res);res.on('close',()=>streams.delete(res));}
  const upstream=http.request({hostname:'127.0.0.1',port:req.url.startsWith('/api/v1')?18101:13100,path:req.url,method:req.method,headers:{...req.headers,'x-forwarded-proto':'https'}},incoming=>{res.writeHead(incoming.statusCode,incoming.headers);incoming.pipe(res);});
  upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end('Audit upstream unavailable');});res.on('close',()=>upstream.destroy());req.pipe(upstream);
});
const sizes=[[1440,900],[1280,800],[768,1024],[390,844]];
async function screenshot(name,w,h){await page.setViewportSize({width:w,height:h});await page.waitForTimeout(250);const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);const file=`${name}-${w}.png`;await page.screenshot({path:path.join(out,file)});results.screenshots.push({file,width:w,height:h,overflow});}
async function captureAll(name){for(const size of sizes)await screenshot(name,...size);await page.setViewportSize({width:1440,height:900});}
async function main(){
  await new Promise(resolve=>server.listen(13300,'127.0.0.1',resolve));
  browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:900},reducedMotion:'no-preference'});page=await context.newPage();page.setDefaultTimeout(15000);
  page.on('pageerror',error=>results.pageErrors.push(error.message));page.on('dialog',async dialog=>{results.xssDialogs++;await dialog.dismiss();});
  const streamRequests=[];page.on('request',r=>{if(r.url().includes('/stream'))streamRequests.push({queryToken:/[?&]token=/.test(r.url()),bearer:!!r.headers().authorization});});
  await page.goto('https://localhost:13300');await page.getByRole('heading',{name:'Welcome back'}).waitFor();await captureAll('auth');
  await page.getByLabel('Email',{exact:true}).fill(contextData.email);await page.getByLabel('Password',{exact:true}).fill('Phase7OnlyStrongPass123!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('heading',{name:'Your workspaces'}).waitFor();record('login',true);await captureAll('dashboard');
  await page.reload();await page.getByRole('heading',{name:'Your workspaces'}).waitFor();const cookies=await context.cookies();record('refresh_and_storage',{refreshCookie:cookies.filter(c=>c.name.includes('refresh')).map(c=>({httpOnly:c.httpOnly,secure:c.secure,sameSite:c.sameSite})),localStorage:await page.evaluate(()=>localStorage.length),sessionStorage:await page.evaluate(()=>sessionStorage.length)});
  await page.getByLabel('Search workspaces').fill('no-phase7-match');record('search_empty',await page.getByText('No matching workspaces',{exact:true}).isVisible());await page.getByRole('button',{name:'Clear search'}).click();
  const trigger=page.getByRole('button',{name:'Create workspace',exact:true}).first();await trigger.click();let dialog=page.getByRole('dialog',{name:'Create workspace',exact:true});await dialog.waitFor();
  for(let n=0;n<10;n++)await page.keyboard.press('Tab');record('dialog_focus_containment',await page.evaluate(()=>!!document.activeElement.closest('dialog')));await captureAll('dialog');
  await page.keyboard.press('Escape');const retained=await page.locator('dialog[open]').count();await page.waitForTimeout(220);record('animated_close',{openImmediately:retained,closedAfter220ms:await page.locator('dialog[open]').count()===0,focusRestored:await trigger.evaluate(e=>e===document.activeElement)});
  await page.emulateMedia({reducedMotion:'reduce'});await trigger.click();await page.keyboard.press('Escape');record('reduced_motion_close',await page.locator('dialog[open]').count()===0);
  await page.goto(`https://localhost:13300/workspaces/${contextData.workspace_id}`);await page.getByLabel('Investigation objective',{exact:true}).waitFor();await captureAll('workspace');
  const filename='phase7-<img src=x onerror=alert(1)>.txt';const payload='<script>alert(1)</script>\n<img src=x onerror=alert(1)>\nAUTHORED PHASE7 XSS INPUT';
  await page.locator('input[type=file]').setInputFiles({name:filename,mimeType:'text/plain',buffer:Buffer.from(payload)});
  const source=page.getByRole('button',{name:/phase7-.*img/}).first();await source.waitFor({timeout:60000});await source.click();await page.getByRole('dialog').waitFor();await captureAll('source-xss-preview');record('source_xss',{scriptNodes:await page.locator('dialog script').count(),imageNodes:await page.locator('dialog img').count(),dialogs:results.xssDialogs});await page.keyboard.press('Escape');
  for(const [w,h] of sizes){await page.setViewportSize({width:w,height:h});if(w<1024)await page.getByRole('button',{name:/^Sources/}).click();await screenshot('sources',w,h);if(w<1024)await page.getByRole('button',{name:'Investigation',exact:true}).click();await screenshot('investigation',w,h);if(w<1024)await page.getByRole('button',{name:/^Trace/}).click();await screenshot('trace',w,h);}
  await page.setViewportSize({width:1440,height:900});await page.getByLabel('Investigation objective',{exact:true}).fill('Phase7 test provider-unavailable request');await page.getByLabel('Investigation objective',{exact:true}).press('Control+Enter');await page.getByText('No final report produced',{exact:true}).waitFor({timeout:45000});await captureAll('provider-failure');record('provider_failure_explicit',true);
  await page.goto(`https://localhost:13300/workspaces/${contextData.workspace_id}?investigation=${contextData.actual_investigation_id}`);await page.waitForTimeout(3000);await captureAll('actual-worker-completion');record('actual_worker_report',{bodyHasApplicationError:(await page.locator('body').innerText()).includes('Application error'),pageErrors:[...results.pageErrors]});
  await page.goto(`https://localhost:13300/workspaces/${contextData.workspace_id}?investigation=${contextData.fixture_investigation_id}`);await page.getByRole('heading',{name:'Executive summary'}).waitFor();await captureAll('authored-report-xss');record('report_xss',{dialogs:results.xssDialogs,scriptPayloadElements:await page.locator('#summary script,#claims img').count()});
  const before=streamRequests.length;await context.request.post('https://localhost:13300/__phase7/disconnect');await page.waitForTimeout(4000);record('stream_reconnect',{additionalRequests:streamRequests.length-before,requests:streamRequests});
  await page.setViewportSize({width:390,height:844});record('touch_targets',await page.locator('button:visible').evaluateAll(es=>es.map(e=>({label:e.getAttribute('aria-label')||e.textContent.trim().slice(0,70),width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})).filter(x=>x.width<44||x.height<44)));
  await page.setViewportSize({width:1280,height:800});await page.evaluate(()=>document.documentElement.style.zoom='2');await page.screenshot({path:path.join(out,'report-css-zoom-200.png')});record('css_zoom_200',{overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),limitation:'CSS zoom sanity, not browser UI zoom certification'});await page.evaluate(()=>document.documentElement.style.zoom='');
  await page.goto('https://localhost:13300');await page.getByRole('heading',{name:'Your workspaces'}).waitFor();await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('heading',{name:'Welcome back'}).waitFor();await page.reload();await page.getByRole('heading',{name:'Welcome back'}).waitFor();record('logout_reload',true);
  await page.goto('https://localhost:13300/phase7-missing');await page.getByRole('heading',{name:'Page not found'}).waitFor();await captureAll('not-found');record('done',true);
}
main().catch(async e=>{results.failure=e.message;console.error(e.message);if(page)await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));await browser?.close();server.close();});
