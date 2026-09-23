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
  vm.runInNewContext(compiled, { exports, require: resolve, process, console, Map, Set, URL, Intl, Date });
  return exports;
}
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const { ExecutiveReportView } = load(path.join(root, 'src/components/workspace/ExecutiveReportView.tsx'));
const { MetricChartRenderer } = load(path.join(root, 'src/components/workspace/MetricChartRenderer.tsx'));
const { StatusBadge } = load(path.join(root, 'src/components/ui/Primitives.tsx'));
const { LiveActivityStepper } = load(path.join(root, 'src/components/workspace/LiveActivityStepper.tsx'));
const { InvestigationProgress } = load(path.join(root, 'src/components/workspace/InvestigationProgress.tsx'));
const { ConversationReport } = load(path.join(root, 'src/components/workspace/ConversationReport.tsx'));
const { deriveInvestigationStage } = load(path.join(root, 'src/lib/investigation-stages.ts'));
const { observedInvestigationStages } = load(path.join(root, 'src/lib/investigation-stages.ts'));
const { formatBytes, formatNumber, formatDuration } = load(path.join(root, 'src/lib/utils.ts'));
const { normalizeStreamError } = load(path.join(root, 'src/hooks/useInvestigationStream.ts'));
const claim = { claim_id: 'T1', statement: 'In 2026, the sample was 0.30000000004.', epistemic_type: 'fact', confidence_score: null, citations: [], calculation_ids: [], supporting_claims: [] };
const report = { executive_summary: 'Test only', claims: [claim], key_findings: [], inferences: [], recommendations: [], rejected_proposals: [] };
const stream = overrides => ({ objective: 'Investigate the source', connection: 'live', status: 'created', activitySummary: '', steps: [], planTasks: [], evidenceDiscovered: [], finalResponse: null, errorMessage: null, failureCode: null, timeline: [], ...overrides });
test('Missing verification is never rendered as verified', () => {
  const html = render(ExecutiveReportView, { report });
  assert.match(html, /Verification not reported/); assert.doesNotMatch(html, /References verified/);
});
test('Conversation finding never labels an unverified claim as verified', () => {
  const html = render(ConversationReport, { report: { ...report, key_findings: [{ title: 'Finding', detail: 'Observed detail', claim_id: claim.claim_id }] } });
  assert.match(html, /verification not reported/);
  assert.doesNotMatch(html, /Inspect verified claim/);
});
test('Completion details only list stages observed in runtime history', () => {
  assert.deepEqual(Array.from(observedInvestigationStages([])), []);
  const stages = observedInvestigationStages([{ id: 's', type: 'synthesis.started', payload: {} }]);
  assert.equal(stages.length, 1);
  assert.equal(stages[0].id, 'prepare');
  const html = render(InvestigationProgress, { streamState: stream({ status: 'completed' }) });
  assert.doesNotMatch(html, /Understanding your request|Finding and reviewing evidence/);
  assert.match(html, /Stage history is not available/);
});
test('Verified outputs is a final verification transition', () => {
  const result = deriveInvestigationStage(stream({ status: 'verifying', timeline: [{ id: 'v', type: 'state.changed', payload: { to: 'verifying', reason: 'verified_outputs' } }] }));
  assert.equal(result.current.id, 'verify');
});
test('Failure stage comes from the recorded failed_state, not the rolled-back history', () => {
  const failedAt = failed_state => stream({ status: 'failed', failureCode: 'EVIDENCE_NOT_FOUND', timeline: [
    { id: 'c', type: 'investigation.created', payload: {} },
    { id: 'f', type: 'investigation.failed', payload: { code: 'EVIDENCE_NOT_FOUND', failed_state } },
  ] });
  assert.equal(deriveInvestigationStage(failedAt('observing')).current.id, 'investigate');
  assert.equal(deriveInvestigationStage(failedAt('synthesizing')).current.id, 'prepare');
  assert.equal(deriveInvestigationStage(failedAt('planning')).current.id, 'understand');
  assert.equal(deriveInvestigationStage(failedAt(undefined)).current.id, 'understand');
  const html = render(InvestigationProgress, { streamState: failedAt('observing') });
  assert.match(html, /Stopped while finding and reviewing evidence/); assert.match(html, /EVIDENCE_NOT_FOUND/);
});
test('Conversational brief shows three recommendations and retains full analysis access', () => {
  const recommendations = [1, 2, 3, 4].map(index => ({ recommendation_id: `R${index}`, title: `Action ${index}`, action: `Do ${index}`, supported_by_claims: [] }));
  const html = render(ConversationReport, { report: { ...report, recommendations } });
  assert.match(html, /Action 1/); assert.match(html, /Action 2/); assert.match(html, /Action 3/);
  assert.match(html, /View full analysis/);
  assert.match(render(ExecutiveReportView, { report: { ...report, recommendations } }), /Action 4/);
});
test('Rejected claim keeps its rejected status', () => {
  const html = render(ExecutiveReportView, { report: { ...report, claims: [{ ...claim, verification_status: 'REJECTED' }] } });
  assert.match(html, /rejected/i); assert.doesNotMatch(html, /References verified/);
});
test('Metric summary does not parse dates or values out of prose', () => {
  const html = render(MetricChartRenderer, { claims: [claim] });
  assert.doesNotMatch(html, /2026|0\.300|<svg|confidence/i); assert.match(html, /Verified references/);
});
test('Partial ingestion and failed runtime have textual status indicators', () => {
  assert.match(render(StatusBadge, { status: 'partially_ready' }), /Partially ready/);
  assert.match(render(StatusBadge, { status: 'failed' }), /failed/);
});
test('Report text is escaped, not interpreted as HTML', () => {
  const html = render(ExecutiveReportView, { report: { ...report, executive_summary: '<img src=x onerror=alert(1)>' } });
  assert.match(html, /&lt;img/); assert.doesNotMatch(html, /<img/);
});
test('Operational trace excludes reasoning and raw tool content', () => {
  const html = render(LiveActivityStepper, { streamState: { status: 'running', connection: 'reconnecting', activitySummary: '', steps: [], planTasks: [], evidenceDiscovered: [], timeline: [{ id: 'event-1', type: 'tool.started', payload: { tool: 'lookup', thought: 'PRIVATE_REASONING_TEST', tool_output: 'RAW_OUTPUT_TEST', request_id: 'safe-request-id' } }] } });
  assert.match(html, /Reconnecting/); assert.match(html, /safe-request-id/); assert.doesNotMatch(html, /PRIVATE_REASONING_TEST|RAW_OUTPUT_TEST/);
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
test('First investigation stage has a current and next stage but no empty previous row', () => {
  const snapshot = deriveInvestigationStage(stream({ status: 'planning' }));
  assert.equal(snapshot.current.id, 'understand'); assert.equal(snapshot.previous, null); assert.equal(snapshot.next.id, 'investigate');
  const html = render(InvestigationProgress, { streamState: stream({ status: 'planning' }) });
  assert.match(html, /Understanding your request/); assert.match(html, /Finding and reviewing evidence/); assert.doesNotMatch(html, /stage-previous/);
});
test('Middle investigation stage derives previous, current and next from runtime state', () => {
  const value = stream({ status: 'running', timeline: [{ id: 'plan', type: 'plan.created', payload: {} }] });
  const snapshot = deriveInvestigationStage(value);
  assert.equal(snapshot.previous.id, 'understand'); assert.equal(snapshot.current.id, 'investigate'); assert.equal(snapshot.next.id, 'verify');
});
test('Last active stage omits an empty upcoming placeholder', () => {
  const value = stream({ status: 'synthesizing', timeline: [{ id: 'synthesis', type: 'synthesis.started', payload: {} }] });
  const snapshot = deriveInvestigationStage(value);
  assert.equal(snapshot.current.id, 'prepare'); assert.equal(snapshot.next.id, 'complete');
  const complete = deriveInvestigationStage(stream({ status: 'completed' }));
  assert.equal(complete.current.id, 'complete'); assert.equal(complete.next, null);
});
test('Runtime transition moves the next stage into the current position', () => {
  const before = deriveInvestigationStage(stream({ status: 'planning' }));
  const afterState = stream({ status: 'running', timeline: [{ id: 'tool', type: 'tool.started', payload: { tool: 'search' } }] });
  const after = deriveInvestigationStage(afterState);
  assert.equal(before.next.id, after.current.id); assert.equal(after.previous.id, before.current.id);
  assert.match(render(InvestigationProgress, { streamState: afterState }), /data-stage-id="investigate"/);
});
test('Completion collapses to a factual expandable summary', () => {
  const html = render(InvestigationProgress, { streamState: stream({ status: 'completed' }), sourceCount: 3, verifiedClaimCount: 6 });
  assert.match(html, /Analysis complete/); assert.match(html, /3 sources/); assert.match(html, /6 verified claims/); assert.match(html, /Recorded investigation stages/);
});
test('Failure stops on the real last stage and exposes normalized technical detail', () => {
  const failed = stream({ status: 'failed', errorMessage: 'Unable to reach the analysis provider.', failureCode: 'PROVIDER_UNAVAILABLE', timeline: [{ id: 'tool', type: 'tool.started', payload: {} }] });
  const snapshot = deriveInvestigationStage(failed); assert.equal(snapshot.current.id, 'investigate'); assert.equal(snapshot.next, null);
  const html = render(InvestigationProgress, { streamState: failed, onRetry() {} });
  assert.match(html, /Unable to reach the analysis provider/); assert.match(html, /PROVIDER_UNAVAILABLE/); assert.match(html, /Try again/); assert.doesNotMatch(html, /Preparing your answer/);
});
test('Unknown runtime events do not invent a later stage', () => {
  const snapshot = deriveInvestigationStage(stream({ status: 'planning', timeline: [{ id: 'unknown', type: 'provider.telepathy', payload: {} }] }));
  assert.equal(snapshot.current.id, 'understand');
});
test('Stage derivation cannot advance from elapsed time alone', () => {
  const value = stream({ status: 'created', timeline: [] });
  assert.equal(deriveInvestigationStage(value).current.id, deriveInvestigationStage(value).current.id);
  assert.doesNotMatch(fs.readFileSync(path.join(root, 'src/lib/investigation-stages.ts'), 'utf8'), /setTimeout|setInterval/);
});
test('Reduced motion removes stage and answer animation without hiding state', () => {
  const css = fs.readFileSync(path.join(root, 'src/app/globals.css'), 'utf8');
  assert.match(css, /prefers-reduced-motion:\s*reduce/); assert.match(css, /animation:\s*none\s*!important/); assert.match(css, /stage-window-enter/);
});
test('Conversational answer preserves structured findings, citations and full-analysis access', () => {
  const cited = { ...claim, claim_id: 'CLM-001', citations: ['evidence-1'], verification_status: 'VERIFIED' };
  const rich = { ...report, key_findings: [{ title: 'Retention changed', detail: 'Retention declined.', claim_id: 'CLM-001' }], claims: [cited], recommendations: [{ recommendation_id: 'REC-1', title: 'Review retention', action: 'Inspect churn cohorts.', priority: 'high', supported_by_claims: ['CLM-001'], supporting_inference_ids: [] }] };
  const html = render(ConversationReport, { report: rich, onInspectClaim() {}, onInspectCitation() {}, onViewFullAnalysis() {}, fullAnalysisOpen: false });
  assert.match(html, /Test only/); assert.match(html, /Retention changed/); assert.match(html, /\[1\]/); assert.match(html, /Review retention/); assert.match(html, /View full analysis/);
});
test('Full analysis exposes an explicit calculations section when calculation lineage exists', () => {
  const calculated = { ...claim, epistemic_type: 'calculation', calculation_ids: ['calc-1'], calculation_summary: '2 + 2 = 4', verification_status: 'VERIFIED' };
  const html = render(ExecutiveReportView, { report: { ...report, claims: [calculated] } });
  assert.match(html, />Calculations</); assert.match(html, /2 \+ 2 = 4/); assert.match(html, /Inspect calculation lineage/);
});
