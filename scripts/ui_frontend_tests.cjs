const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '../frontend');
const localRequire = createRequire(path.join(root, 'package.json'));
const ts = localRequire('typescript');
const React = localRequire('react');
const { renderToStaticMarkup } = localRequire('react-dom/server');
const cache = new Map();
function load(file) {
  file = path.resolve(file);
  if (cache.has(file)) return cache.get(file);
  const exports = {}; cache.set(file, exports);
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const resolve = name => {
    if (!name.startsWith('.') && !name.startsWith('@/')) return localRequire(name);
    const base = name.startsWith('@/') ? path.join(root, 'src', name.slice(2)) : path.resolve(path.dirname(file), name);
    return load(['.ts', '.tsx'].map(extension => base + extension).find(candidate => fs.existsSync(candidate)));
  };
  vm.runInNewContext(compiled, { exports, require: resolve, process, console, Map, Set, URL, Intl, Date, Math, JSON, Number, String, Array, Object, RegExp, Boolean, Error });
  return exports;
}
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const src = file => path.join(root, 'src', file);
const { Brief, excerpt, sharedLeadLines } = load(src('components/casefile/Brief.tsx'));
const { Inspector } = load(src('components/casefile/Inspector.tsx'));
const { InvestigationField, StageBar, useStageDetail } = load(src('components/casefile/InvestigationField.tsx'));
const { FailureView } = load(src('components/casefile/FailureView.tsx'));
const { EvidenceChart } = load(src('components/casefile/EvidenceChart.tsx'));
const { StatusBadge } = load(src('components/ui/Primitives.tsx'));
const { LiveActivityStepper } = load(src('components/workspace/LiveActivityStepper.tsx'));
const { groupByDay } = load(src('components/casefile/Rail.tsx'));
const { deriveInvestigationStage, observedInvestigationStages, describeEvent } = load(src('lib/investigation-stages.ts'));
const { buildBrief, indexLineage, chartFromCalculation, sharedFigures, dedupeClaims, explainReason } = load(src('lib/brief-model.ts'));
const { layoutTrack, binRanges, unitAt, unitLabel, trackPaths, trackTicks, keyboardStops } = load(src('lib/source-track.ts'));
const { failureCopy } = load(src('lib/failure-copy.ts'));
const { formatBytes, formatNumber, formatDuration } = load(src('lib/utils.ts'));
const { normalizeStreamError } = load(src('hooks/useInvestigationStream.ts'));
const { resolveTheme, THEME_BOOTSTRAP_SCRIPT } = load(src('lib/theme.ts'));

// ---------------------------------------------------------------- fixtures
const claim = { claim_id: 'T1', statement: 'In 2026, the sample was 0.30000000004.', epistemic_type: 'fact', confidence_score: null, citations: [], calculation_ids: [], supporting_claims: [] };
const report = { executive_summary: 'Test only', claims: [claim], key_findings: [], inferences: [], recommendations: [], rejected_proposals: [] };
const stream = overrides => ({ objective: 'Investigate the source', connection: 'live', status: 'created', activitySummary: '', steps: [], planTasks: [], evidenceDiscovered: [], finalResponse: null, errorMessage: null, failureCode: null, timeline: [], createdAt: null, completedAt: null, workspaceId: null, ...overrides });
/** Lineage with one source, N passages, evidence ev-i on chunk-i, optional calculations. */
function lineage(count = 3, calculations = []) {
  const nodes = [{ id: 'src_S1', type: 'source', label: 'Report.pdf', data: { source_id: 'S1', modality: 'pdf' } }];
  const edges = [];
  for (let i = 1; i <= count; i += 1) {
    nodes.push({ id: `content_chunk-${i}`, type: 'extracted_content', label: `Extracted content #${i - 1}`, data: { content_id: `chunk-${i}`, locator: { page_number: i }, content: `Passage ${i}: retention fell from 91% in Q1 to 84% in Q4.` } });
    nodes.push({ id: `ev_ev-${i}`, type: 'evidence', label: 'Quote', data: { quote: `Passage ${i}` } });
    edges.push({ source: 'src_S1', target: `content_chunk-${i}`, relation: 'EXTRACTED_FROM' });
    edges.push({ source: `content_chunk-${i}`, target: `ev_ev-${i}`, relation: 'SUPPORTED_BY_CONTENT' });
  }
  for (const calc of calculations) nodes.push({ id: `calc_${calc.id}`, type: 'calculation', label: `Calc (${calc.type})`, data: { code: calc.code || 'SELECT 1', output: calc.output, reproducibility_hash: 'abcdef0123' } });
  return { session_id: 'inv', nodes, edges, claims_count: 0, citations_count: count, calculations_count: calculations.length };
}
const verified = (id, citations, extra = {}) => ({ ...claim, claim_id: id, statement: `Statement ${id} at 91% in Q1.`, citations, verification_status: 'VERIFIED', ...extra });
const briefProps = (model, extra = {}) => ({ model, objective: 'What happened?', files: [], outlines: {}, selection: null, onSelect() {}, fold: false, ...extra });
const passageMap = (lengths, extra = {}) => ({ source_id: 'S1', modality: 'pdf', processing_status: 'ready', passage_count: lengths.length, chunk_id: lengths.map((_, i) => `chunk-${i + 1}`), chunk_index: lengths.map((_, i) => i), char_length: lengths, page_number: lengths.map((_, i) => Math.floor(i / 4) + 1), audio_start_ms: lengths.map(() => null), audio_end_ms: lengths.map(() => null), heading: lengths.map(() => null), ...extra });

// ------------------------------------------------ truthfulness of the brief
test('Missing verification is never rendered as verified', () => {
  const html = render(Brief, briefProps(buildBrief({ ...report, key_findings: [{ title: 'Finding', detail: 'Observed', claim_id: 'T1' }] }, lineage())));
  assert.doesNotMatch(html, /Citation verified/); assert.doesNotMatch(html, /class="cite"/);
  assert.match(html, /0 claims with verified citations/);
});
test('A finding linked to an unverified claim carries no citation marker', () => {
  const unverified = { ...claim, citations: ['ev-1'] };
  const html = render(Brief, briefProps(buildBrief({ ...report, claims: [unverified], key_findings: [{ title: 'Finding', detail: 'Observed detail', claim_id: 'T1' }] }, lineage())));
  assert.match(html, /Observed detail/); assert.doesNotMatch(html, /aria-label="Citation 1/);
});
test('Findings with a null claim_id only join a verified claim by exact statement', () => {
  const report2 = { ...report, claims: [verified('C1', ['ev-1'])], key_findings: [
    { title: 'Exact', detail: 'Statement C1 at 91% in Q1.', claim_id: null },
    { title: 'Paraphrase', detail: 'Statement C1 at about 91% in Q1.', claim_id: null },
  ] };
  const model = buildBrief(report2, lineage());
  assert.equal(model.findings[0].join, 'exact_statement'); assert.equal(model.findings[0].claim.claimId, 'C1');
  assert.equal(model.findings[1].join, null); assert.equal(model.findings[1].claim, null);
  assert.equal(model.otherClaims.length, 0);
});
test('Identical duplicate claims are shown once; distinct claims with one id are kept', () => {
  const a = verified('C6', ['ev-1']);
  assert.equal(dedupeClaims([a, { ...a }, verified('C7', ['ev-2'])]).length, 2);
  assert.equal(dedupeClaims([a, { ...a, statement: 'Different' }]).length, 2);
});
test('Completion details only list stages observed in runtime history', () => {
  assert.deepEqual(Array.from(observedInvestigationStages([])), []);
  const stages = observedInvestigationStages([{ id: 's', type: 'synthesis.started', payload: {} }]);
  assert.equal(stages.length, 1); assert.equal(stages[0].id, 'write');
});
test('Claim verification is only reached through synthesis, never from runtime step verification', () => {
  const result = deriveInvestigationStage(stream({ status: 'verifying', timeline: [{ id: 'v', type: 'state.changed', payload: { to: 'verifying', reason: 'verified_outputs' } }] }));
  assert.equal(result.current.id, 'evidence');
});
test('Failure stage comes from the recorded failed_state, not the rolled-back history', () => {
  const failedAt = (failed_state, code = 'EVIDENCE_NOT_FOUND') => stream({ status: 'failed', failureCode: code, timeline: [
    { id: 'c', type: 'investigation.created', payload: {} },
    { id: 'f', type: 'investigation.failed', payload: { code, failed_state } },
  ] });
  assert.equal(deriveInvestigationStage(failedAt('observing')).current.id, 'evidence');
  assert.equal(deriveInvestigationStage(failedAt('executing')).current.id, 'search');
  assert.equal(deriveInvestigationStage(failedAt('synthesizing', 'PROVIDER_TIMEOUT')).current.id, 'write');
  assert.equal(deriveInvestigationStage(failedAt('synthesizing', 'EVIDENCE_INVALID')).current.id, 'verify');
  assert.equal(deriveInvestigationStage(failedAt('planning')).current.id, 'understand');
  assert.equal(deriveInvestigationStage(failedAt(undefined)).current.id, 'understand');
  const html = render(FailureView, { stream: failedAt('observing'), onAction() {}, canEdit: true });
  assert.match(html, /stopped during evidence/); assert.match(html, /EVIDENCE_NOT_FOUND/); assert.match(html, /No matching passages were found/);
  assert.match(html, /Edit question/); assert.match(html, /Add a source/);
});
test('Brief lists every recommendation and says which rest on no verified claim', () => {
  const recommendations = [1, 2, 3, 4].map(index => ({ recommendation_id: `R${index}`, title: `Action ${index}`, action: `Do ${index}`, supported_by_claims: index === 1 ? ['C1'] : [] }));
  const html = render(Brief, briefProps(buildBrief({ ...report, claims: [verified('C1', ['ev-1'])], recommendations }, lineage())));
  for (const index of [1, 2, 3, 4]) assert.match(html, new RegExp(`Do ${index}`));
  assert.equal((html.match(/Not linked to a claim with verified citations/g) || []).length, 3);
});
test('Rejected claim keeps its rejected status and is never cited', () => {
  const rejected = { ...claim, citations: ['ev-1'], verification_status: 'REJECTED', verification_errors: ['SOURCE_DELETED'] };
  const html = render(Brief, briefProps(buildBrief({ ...report, claims: [rejected] }, lineage())));
  assert.match(html, /Rejected claim/); assert.match(html, /Its source was deleted after the brief was saved/);
  assert.doesNotMatch(html, /class="cite"/); assert.match(html, /1 rejected/);
});
test('No chart is drawn from prose; only saved SQL output of two columns and two or more rows', () => {
  const html = render(Brief, briefProps(buildBrief({ ...report, claims: [verified('C1', ['ev-1'])] }, lineage())));
  assert.doesNotMatch(html, /role="img"/);
  const sql = { id: 'k', type: 'sql_query', code: 'SELECT q, r FROM t', output: [{ q: 'Q1', r: 91 }, { q: 'Q2', r: 89 }], hash: 'h' };
  assert.ok(chartFromCalculation(sql));
  assert.equal(chartFromCalculation({ ...sql, type: 'python' }), null);
  assert.equal(chartFromCalculation({ ...sql, output: [{ q: 'Q1', r: 91 }] }), null);
  assert.equal(chartFromCalculation({ ...sql, output: [{ q: 'Q1', r: 91, s: 1 }, { q: 'Q2', r: 89, s: 2 }] }), null);
  assert.equal(chartFromCalculation({ ...sql, output: [{ q: 'Q1', r: '91%' }, { q: 'Q2', r: '89%' }] }), null);
});
test('Partial ingestion and failed runtime have textual status indicators', () => {
  assert.match(render(StatusBadge, { status: 'partially_ready' }), /Partially ready/);
  assert.match(render(StatusBadge, { status: 'failed' }), /failed/);
});
test('Report text is escaped, not interpreted as HTML', () => {
  const html = render(Brief, briefProps(buildBrief({ ...report, executive_summary: '<img src=x onerror=alert(1)>' }, lineage())));
  assert.match(html, /&lt;img/); assert.doesNotMatch(html, /<img/);
});
test('Operational trace excludes reasoning and raw tool content', () => {
  const html = render(LiveActivityStepper, { streamState: { status: 'running', connection: 'reconnecting', activitySummary: '', steps: [], planTasks: [], evidenceDiscovered: [], timeline: [{ id: 'event-1', type: 'tool.started', payload: { tool: 'lookup', thought: 'PRIVATE_REASONING_TEST', tool_output: 'RAW_OUTPUT_TEST', request_id: 'safe-request-id' } }] } });
  assert.match(html, /Reconnecting/); assert.match(html, /safe-request-id/); assert.doesNotMatch(html, /PRIVATE_REASONING_TEST|RAW_OUTPUT_TEST/);
  const saved = describeEvent({ id: 'e', type: 'tool.completed', payload: { tool: 'hybrid_document_search', tool_output: 'RAW_OUTPUT_TEST' } });
  assert.equal(saved.label, 'Search completed'); assert.doesNotMatch(JSON.stringify(saved), /RAW_OUTPUT_TEST/);
});
test('Numbers and missing durations are formatted without inventing measurements', () => {
  assert.equal(formatNumber(0.30000000004), '0.3'); assert.equal(formatDuration(null), 'Not recorded');
  assert.equal(formatBytes(0), '0 B'); assert.equal(formatBytes(-1), 'Unavailable');
});
test('SSE errors always normalize to renderable text', () => {
  assert.equal(normalizeStreamError('provider failed'), 'provider failed');
  assert.equal(normalizeStreamError({ message: 'structured failure' }), 'structured failure');
  assert.equal(normalizeStreamError({ message: { nested: true } }), 'Investigation failed.');
});

// ------------------------------------------------------- truthful stages
test('First investigation stage has a current and next stage but no previous stage', () => {
  const snapshot = deriveInvestigationStage(stream({ status: 'planning' }));
  assert.equal(snapshot.current.id, 'understand'); assert.equal(snapshot.previous, null); assert.equal(snapshot.next.id, 'search');
  const html = render(StageBar, { snapshot, detail: 'Planning and searching · 0:04' });
  assert.match(html, /data-stage-id="understand" data-state="current"|data-state="current" data-stage-id="understand"/);
  assert.match(html, /Planning and searching · 0:04/); assert.doesNotMatch(html, /data-state="done"/);
});
test('Middle investigation stage derives previous, current and next from runtime state', () => {
  const snapshot = deriveInvestigationStage(stream({ status: 'running', timeline: [{ id: 'plan', type: 'plan.created', payload: {} }] }));
  assert.equal(snapshot.previous.id, 'understand'); assert.equal(snapshot.current.id, 'search'); assert.equal(snapshot.next.id, 'evidence');
});
test('The saved batch moves Writing to current; completion ends on Verification with no next', () => {
  const batch = [
    { id: 'c', type: 'investigation.created', payload: {} },
    { id: 'p', type: 'plan.created', payload: {} },
    { id: 't', type: 'tool.completed', payload: { tool: 'hybrid_document_search' } },
    { id: 's', type: 'state.changed', payload: { from: 'observing', to: 'synthesizing' } },
  ];
  const writing = deriveInvestigationStage(stream({ status: 'created', timeline: batch }));
  assert.equal(writing.current.id, 'write'); assert.equal(writing.next.id, 'verify'); assert.equal(writing.batchReceived, true);
  const complete = deriveInvestigationStage(stream({ status: 'completed' }));
  assert.equal(complete.current.id, 'verify'); assert.equal(complete.next, null); assert.equal(complete.terminal, 'completed');
});
test('A polled persisted state past planning proves the saved batch without SSE events', () => {
  // Planning through synthesis commit together, so REST can only observe created or synthesizing.
  assert.equal(deriveInvestigationStage(stream({ status: 'created' })).batchReceived, false);
  assert.equal(deriveInvestigationStage(stream({ status: 'planning' })).batchReceived, false);
  const polled = deriveInvestigationStage(stream({ status: 'synthesizing' }));
  assert.equal(polled.batchReceived, true); assert.equal(polled.current.id, 'write');
  // A failed run rolled back its batch: failure never counts as a saved batch.
  assert.equal(deriveInvestigationStage(stream({ status: 'failed' })).batchReceived, false);
});
test('Excerpts skip a running header shared across passages and a bare page label', () => {
  const header = 'Northstar Analytics Ltd. - FY2026 Business Performance Review';
  const a = `${header}\nPage 2\n1. Executive Summary\nRevenue grew 18.4%.`;
  const b = `${header}\nPage 4\n3. Customer Performance\nRetention fell.`;
  const lone = 'Only passage\nPage 1\nBody text.';
  const skip = sharedLeadLines([a, b, lone]);
  assert.equal(skip.has(header), true); assert.equal(skip.has('Only passage'), false);
  assert.equal(excerpt(a, 90, skip), '“1. Executive Summary Revenue grew 18.4%.”');
  // A first line that is not repeated is real content and stays.
  assert.equal(excerpt(lone, 90, skip), '“Only passage Page 1 Body text.”');
  assert.match(excerpt(b, 12, skip), /^“3\. Customer…”$/);
});
test('Stage sub-status is the stage description plus real elapsed time from persisted timestamps', () => {
  const ago = seconds => new Date(Date.now() - seconds * 1000).toISOString();
  const Probe = ({ value }) => React.createElement('span', null, useStageDetail(value));
  const detailOf = value => render(Probe, { value }).replace(/^<span>|<\/span>$/g, '');
  const planning = stream({ status: 'planning', createdAt: ago(65) });
  assert.equal(detailOf(planning), `${deriveInvestigationStage(planning).detail} · 1:05`);
  // No persisted start time: the description alone, never an invented clock.
  const untimed = stream({ status: 'planning' });
  assert.equal(detailOf(untimed), deriveInvestigationStage(untimed).detail);
  // Writing counts from the persisted transition into synthesis, not from creation.
  const writing = stream({ status: 'created', createdAt: ago(100), timeline: [
    { id: 'p', type: 'plan.created', payload: {}, timestamp: ago(90) },
    { id: 's', type: 'state.changed', payload: { from: 'observing', to: 'synthesizing' }, timestamp: ago(12) },
  ] });
  assert.equal(deriveInvestigationStage(writing).current.id, 'write');
  assert.equal(detailOf(writing), `${deriveInvestigationStage(writing).detail} · 0:12`);
  // Terminal runs show no running sub-status.
  assert.equal(detailOf(stream({ status: 'completed', createdAt: ago(65) })), '');
  assert.equal(detailOf(stream({ status: 'failed', createdAt: ago(65) })), '');
});
test('Runtime transition moves the next stage into the current position', () => {
  const before = deriveInvestigationStage(stream({ status: 'planning' }));
  const afterState = stream({ status: 'running', timeline: [{ id: 'tool', type: 'tool.started', payload: { tool: 'search' } }] });
  const after = deriveInvestigationStage(afterState);
  assert.equal(before.next.id, after.current.id); assert.equal(after.previous.id, before.current.id);
  assert.match(render(StageBar, { snapshot: after, detail: null }), /data-state="current" data-stage-id="search"/);
});
test('Completion collapses to a factual receipt', () => {
  const model = buildBrief({ ...report, claims: [verified('C1', ['ev-1']), verified('C2', ['ev-2', 'ev-3'])] }, lineage());
  const html = render(Brief, briefProps(model));
  assert.match(html, /3 cited passages/); assert.match(html, /2 claims with verified citations/); assert.match(html, /Grounded/);
  assert.match(html, /Grounded in 3 cited passages from 1 source/);
});
test('Failure stops on the real last stage and exposes normalized technical detail', () => {
  const failed = stream({ status: 'failed', errorMessage: 'Unable to reach the analysis provider.', failureCode: 'PROVIDER_UNAVAILABLE', timeline: [{ id: 'tool', type: 'tool.started', payload: {} }, { id: 'f', type: 'investigation.failed', payload: { code: 'PROVIDER_UNAVAILABLE', failed_state: 'executing' } }] });
  const snapshot = deriveInvestigationStage(failed); assert.equal(snapshot.current.id, 'search'); assert.equal(snapshot.next, null); assert.equal(snapshot.stageKnown, true);
  const html = render(FailureView, { stream: failed, onAction() {}, canEdit: true });
  assert.match(html, /Unable to reach the analysis provider/); assert.match(html, /PROVIDER_UNAVAILABLE/); assert.match(html, /Try again/);
  assert.match(html, /stopped during searching/); assert.doesNotMatch(html, /stopped during writing/);
  assert.match(render(StageBar, { snapshot, detail: 'Stopped here' }), /data-state="failed"/);
});
test('A failed run whose failure event was not received names no stage', () => {
  // Polled status alone cannot say where a run stopped: the failure rolls back its progress.
  for (const timeline of [[], [{ id: 'tool', type: 'tool.started', payload: {} }]]) {
    const polled = stream({ status: 'failed', failureCode: 'EVIDENCE_NOT_FOUND', timeline });
    const snapshot = deriveInvestigationStage(polled);
    assert.equal(snapshot.stageKnown, false);
    const bar = render(StageBar, { snapshot, detail: 'Stopped · stage not received' });
    assert.doesNotMatch(bar, /data-state="(failed|done|current)"/); assert.match(bar, /stage not received/);
    const view = render(FailureView, { stream: polled, onAction() {}, canEdit: true });
    assert.doesNotMatch(view, /stopped during/); assert.match(view, /EVIDENCE_NOT_FOUND/);
  }
  const cancelled = deriveInvestigationStage(stream({ status: 'cancelled' }));
  assert.equal(cancelled.stageKnown, false);
  assert.equal(deriveInvestigationStage(stream({ status: 'planning' })).stageKnown, true);
});
test('Unknown runtime events do not invent a later stage', () => {
  const snapshot = deriveInvestigationStage(stream({ status: 'planning', timeline: [{ id: 'unknown', type: 'provider.telepathy', payload: {} }] }));
  assert.equal(snapshot.current.id, 'understand');
});
test('Stage derivation cannot advance from elapsed time alone', () => {
  const value = stream({ status: 'created', timeline: [] });
  assert.equal(deriveInvestigationStage(value).current.id, deriveInvestigationStage(value).current.id);
  assert.doesNotMatch(fs.readFileSync(src('lib/investigation-stages.ts'), 'utf8'), /setTimeout|setInterval/);
});
test('Reduced motion removes stage and answer animation without hiding state', () => {
  const css = fs.readFileSync(src('app/globals.css'), 'utf8');
  assert.match(css, /prefers-reduced-motion:\s*reduce/); assert.match(css, /animation:\s*none\s*!important/); assert.match(css, /stage-window-enter/);
  // The fold becomes a 150 ms cross-fade and threads appear without drawing.
  assert.match(css, /reduced-fade 150ms/); assert.match(css, /stroke-dashoffset:\s*0\s*!important/);
});
test('Brief preserves structured findings, inline citations and actions', () => {
  const cited = verified('CLM-001', ['evidence-1']);
  const graph = lineage(1); graph.nodes[2].id = 'ev_evidence-1'; graph.edges[1].target = 'ev_evidence-1';
  const rich = { ...report, key_findings: [{ title: 'Retention changed', detail: 'Retention declined.', claim_id: 'CLM-001' }], claims: [cited], recommendations: [{ recommendation_id: 'REC-1', title: 'Review retention', action: 'Inspect churn cohorts.', priority: 'high', supported_by_claims: ['CLM-001'], supporting_inference_ids: [] }] };
  const html = render(Brief, briefProps(buildBrief(rich, graph)));
  assert.match(html, /Test only/); assert.match(html, /Retention changed/); assert.match(html, /aria-label="Citation 1: open the cited passage"/);
  assert.match(html, /Inspect churn cohorts/); assert.match(html, /uncited; the claims below carry the citations/);
});
test('A verified SQL calculation gets an ƒ marker and a labelled chart; others get no chart', () => {
  const output = [{ quarter: 'Q1', retention: 91 }, { quarter: 'Q2', retention: 89 }, { quarter: 'Q3', retention: 87 }, { quarter: 'Q4', retention: 84 }];
  const graph = lineage(1, [{ id: 'calc-1', type: 'sql_query', output }, { id: 'calc-2', type: 'python_sandbox', output: 4 }]);
  const model = buildBrief({ ...report, claims: [verified('C1', ['ev-1'], { calculation_ids: ['calc-1', 'calc-2'] })] }, graph);
  assert.equal(model.charts.length, 1);
  const html = render(Brief, briefProps(model));
  assert.match(html, /ƒ1/); assert.match(html, /ƒ2/); assert.match(html, /Axis starts at/); assert.match(html, /SQL calculation · query and output in the inspector/);
  assert.equal((html.match(/role="img"/g) || []).length, 1);
  const bars = render(EvidenceChart, { chart: { ...model.charts[0], rows: [{ label: 'North', value: 5 }, { label: 'South', value: 9 }] }, onInspect() {} });
  assert.doesNotMatch(bars, /Axis starts at/);
});

// --------------------------------------------------------- source track
test('Track segments are ordered and proportional to passage length', () => {
  const layout = layoutTrack(passageMap([100, 300, 100]), { width: 200, gap: 0, minSegment: 3 });
  assert.equal(layout.binned, false); assert.equal(layout.units.length, 3);
  assert.ok(Math.abs(layout.units[1].width - 3 * layout.units[0].width) < 2.5);
  assert.ok(layout.units[0].x < layout.units[1].x && layout.units[1].x < layout.units[2].x);
});
test('Large sources bin into contiguous ranges covering every passage exactly once', () => {
  const lengths = Array.from({ length: 1500 }, (_, i) => 200 + (i % 7) * 40);
  const ranges = binRanges(lengths, 100);
  assert.equal(ranges.length, 100); assert.equal(ranges[0][0], 0); assert.equal(ranges[ranges.length - 1][1], 1500);
  for (let i = 1; i < ranges.length; i += 1) assert.equal(ranges[i][0], ranges[i - 1][1]);
  const states = new Map([['chunk-1204', 'cited'], ['chunk-1205', 'evidence']]);
  const layout = layoutTrack(passageMap(lengths), { width: 300, states });
  assert.equal(layout.binned, true);
  const bin = layout.units.find(unit => unit.start <= 1203 && unit.end > 1203);
  assert.equal(bin.state, 'cited'); assert.equal(bin.citedCount, 1);
  assert.match(unitLabel(passageMap(lengths), bin), /^Passages 1,\d{3}–1,\d{3} · p\.\d+–\d+ · 1 cited/);
});
test('Track hit-testing, labels, ticks and keyboard stops use the real passage metadata', () => {
  const map = passageMap([100, 100, 100, 100, 100, 100, 100, 100]);
  const states = new Map([['chunk-2', 'evidence'], ['chunk-6', 'cited']]);
  const layout = layoutTrack(map, { width: 400, states });
  assert.equal(unitAt(layout, 0), 0); assert.equal(unitAt(layout, 399), 7); assert.equal(unitAt(layout, layout.units[5].x + 1), 5);
  assert.equal(unitLabel(map, layout.units[5], { citedBy: new Map([['chunk-6', [1, 3]]]) }), 'Passage 6 of 8, page 2, cited by claims 1, 3');
  assert.equal(unitLabel(map, layout.units[1]), 'Passage 2 of 8, page 1, retrieved as evidence, not cited');
  assert.deepEqual(Array.from(keyboardStops(layout)), [1, 5]);
  assert.deepEqual(Array.from(trackTicks(map, layout).map(tick => tick.label)), ['p.1', 'p.2']);
  // Long labels on a binned track never overlap: each tick clears the previous label's width.
  const pages = 260; const many = { ...map, passage_count: pages, chunk_id: Array.from({ length: pages }, (_, i) => `c${i}`), chunk_index: Array.from({ length: pages }, (_, i) => i), char_length: Array(pages).fill(900), page_number: Array.from({ length: pages }, (_, i) => i + 1), audio_start_ms: Array(pages).fill(null), audio_end_ms: Array(pages).fill(null), heading: Array(pages).fill(null) };
  const ticks = trackTicks(many, layoutTrack(many, { width: 552 }));
  for (let i = 1; i < ticks.length; i += 1) assert.ok(ticks[i].x - ticks[i - 1].x >= Math.ceil(ticks[i - 1].label.length * 5.6) + 12);
  const paths = trackPaths(layout, 6);
  assert.ok(paths.cited.length > 0 && paths.evidence.length > 0); assert.equal(paths.dots.length, 1);
});

// ------------------------------------------------ provenance & wording
test('During a run evidence stays neutral: no cited segments and no verified seal', () => {
  const index = indexLineage(lineage(3));
  const map = passageMap([100, 100, 100]);
  const running = stream({ status: 'synthesizing', timeline: [{ id: 's', type: 'state.changed', payload: { to: 'synthesizing' }, timestamp: '2026-09-23T10:00:00Z' }] });
  const html = render(InvestigationField, { stream: running, files: [{ id: 'S1', file_name: 'Report.pdf', modality: 'pdf', processing_status: 'ready' }], tables: [], outlines: { S1: map }, evidence: index.passages, calculations: index.calculations, selection: null, onSelect() {}, canCancel: true, folding: false });
  assert.match(html, /Evidence · 3 passages/); assert.match(html, /3 of 3 passages retrieved as evidence/);
  assert.match(html, /class="cited" d=""/); assert.doesNotMatch(html, /Citation verified/);
  const inspector = render(Inspector, { selection: { kind: 'passage', chunkId: 'chunk-1' }, tab: 'passage', onTab() {}, onSelect() {}, onClose() {}, model: null, evidence: index.passages, outlines: { S1: map }, files: [], tables: [], completed: false, stream: running, onCancel() {}, onOpenSource() {}, passageRef: { current: null } });
  assert.match(inspector, /Retrieved as evidence/); assert.doesNotMatch(inspector, /Citation verified/); assert.match(inspector, /data-cited="false"/);
});
test('Verified wording states that the citation chain, not the conclusion, was checked', () => {
  const model = buildBrief({ ...report, claims: [verified('C1', ['ev-1'])] }, lineage());
  const props = { selection: { kind: 'passage', chunkId: 'chunk-1', claimId: 'C1' }, tab: 'passage', onTab() {}, onSelect() {}, onClose() {}, model, evidence: new Map(), outlines: {}, files: [], tables: [], completed: true, stream: stream({ status: 'completed' }), onCancel() {}, onOpenSource() {}, passageRef: { current: null } };
  const html = render(Inspector, props);
  assert.match(html, /Citation verified/); assert.match(html, /This checks the citation chain, not the conclusion/);
  assert.match(html, /text match, not verification/); assert.match(html, /<mark>91%<\/mark>/);
  const brief = render(Brief, briefProps(model));
  assert.doesNotMatch(brief.replace(/with verified citations/g, ''), />\s*Verified\s*</);
});
test('Shared passages are grouped by chunk and report every citing claim', () => {
  const model = buildBrief({ ...report, claims: [verified('C1', ['ev-1']), verified('C2', ['ev-1', 'ev-2'])] }, lineage());
  assert.deepEqual(Array.from(model.citedBy.get('chunk-1')), [1, 2]); assert.equal(model.citationOrder.length, 2);
  assert.equal(model.claims[1].citations[0].number, 1);
});
test('Unresolvable citations are reported, never drawn', () => {
  const model = buildBrief({ ...report, claims: [verified('C1', ['ev-missing'])] }, lineage());
  assert.deepEqual(Array.from(model.claims[0].unresolved), ['ev-missing']); assert.equal(model.citedChunkIds.size, 0);
});
test('Figure chips are deterministic text matches between claim and passage', () => {
  assert.deepEqual(Array.from(sharedFigures('Retention fell from 91% in Q1 to 84% in Q4; revenue $112.5 million', 'fell from 91% in Q1 to 84% in Q4 and $112.5 million')), ['91%', 'Q1', '84%', 'Q4', '$112.5 million']);
  assert.deepEqual(Array.from(sharedFigures('Grew 18.4%', 'grew 18.5%')), []);
});
test('Reason codes and failure codes read as plain language', () => {
  assert.equal(explainReason('DUPLICATE_CLAIM_ID:CLM-6'), 'The model reused a claim ID, so every claim sharing it was set aside.');
  assert.equal(failureCopy('EVIDENCE_NOT_FOUND').title, 'No matching passages were found');
  assert.equal(failureCopy('SOMETHING_NEW').title, 'The investigation could not finish');
});
test('History groups by calendar day in order', () => {
  const now = new Date();
  const earlier = new Date(now.getTime() - 26 * 3600 * 1000);
  const groups = groupByDay([{ id: 'a', objective: 'A', status: 'completed', created_at: now.toISOString() }, { id: 'b', objective: 'B', status: 'failed', created_at: earlier.toISOString() }]);
  assert.equal(groups[0].label, 'Today'); assert.ok(groups.length === 2);
});
test('Theme preference resolves System to the operating system setting before paint', () => {
  assert.equal(resolveTheme('system', true), 'light'); assert.equal(resolveTheme('system', false), 'dark'); assert.equal(resolveTheme('dark', true), 'dark');
  assert.match(THEME_BOOTSTRAP_SCRIPT, /prefers-color-scheme: light/); assert.match(THEME_BOOTSTRAP_SCRIPT, /dataset\.theme/);
});
