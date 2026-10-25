// Exercise API modules and compiled Vue setup code with controlled HTTP responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../platform/frontend/node_modules/typescript');
const vue = require('../../platform/frontend/node_modules/vue');
const { parse, compileScript } = require('../../platform/frontend/node_modules/@vue/compiler-sfc');
const root = path.resolve(__dirname, '../../platform/frontend/src');

function runtime(respond = () => { throw new TypeError('offline'); }) {
  const cache = new Map(), calls = [];
  function load(name) {
    if (name === 'vue') return { ...vue, onMounted() {} };
    if (name === 'vue-router') return { useRouter: () => ({ push: async () => {} }) };
    if (name.endsWith('.vue')) return {};
    const filename = path.join(root, name.replace(/^@\//, '') + '.ts');
    if (cache.has(filename)) return cache.get(filename).exports;
    return evaluate(fs.readFileSync(filename, 'utf8'), filename);
  }
  function evaluate(source, filename) {
    source = source.replaceAll('import.meta.env.VITE_API_BASE_URL', 'undefined');
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
    const module = { exports: {} };
    cache.set(filename, module);
    new Function('require', 'module', 'exports', 'window', 'fetch', code)(
      load, module, module.exports, { location: { origin: 'http://localhost' }, setTimeout },
      async (url, options) => {
        const call = { path: new URL(url).pathname, ...options, body: options.body ? JSON.parse(options.body) : undefined };
        calls.push(call);
        const body = await respond(call);
        return { ok: true, text: async () => JSON.stringify(body) };
      }
    );
    return module.exports;
  }
  function component(name, props = {}) {
    const filename = path.join(root, 'components', name + '.vue');
    const { descriptor } = parse(fs.readFileSync(filename, 'utf8'));
    const compiled = compileScript(descriptor, { id: name });
    return evaluate(compiled.content, filename).default.setup(props, { expose() {} });
  }
  return { load, component, calls };
}

(async () => {
  const real = runtime();
  const management = real.load('@/api/modules/management').managementApi;
  for (const call of [() => management.listCases(), () => management.listSuites(),
      () => management.listEnvironments(), () => management.listSchedules(),
      () => management.listRuns(), () => management.getEnvironmentDetail('missing'),
      () => management.createEnvironment({ name: 'real', baseUrl: 'http://localhost' })]) {
    await assert.rejects(call, /offline/);
  }
  const before = real.calls.length;
  await assert.rejects(real.load('@/api/modules/dashboard').dashboardApi.getOverview(), /offline/);
  assert.equal(real.calls.length, before + 1, 'dashboard must not hide failure with compatibility statistics');
  await assert.rejects(real.load('@/api/modules/execution').executionApi.getRunDetail('old'), /offline/);
  const status = real.load('@/utils/runStatus');
  for (const state of ['error', 'skipped', 'blocked', 'cancelled', 'timed_out', 'interrupted']) {
    assert.equal(status.normalizeRunStatus(state), state);
    assert.notEqual(status.getRunStatusMeta(state).tone, 'success');
  }
  const adapters = real.load('@/api/adapters/runs');
  const mock = adapters.normalizeRunSummary({ run_id: 'mock', status: 'succeeded', transport_mode: 'mock' }, 0);
  assert.notEqual(mock.status, 'success');
  const historical = adapters.normalizeRunSummary({ run_id: 'old', status: 'succeeded' }, 0);
  assert.equal(historical.transportMode, 'historical_unknown');
  assert.equal(historical.eligibleForRelease, false);

  const api = runtime(call => {
    if (call.path === '/api/v1/dashboard/overview') return { metrics: [], focus_items: [], recent_runs: [] };
    if (call.path.endsWith('/rerun')) return { run_id: 'new' };
    if (call.path.endsWith('/execute')) return { run_id: 'new', status: 'queued', transport_mode: 'live' };
    if (call.path.endsWith('/runs')) return { run_id: 'new' };
    if (call.path === '/api/v1/schedules') return { id: 'plan', parameters: {}, transport_mode: 'live' };
    return [];
  });
  assert.deepEqual((await api.load('@/api/modules/dashboard').dashboardApi.getOverview()).data,
    { metrics: [], focusItems: [], recentRuns: [] });
  await api.load('@/api/modules/execution').executionApi.rerun('live-old');
  assert.equal(api.calls.find(call => call.path.endsWith('/rerun')).body.transport_mode, 'live');

  const suiteRuntime = runtime(call => call.path.endsWith('/versions')
    ? [{ version: 1, change_note: 'published' }] : []);
  const suiteEditor = suiteRuntime.component('ScenarioAssetsPanel', { kind: 'suites' });
  const suiteAsset = vue.reactive({ id: 'persisted-suite', revision: 1, draft: {
    name: '真实套件', priority: 'P0', timeout_seconds: 30,
    scenarios: [{ scenario_id: 'published-scenario', version: 1 }],
  } });
  await suiteEditor.select(suiteAsset);
  assert.equal(suiteEditor.scenarioRefs.value[0].scenario_id, 'published-scenario');
  assert.equal(suiteEditor.chosenVersion.value, 1, 'saved suite selection must load published versions');
  suiteEditor.scenarioRefs.value[0].version = 2;
  assert.equal(suiteAsset.draft.scenarios[0].version, 1, 'editing a reference must not mutate the saved draft');

  const assets = api.component('ScenarioAssetsPanel', { kind: 'scenarios' });
  assets.selected.value = { id: 'owned', revision: 1, draft: {} };
  assets.chosenVersion.value = 1;
  await assets.plan();
  await assets.run();
  const schedules = api.component('SchedulePlansPanel');
  await schedules.save();
  const journey = api.component('JourneyCapabilitiesPanel');
  await journey.run({ id: 'owned', version: 1 });
  const requests = api.calls.filter(call => call.body && ('transport_mode' in call.body));
  assert.ok(requests.length >= 5);
  for (const call of requests) {
    assert.equal(call.body.transport_mode, 'live');
    assert.equal('mock_case_responses' in call.body, false);
  }

  const evaluation = api.component('EvaluationQualityPanel');
  const start = api.calls.length;
  await evaluation.load();
  evaluation.queryRun.value = 'history';
  await evaluation.report();
  evaluation.otherRun.value = 'other';
  await evaluation.compare();
  assert.equal(typeof evaluation.run, 'undefined');
  assert.ok(api.calls.slice(start).every(call => call.method === 'GET'));
  assert.ok(api.calls.some(call => call.path === '/api/v1/evaluation-runs/history'));
  const failed = real.component('EvaluationQualityPanel');
  failed.queryRun.value = 'history';
  await failed.report();
  assert.match(failed.error.value, /offline/);

  // Guard against reintroducing a product feature flag, fixture catalog or simulation input.
  function audit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) audit(filename);
      else if (/\.(ts|vue)$/.test(filename)) {
        const source = fs.readFileSync(filename, 'utf8');
        assert.doesNotMatch(source, /VITE_USE_MOCK|mock_case_responses|\/demo-suites|\/seed-local|local-replay@/, filename);
      }
    }
  }
  audit(root);
  console.log('Frontend reliability passed: explicit failures, empty data, historical labels, live requests and read-only evaluation history.');
})().catch(error => { console.error(error); process.exitCode = 1; });
