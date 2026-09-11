// Execute the actual hook with controlled React scheduling and transport inputs.
// This checks state merging, not browser DOM rendering or an HTTPS deployment.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const ts = require('../frontend/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../frontend/src/hooks/useInvestigationStream.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
let state, cleanup, connections = 0;
const headers = [];
const step = { id: 'step-1', step_number: 1, created_at: '2026-09-08T00:00:00Z' };
const frames = [
  ['state.changed', { event_id: 'event-1', payload: { to: 'executing' } }],
  ['tool_completed', { event_id: 'event-2', step_id: 'step-1', step_number: 1, tool: 'closure', created_at: step.created_at }],
  ['evidence_found', { event_id: 'event-3', citation_id: 'citation-1', source_name: 'test.txt', quote: 'test only', modality: 'text' }],
].map(([type, data], i) => `id: event-${i + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`).join('');
const context = {
  exports: {}, console, process: { env: {} }, EventTarget, MessageEvent, AbortController, TextDecoder,
  window: { setTimeout }, setInterval: () => 1, clearInterval: () => {},
  require: (name) => {
    if (name === 'react') return {
      useState: (initial) => { state = initial; return [state, (change) => { state = typeof change === 'function' ? change(state) : change; }]; },
      useEffect: (effect) => { cleanup = effect(); }, useCallback: (callback) => callback, useRef: (value) => ({ current: value }),
    };
    if (name === '@/lib/api-client') return { apiClient: {
      getAccessToken: () => 'test-access-in-memory', refresh: async () => true,
      get: async () => ({ status: 'running', steps: [step] }),
    } };
    throw new Error(`Unexpected dependency: ${name}`);
  },
  fetch: async (_url, options) => {
    connections += 1; headers.push(options.headers);
    return new Response(frames, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  },
};
vm.runInNewContext(compiled, context);
context.exports.useInvestigationStream('closure-test');
setTimeout(() => {
  cleanup();
  assert.ok(connections >= 2);
  assert.equal(headers[1]['Last-Event-ID'], 'event-3');
  assert.equal(state.timeline.length, 3);
  assert.equal(state.steps.length, 1);
  assert.equal(state.evidenceDiscovered.length, 1);
  console.log(JSON.stringify({ result: 'PASS', connections, rest_plus_replay_plus_reconnect: true, timeline: 3, steps: 1, evidence: 1, actual_hook_executed: true, browser_dom: 'NOT_TESTED' }));
}, 800);
