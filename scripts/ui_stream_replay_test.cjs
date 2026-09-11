// Reproduce a completed REST snapshot arriving before the second SSE replay batch.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const ts = require('../frontend/node_modules/typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/src/hooks/useInvestigationStream.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
let state, cleanup, poll, aborted = false;
const frame = (id, type, payload) => `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({ event_id: id, payload })}\n\n`;
const context = { exports: {}, console, process: { env: {} }, EventTarget, MessageEvent, AbortController, TextDecoder, window: { setTimeout }, setInterval: fn => { poll = fn; return 1; }, clearInterval: () => {},
  require: name => name === 'react' ? {
    useState: initial => { state = initial; return [state, update => { state = typeof update === 'function' ? update(state) : update; }]; },
    useEffect: effect => { cleanup = effect(); }, useCallback: callback => callback, useRef: value => ({ current: value }),
  } : { apiClient: { getAccessToken: () => 'test-in-memory', refresh: async () => true, get: async () => ({ status: 'completed', objective: 'Test fixture', steps: [] }) } },
  fetch: async (_url, options) => new Response(new ReadableStream({ start(controller) {
    options.signal.addEventListener('abort', () => { aborted = true; controller.error(new Error('Test connection closed')); });
    controller.enqueue(new TextEncoder().encode(frame('page-1', 'state.changed', { to: 'executing' })));
    setTimeout(() => { if (!aborted) controller.enqueue(new TextEncoder().encode(frame('page-2', 'investigation.completed', { status: 'completed' }))); }, 900);
  } }), { status: 200 }),
};
vm.runInNewContext(code, context); context.exports.useInvestigationStream('test');
setTimeout(() => void poll(), 150);
setTimeout(() => {
  cleanup();
  assert.equal(state.timeline.length, 2, 'A completed REST snapshot must not truncate persisted SSE replay');
  assert.equal(state.status, 'completed');
  console.log(JSON.stringify({ result: 'PASS', replay_batches: 2, completed_rest_before_second_batch: true, terminal_status_preserved: true }));
}, 1200);
