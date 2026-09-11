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
const { formatBytes, formatNumber, formatDuration } = load(path.join(root, 'src/lib/utils.ts'));
const claim = { claim_id: 'T1', statement: 'In 2026, the sample was 0.30000000004.', epistemic_type: 'fact', confidence_score: null, citations: [], calculation_ids: [], supporting_claims: [] };
const report = { executive_summary: 'Test only', claims: [claim], key_findings: [], inferences: [], recommendations: [], rejected_proposals: [] };
test('Missing verification is never rendered as verified', () => {
  const html = render(ExecutiveReportView, { report });
  assert.match(html, /Verification not reported/); assert.doesNotMatch(html, /References verified/);
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
