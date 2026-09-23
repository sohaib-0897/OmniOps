// Local QA only. Credentials and real provider results stay in ignored storage.
const fs = require('node:fs');
const crypto = require('node:crypto');
const dir = '.tmp_test/design-live';
fs.mkdirSync(dir, { recursive: true });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  let token;
  const api = async (path, body) => {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    if (!(body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(`http://localhost/api/v1${path}`, { method: body ? 'POST' : 'GET', headers, body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined });
    const result = await response.json();
    if (!result.success) throw new Error(`${path}: ${response.status} ${result.error?.code || ''}`);
    return result.data;
  };
  const account = { email: `design-${crypto.randomBytes(5).toString('hex')}@example.com`, password: `${crypto.randomBytes(20).toString('base64url')}!Aa1`, full_name: 'OmniOps Design QA' };
  fs.writeFileSync(`${dir}/account.json`, JSON.stringify(account));
  token = (await api('/auth/register', account)).token.access_token;
  const workspace = await api('/workspaces', { name: 'Business performance · Design QA', description: 'Real report investigation for local design validation.' });
  const form = new FormData();
  form.append('file', new Blob([fs.readFileSync('.tmp_test/OmniOps_Test_Business_Performance_Report.pdf')], { type: 'application/pdf' }), 'OmniOps_Test_Business_Performance_Report.pdf');
  await api(`/workspaces/${workspace.id}/files`, form);
  let files;
  for (let i = 0; i < 60; i++) {
    files = await api(`/workspaces/${workspace.id}/files`);
    if (files.some(file => ['ready', 'partially_ready', 'failed'].includes(file.processing_status))) break;
    await pause(2000);
  }
  console.log('Source processing:', files.map(file => file.processing_status).join(', '));
  const objective = 'Analyze this report. Identify the most important business findings, explain the likely causes of underperformance, highlight the major risks, and recommend the three highest-priority management actions. Support every conclusion with evidence and distinguish facts from inference.';
  const session = await api(`/workspaces/${workspace.id}/investigations`, { objective, max_steps: 12 });
  fs.writeFileSync(`${dir}/context.json`, JSON.stringify({ workspaceId: workspace.id, investigationId: session.id }));
  console.log('Real investigation started:', session.id);
  const response = await fetch(`http://localhost/api/v1/investigations/${session.id}/stream`, { headers: { Authorization: `Bearer ${token}` } });
  const controller = response.body.getReader();
  const decoder = new TextDecoder();
  let events = '';
  const stream = (async () => { try { while (true) { const part = await controller.read(); if (part.done) break; events += decoder.decode(part.value, { stream: true }); fs.writeFileSync(`${dir}/events.txt`, events); } } catch {} })();
  let last;
  for (let i = 0; i < 180; i++) {
    const current = await api(`/investigations/${session.id}`);
    fs.writeFileSync(`${dir}/session.json`, JSON.stringify(current, null, 2));
    if (current.current_state !== last) { console.log('Runtime:', current.current_state || current.status); last = current.current_state; }
    if (['completed', 'failed', 'cancelled'].includes(current.status)) {
      fs.writeFileSync(`${dir}/evidence.json`, JSON.stringify(await api(`/investigations/${session.id}/evidence`), null, 2));
      console.log('Terminal:', current.status, 'Claims:', current.final_response?.claims?.length || 0, 'Code:', current.failure_code || 'none');
      await controller.cancel(); await stream; return;
    }
    await pause(5000);
  }
  await controller.cancel();
  console.log('Observation window ended; investigation remains available.');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
