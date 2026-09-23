// Repeatable visual baseline; all routed analytical content is authored QA data.
const { chromium } = require('../.ui-qa/node_modules/playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE || 'http://localhost';
const phase = process.env.UI_PHASE || 'before';
const out = `.tmp_test/design-${phase}`;
fs.mkdirSync(out, { recursive: true });
const claim = { claim_id: 'C1', statement: 'Revenue increased 24%, while enterprise gross retention declined from 91% to 84%.', epistemic_type: 'fact', verification_status: 'VERIFIED', citations: ['evidence-1'], calculation_ids: [], supporting_claims: [], confidence_score: null };
const report = {
  executive_summary: 'Growth accelerated. Its foundations became less secure.\n\nRevenue increased 24% during FY2026, but enterprise retention weakened and infrastructure costs grew faster than revenue. The immediate management priority is to protect existing customer value while restoring operating discipline.',
  claims: [claim, { ...claim, claim_id: 'C2', statement: 'Enterprise gross retention fell by 7 percentage points.', epistemic_type: 'calculation', calculation_ids: ['calc-1'], calculation_summary: '84% − 91% = −7 percentage points. Source: annual operating review, page 3.' }],
  key_findings: [{ title: 'Enterprise retention is deteriorating', detail: 'Enterprise gross retention declined from 91% to 84%. The report associates this decline with slower support resolution and recurring implementation delays. Those observations support a targeted retention review; they do not establish a single cause.', claim_id: 'C1' }, { title: 'Growth is placing pressure on operating capacity', detail: 'Infrastructure spending and customer-support demand increased alongside revenue. Management should review unit economics before committing to another period of expansion.', claim_id: 'C2' }],
  inferences: [{ inference_id: 'I1', statement: 'Support delays may be contributing to lower retention. The available evidence does not isolate their effect from implementation quality or customer mix.', supporting_claim_ids: ['C1'] }],
  recommendations: [{ recommendation_id: 'R1', title: 'Protect at-risk enterprise customers', action: 'Review the highest-risk accounts and assign an accountable owner to each recovery plan. Measure retention and resolution time together.', priority: 'high', supported_by_claims: ['C1'] }, { recommendation_id: 'R2', title: 'Restore infrastructure cost discipline', action: 'Review workload-level costs and establish a weekly capacity review before expanding commitments.', priority: 'high', supported_by_claims: ['C2'] }, { recommendation_id: 'R3', title: 'Validate the causes of underperformance', action: 'Compare customer cohorts and implementation outcomes before attributing the retention decline to a single cause.', priority: 'medium', supported_by_claims: ['C1'] }],
  missing_data_warnings: ['Customer-level cohort data is needed to establish causal relationships.'], contradictions: [], rejected_proposals: [],
};
const graph = { nodes: [{ id: 'source', type: 'source', label: 'FY2026 operating review.pdf', data: { source_id: 'source', modality: 'pdf' } }, { id: 'chunk', type: 'extracted_content', label: 'Page 3', data: { content: 'Enterprise gross retention: Q1 91%; Q4 84%.', page_number: 3 } }, { id: 'evidence-1', type: 'evidence', label: 'Retention evidence', data: { quote: 'Enterprise gross retention declined from 91% in Q1 to 84% in Q4.', source_id: 'source', locator: { page_number: 3 } } }, { id: 'claim_1', type: 'claim', label: claim.statement, data: { claim_code: 'C1', statement: claim.statement, verification_status: 'VERIFIED' } }], edges: [{ source: 'source', target: 'chunk', relation: 'EXTRACTED_FROM' }, { source: 'chunk', target: 'evidence-1', relation: 'SUPPORTS' }, { source: 'evidence-1', target: 'claim_1', relation: 'SUPPORTS' }] };
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = []; page.on('pageerror', e => { errors.push(e.message); console.error('Page error:', e.message); });
    let status = 'planning', hasSources = false, submittedObjective = null;
    const workspace = { id: 'design', name: 'Operating review', description: 'Quarterly business intelligence' };
    const table = { id: 'table', workspace_id: 'design', source_id: 'source', table_name: 'Quarterly metrics', row_count: 2, column_count: 2, schema_definition: ['Quarter', 'Retention'].map(name => ({ name, type: 'text', null_count: 0, null_percentage: 0, unique_count: 2, sample_values: [] })) };
    const source = { id: 'source', file_name: 'FY2026 operating review.pdf', modality: 'pdf', byte_size: 42800, processing_status: 'ready', created_at: '2026-09-23T00:00:00Z', doc_metadata: {} };
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let data = workspace;
      if (path.endsWith('/stream')) return route.fulfill({ contentType: 'text/event-stream', body: `event: state.changed\ndata: ${JSON.stringify({ id: `event-${status}`, to: status, reason: 'all_steps_complete', timestamp: '2026-09-23T00:01:00Z' })}\n\n` });
      if (path.endsWith('/auth/refresh')) data = { token: { access_token: 'fixture' } };
      else if (path.endsWith('/investigations') && route.request().method() === 'POST') { submittedObjective = route.request().postDataJSON().objective; data = { id: 'run' }; }
      else if (path.endsWith('/workspaces')) data = [workspace];
      else if (path.endsWith('/files')) data = hasSources ? [source] : [];
      else if (path.endsWith('/tables')) data = hasSources ? [table] : [];
      else if (path.includes('/tables/') && path.endsWith('/preview')) data = { ...table, columns: ['Quarter', 'Retention'], sample_rows: [{ Quarter: 'Q1', Retention: '91%' }, { Quarter: 'Q4', Retention: '84%' }] };
      else if (path.endsWith('/evidence')) data = graph;
      else if (path.endsWith('/preview')) data = [{ id: 'chunk', chunk_index: 0, content: graph.nodes[1].data.content, page_number: 3, extraction_method: 'native', semantic_search_status: 'available', lexical_search_status: 'available' }];
      else if (path.includes('/files/source')) data = source;
      else if (path.includes('/investigations/')) data = { id: 'run', objective: 'Analyze this report. Identify the most important findings, explain the risks, and recommend the three highest-priority actions.', status: ['completed', 'failed'].includes(status) ? status : 'running', current_state: status, steps: [], final_response: status === 'completed' ? report : null, failure_code: status === 'failed' ? 'PROVIDER_UNAVAILABLE' : null, failure_message: status === 'failed' ? 'OmniOps could not reach the configured model provider.' : null };
      await route.fulfill({ json: { success: true, data } });
    });
    const capture = async (name, width = 1440) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 960 });
      await page.waitForTimeout(500);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, name);
      await page.screenshot({ path: `${out}/${name}-${width}.png` });
    };
    const navigate = async (run = false) => { await page.setViewportSize({ width: 1440, height: 960 }); await page.goto(`${base}/workspaces/design${run ? '?investigation=run' : ''}`); await page.locator('#main-content').waitFor(); };
    await navigate();
    await page.getByRole('heading', { name: 'What do you want to investigate?' }).waitFor();
    for (const w of [1600, 1280, 768, 390]) await capture('empty', w);
    hasSources = true; await navigate(); await capture('sources');
    if (phase !== 'before') {
      await page.getByRole('button', { name: /Workspace sources/ }).click();
      await page.getByRole('dialog', { name: 'Workspace sources' }).waitFor();
      await capture('source-manager');
      await page.getByText('Search and filter sources', { exact: true }).click();
      await page.getByRole('textbox', { name: 'Search sources' }).fill('missing');
      await page.getByText('No matching sources', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
      await page.getByRole('button', { name: /FY2026 operating review.pdf/ }).first().click();
      await page.getByRole('dialog', { name: 'FY2026 operating review.pdf' }).waitFor();
      await capture('source-preview');
      await page.keyboard.press('Escape');
      await page.getByRole('dialog', { name: 'FY2026 operating review.pdf' }).waitFor({ state: 'hidden' });
      await page.getByRole('button', { name: /Quarterly metrics/ }).click();
      await page.getByRole('heading', { name: 'Column profile' }).waitFor();
      await capture('table-preview', 390);
      await page.keyboard.press('Escape');
      await page.getByRole('dialog', { name: 'Quarterly metrics', exact: true }).waitFor({ state: 'hidden' });
      await page.setViewportSize({ width: 1440, height: 960 });
      await page.keyboard.press('Escape');
      await page.getByRole('dialog', { name: 'Workspace sources', exact: true }).waitFor({ state: 'hidden' });
      await page.getByRole('button', { name: 'Toggle navigation' }).click();
      await capture('navigation-collapsed');
      await page.getByRole('button', { name: 'Toggle navigation' }).click();
    }
    await page.getByRole('textbox', { name: 'Investigation question' }).focus(); await capture('composer-focus');
    const composer = page.getByRole('textbox', { name: 'Investigation question' });
    await composer.fill(Array(12).fill('A longer investigation question.').join('\n'));
    assert.ok((await composer.boundingBox()).height > 200);
    await composer.fill('Compare the evidence'); await composer.press('Shift+Enter');
    assert.ok((await composer.inputValue()).includes('\n'));
    await composer.fill('');
    assert.ok((await composer.boundingBox()).height < 100);
    await page.locator('input[type=file]').last().setInputFiles({ name: 'support-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Authored UI test attachment') });
    await capture('attachment');
    await page.getByRole('button', { name: 'Remove support-notes.txt' }).click();
    await composer.fill('Compare the evidence and identify risks.');
    await composer.press('Enter');
    await page.locator('[data-stage-id=understand]').waitFor();
    assert.equal(submittedObjective, 'Compare the evidence and identify risks.');
    for (const [next, id] of [['planning', 'understand'], ['executing', 'investigate'], ['verifying', 'verify'], ['synthesizing', 'prepare']]) {
      status = next; if (next === 'planning') await navigate(true);
      await page.locator(`[data-stage-id=${id}]`).waitFor(); await capture(`stage-${id}`);
      assert.ok(await page.locator('.investigation-stage-row').count() <= 3);
    }
    await page.getByRole('button', { name: 'Activity', exact: true }).last().click();
    await capture('activity'); await page.keyboard.press('Escape');
    status = 'completed'; await page.getByText(report.key_findings[0].title, { exact: true }).first().waitFor();
    for (const w of [1600, 1280, 768, 390]) { await page.evaluate(() => scrollTo(0, 0)); await capture('answer', w); }
    await page.getByRole('button', { name: /Inspect citation/ }).first().click(); await capture('evidence', 1440);
    for (let index = 0; index < 10; index++) await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => Boolean(document.activeElement.closest('dialog'))), true);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'View full analysis' }).click();
    await page.locator('#full-analysis').scrollIntoViewIfNeeded(); await capture('full-analysis');
    await page.locator('#calculations').scrollIntoViewIfNeeded(); await capture('calculations');
    await page.getByRole('heading', { name: 'Recommendations', exact: true }).last().evaluate(el => scrollTo(0, scrollY + el.getBoundingClientRect().top - 90)); await capture('recommendations');
    status = 'failed'; await navigate(true); await page.getByRole('button', { name: 'Try again' }).waitFor(); await capture('provider-failure');
    await capture('provider-failure', 390);
    if (phase !== 'before') {
      await page.getByText('Ask another question', { exact: true }).click();
      assert.equal(await page.getByRole('textbox', { name: 'Investigation question' }).evaluate(el => el === document.activeElement), true);
      await capture('followup-expanded', 390);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      status = 'verifying'; await navigate(true);
      await page.locator('[data-stage-id=verify]').waitFor();
      assert.equal(await page.locator('.investigation-stage-window').evaluate(el => el.getAnimations({ subtree: true }).length), 0);
      await capture('reduced-motion', 390);
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ phase, screenshots: fs.readdirSync(out).length, pageErrors: errors.length }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
