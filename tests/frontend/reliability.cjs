// Exercise API modules and compiled Vue setup code with controlled HTTP responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../platform/frontend/node_modules/typescript');
const vue = require('../../platform/frontend/node_modules/vue');
const { parse, compileScript } = require('../../platform/frontend/node_modules/@vue/compiler-sfc');
const root = path.resolve(__dirname, '../../platform/frontend/src');

function runtime(respond = () => { throw new TypeError('offline'); }, confirm = () => true) {
  const cache = new Map(), calls = [], emissions = [], mounted = [], unmounted = [], listeners = new Map();
  const document = { hidden: false, addEventListener: (event, callback) => listeners.set(event, callback), removeEventListener: (event, callback) => { if (listeners.get(event) === callback) listeners.delete(event); } };
  function load(name) {
    if (name === 'vue') return { ...vue, onMounted(callback) { mounted.push(callback); }, onBeforeUnmount(callback) { unmounted.push(callback); } };
    if (name === 'vue-router') return { useRouter: () => ({ push: async () => {} }), useRoute: () => ({ query: {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} };
    if (name === '@/utils/confirmation') return { confirmAction: async () => await confirm() };
    if (name.endsWith('.vue')) return {};
    const base = path.join(root, name.replace(/^@\//, ''));
    const filename = fs.existsSync(base + '.ts') ? base + '.ts' : path.join(base, 'index.ts');
    if (cache.has(filename)) return cache.get(filename).exports;
    return evaluate(fs.readFileSync(filename, 'utf8'), filename);
  }
  function evaluate(source, filename) {
    source = source.replaceAll('import.meta.env.VITE_API_BASE_URL', 'undefined');
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
    const module = { exports: {} };
    cache.set(filename, module);
    new Function('require', 'module', 'exports', 'window', 'fetch', 'document', code)(
      load, module, module.exports, { location: { origin: 'http://localhost' }, setTimeout, confirm },
      async (url, options) => {
        const call = { path: new URL(url).pathname, ...options, body: options.body ? JSON.parse(options.body) : undefined };
        calls.push(call);
        const body = await respond(call);
        return { ok: true, text: async () => JSON.stringify(body) };
      }, document
    );
    return module.exports;
  }
  function component(name, props = {}) {
    const filename = path.join(root, 'components', name + '.vue');
    const { descriptor } = parse(fs.readFileSync(filename, 'utf8'));
    const compiled = compileScript(descriptor, { id: name });
    return evaluate(compiled.content, filename).default.setup(props, { expose() {}, emit: (event, payload) => emissions.push({ component: name, event, payload }) });
  }
  return { load, component, calls, emissions, document, listeners, mount: () => mounted.forEach(callback => callback()), unmount: () => unmounted.forEach(callback => callback()) };
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
  const namedRun = adapters.normalizeRunSummary({
    run_id: 'opaque-run-id', run_number: '9007199254740993',
    suite_id: 'opaque-asset-id', name: '言迹接诊筛选 · 只读验收',
    status: 'succeeded', transport_mode: 'live',
  }, 0);
  assert.equal(namedRun.name, '言迹接诊筛选 · 只读验收');
  assert.equal(namedRun.runNumber, '9007199254740993', 'BIGINT display numbers must not lose precision');
  assert.equal(namedRun.id, 'opaque-run-id', 'navigation still uses the original association ID');
  assert.equal(adapters.normalizeRunSummary({run_id:'old', suite_id:'opaque-asset-id'}, 0).name,
    '未命名运行', 'missing historical names must not turn opaque asset IDs into titles');

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
  assert.equal(suiteEditor.settingsOpen.value, false, 'saved assets start with settings collapsed');
  assert.ok(suiteRuntime.emissions.some(item => item.event === 'selected' && item.payload === 'persisted-suite'));
  suiteEditor.newDraft();
  assert.equal(suiteEditor.settingsOpen.value, true, 'new drafts show required settings');
  await suiteEditor.select(suiteAsset);
  assert.equal(suiteEditor.chosenVersion.value, 1, 'saved suite selection must load published versions');
  suiteEditor.scenarioRefs.value[0].version = 2;
  assert.equal(suiteAsset.draft.scenarios[0].version, 1, 'editing a reference must not mutate the saved draft');

  const refsRuntime = runtime(call => call.path.endsWith('/versions') ? [{version:1,change_note:'first'},{version:3,change_note:'latest'}] : []);
  const refsEditor = refsRuntime.component('ScenarioAssetsPanel', {kind:'suites'});
  refsEditor.scenarioRefs.value = [{scenario_id:'scenario-a',version:1}];
  await refsEditor.changeScenarioReference(refsEditor.scenarioRefs.value[0]);
  assert.equal(refsEditor.scenarioRefs.value[0].version, 3);
  await refsEditor.loadReferenceVersions('scenario-a');
  assert.equal(refsRuntime.calls.length, 1, 'published version reads are cached by scenario');
  await refsEditor.select({id:'old-suite',revision:1,draft:{name:'old',priority:'P1',scenarios:[{scenario_id:'scenario-a',version:9}]}});
  assert.equal(refsEditor.scenarioRefs.value[0].version, 9, 'old references stay unchanged during verification');
  await refsEditor.save();
  assert.match(refsEditor.error.value, /未发布/);
  assert.equal(refsRuntime.calls.some(call => call.method === 'PATCH'), false);
  const saveRuntime = runtime(call => call.method === 'POST' && call.path === '/api/v1/scenarios' ? {id:'saved-id',revision:1,draft:{schema_version:'1.0',...call.body,timeout_seconds:300,source:{},migration_warnings:[],migration_blockers:[],fixtures:[]}} : []);
  const savedEditor = saveRuntime.component('ScenarioAssetsPanel', {kind:'scenarios'});
  savedEditor.name.value = '保存事件'; savedEditor.targetRef.value = 'target';
  await savedEditor.save();
  assert.deepEqual(saveRuntime.emissions.find(item => item.event === 'saved').payload, {id:'saved-id'});
  assert.equal(savedEditor.dirty.value, false, 'server-added defaults must not dirty a freshly saved draft');
  await savedEditor.publish();
  assert.ok(saveRuntime.calls.some(call => call.path.endsWith('/publish')), 'freshly saved default-enriched draft can publish');
  let releaseSave;
  const inFlightRuntime = runtime(call => call.method === 'POST' && call.path === '/api/v1/scenarios'
    ? new Promise(resolve => { releaseSave = () => resolve({ id:'in-flight', revision:2, draft:{schema_version:'1.0',...call.body,timeout_seconds:300} }); }) : []);
  const inFlight = inFlightRuntime.component('ScenarioAssetsPanel', {kind:'scenarios'});
  inFlight.name.value = 'submitted'; inFlight.targetRef.value = 'target';
  const saving = inFlight.save();
  inFlight.name.value = 'typed while saving';
  releaseSave(); await saving;
  assert.equal(inFlight.name.value, 'typed while saving');
  assert.equal(inFlight.selected.value.revision, 2);
  assert.equal(inFlight.dirty.value, true, 'save baseline excludes edits made after submission');
  inFlight.name.value = 'submitted'; inFlight.targetRef.value = 'target';
  assert.equal(inFlight.dirty.value, false);
  let releasePublish;
  const publishRuntime = runtime(call => call.path.endsWith('/publish') ? new Promise(resolve => { releasePublish = resolve; }) : []);
  const publishing = publishRuntime.component('ScenarioAssetsPanel', {kind:'scenarios'});
  await publishing.select({id:'published',revision:1,draft:{name:'before',priority:'P1',tags:[],steps:[]}});
  const publication = publishing.publish();
  publishing.name.value = 'typed while publishing';
  releasePublish({}); await publication;
  assert.equal(publishing.name.value, 'typed while publishing');
  assert.equal(publishing.dirty.value, true, 'publish refresh must not reload the editing buffer');
  const refuseRuntime = runtime(() => { throw new Error('must not send'); }, () => false);
  const refusing = refuseRuntime.component('ScenarioAssetsPanel', {kind:'scenarios'});
  refusing.name.value = 'unsaved'; refusing.selected.value = {id:'owned',revision:1,draft:{}}; refusing.chosenVersion.value = 1;
  await refusing.run();
  assert.equal(refuseRuntime.calls.length, 0, 'declining draft discard must prevent run submission');
  assert.equal(refusing.name.value, 'unsaved');
  assert.equal(refusing.formalNavigation.value, false);
  const settingsDetails = { tagName:'DETAILS', open:false, parentElement:null, classList:{contains:name => name === 'scenario-settings'} };
  savedEditor.revealInvalid({ target: { parentElement:settingsDetails, closest:() => null } });
  assert.equal(settingsDetails.open, true, 'invalid controls synchronously reveal their details');
  assert.equal(savedEditor.settingsOpen.value, true);
  const assets = api.component('ScenarioAssetsPanel', { kind: 'scenarios' });
  assets.selected.value = { id: 'owned', revision: 1, draft: {} };
  assets.chosenVersion.value = 1;
  assets.runEnvironment.value = 'test-environment';
  assets.build.value = 'test-build-v1';
  await assets.plan();
  await assets.run();
  const assetRun = api.calls.find(call => call.path === '/api/v1/scenarios/owned/versions/1/runs');
  assert.equal(assetRun.body.environment_id, 'test-environment');
  assert.equal(assetRun.body.build, 'test-build-v1');
  assets.newDraft();
  assets.addStep();
  const step = assets.steps.value[0];
  step.headerRows = [{key: 'X-Test', value: '{{params.tag}}'}];
  step.queryRows = [{key: 'page', value: '2'}];
  step.bodyType = 'raw'; step.bodyText = 'literal content';
  const edited = assets.draftData().steps[0].request;
  assert.deepEqual(edited.headers, {'X-Test': '{{params.tag}}'});
  assert.deepEqual(edited.query, {page: '2'});
  assert.equal(edited.body_type, 'raw'); assert.equal(edited.body, 'literal content');
  assert.equal(assets.runParameters.value, '{}'); assert.equal(assets.build.value, '');
  assert.equal(assets.targetRef.value, ''); assert.equal(assets.dirty.value, true);
  const callsBeforeDirty = api.calls.length;
  await assets.preflight();
  assert.match(assets.error.value, /先保存/); assert.equal(api.calls.length, callsBeforeDirty);
  // Step operations preserve IDs/data and never recycle an existing ID after deletion.
  assets.copyStep(0);
  assert.notEqual(assets.steps.value[0].step_id, assets.steps.value[1].step_id);
  assert.equal(assets.steps.value[1].bodyText, 'literal content');
  const copiedId = assets.steps.value[1].step_id;
  assets.moveStep(1, -1);
  assert.equal(assets.steps.value[0].step_id, copiedId);
  assets.steps.value.splice(1, 1); assets.addStep();
  assert.equal(new Set(assets.steps.value.map(step => step.step_id)).size, 2);
  const debugValidation = api.load('@/utils/debugInputs');
  const dependent = { step_id: 'next', depends_on: ['create'], request: { url: '{{outputs.create.id}}' }, extractors: [{ target: 'outputs.next.id' }] };
  assert.throws(() => debugValidation.debugInputs(dependent, '{}'), /缺少前置输入/);
  assert.throws(() => debugValidation.debugInputs(dependent, '{"create":{}}'), /create.id/);
  assert.deepEqual(debugValidation.debugInputs(dependent, '{"create":{"id":"public-id"}}'), { create: { id: 'public-id' } });
  const extractorProps = { modelValue: '[{"name":"id","selector":"data.id","target":"outputs.a.id","extras":{"custom":true}}]', stepId: 'a' };
  const extractor = api.component('ExtractorEditor', extractorProps);
  assert.equal(extractor.rows.value[0].extras.custom, true);
  extractorProps.modelValue = 'broken';
  extractor.add();
  assert.match(extractor.error.value, /JSON|Unexpected/);
  const debugRuntime = runtime(call => call.path.endsWith('/debug') ? { run_id: 'debug-one' } : { status: 'succeeded', steps: [] });
  let liveDraft = { name: 'unsaved', priority: 'P1', steps: [{ step_id: 'one', depends_on: [], request: { method: 'GET', url: 'http://localhost/old' }, operation_kind: 'query' }] };
  const debugPanel = debugRuntime.component('ScenarioDebugPanel', { getDraft: () => liveDraft, environments: [] });
  await debugPanel.start();
  const debugRequest = debugRuntime.calls.find(call => call.path.endsWith('/debug'));
  assert.equal(debugRequest.body.draft.name, 'unsaved');
  assert.equal(debugRequest.body.live_confirmed, true);
  liveDraft.steps[0].request.url = 'http://localhost/edited';
  assert.equal(debugRequest.body.draft.steps[0].request.url, 'http://localhost/old');
  assert.equal(debugRuntime.calls.filter(call => call.method !== 'GET').length, 1, 'debug must not save/publish drafts');
  const missingDebug = debugRuntime.component('ScenarioDebugPanel', { getDraft: () => ({ steps: [dependent] }), stepId: 'next', environments: [] });
  const debugCalls = debugRuntime.calls.length;
  await missingDebug.start();
  assert.match(missingDebug.error.value, /缺少前置输入/);
  assert.equal(debugRuntime.calls.length, debugCalls);
  const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
  // 异步范围确认的快照在弹窗打开前冻结，期间的输入不能改变确认后发送的请求。
  const permission = deferred();
  const confirmationRuntime = runtime(call => call.path.endsWith('/debug') ? {run_id:'confirmed'} : {status:'succeeded',steps:[]}, () => permission.promise);
  const frozenDraft={name:'confirmed-buffer',steps:[{step_id:'one',depends_on:[],request:{method:'GET',url:'http://localhost/confirmed'},operation_kind:'query'}]};
  const confirmationPanel=confirmationRuntime.component('ScenarioDebugPanel',{getDraft:()=>frozenDraft,environments:[]});
  confirmationPanel.environment.value='confirmed-environment'; confirmationPanel.build.value='confirmed-build';
  const awaitingPermission=confirmationPanel.start();
  frozenDraft.name='changed-during-confirmation'; confirmationPanel.environment.value='new-environment'; confirmationPanel.build.value='new-build';
  permission.resolve(true); await awaitingPermission;
  const confirmedBody=confirmationRuntime.calls.find(call=>call.path.endsWith('/debug')).body;
  assert.equal(confirmedBody.draft.name,'confirmed-buffer');
  assert.equal(confirmedBody.environment_id,'confirmed-environment');
  assert.equal(confirmedBody.build,'confirmed-build');
  const cancelledPermission=deferred();
  const cancelledRuntime=runtime(()=>{throw new Error('cancelled confirmation must not send');},()=>cancelledPermission.promise);
  const cancelledPanel=cancelledRuntime.component('ScenarioDebugPanel',{getDraft:()=>frozenDraft,environments:[]});
  const awaitingCancel=cancelledPanel.start();cancelledPermission.resolve(false);await awaitingCancel;
  assert.equal(cancelledRuntime.calls.length,0);
  const initialPost = deferred(), oldRead = deferred();
  let readCount = 0;
  const racingRuntime = runtime(call => {
    if (call.path.endsWith('/debug')) return initialPost.promise;
    if (++readCount === 1) return { status: 'running', results: [{ steps: [{step_id:'one',status:'failed',assertions:[{name:'id',expected:1,actual:2,status:'failed'}]}] }] };
    return oldRead.promise;
  });
  const debugProps = vue.reactive({ getDraft: () => liveDraft, environments: [], assetId: 'asset-a' });
  const racing = racingRuntime.component('ScenarioDebugPanel', debugProps);
  racingRuntime.mount();
  const submitting = racing.start();
  await racing.start();
  await Promise.resolve();
  assert.equal(racingRuntime.calls.length, 1, 'duplicate debug submissions are blocked');
  initialPost.resolve({run_id:'running-debug'}); await submitting;
  assert.equal(racing.failure.value.step_id, 'one', 'nested case steps yield structured failure evidence');
  assert.equal(racing.statusLabel('failed'), '失败');
  racingRuntime.document.hidden = true;
  racingRuntime.listeners.get('visibilitychange')();
  const hiddenCalls = racingRuntime.calls.length;
  await racing.refresh();
  assert.equal(racingRuntime.calls.length, hiddenCalls, 'hidden pages must not poll');
  racingRuntime.document.hidden = false;
  racingRuntime.listeners.get('visibilitychange')();
  await racing.refresh();
  assert.equal(racingRuntime.calls.length, hiddenCalls + 1, 'resume refresh is singular even with another refresh click');
  debugProps.assetId = 'asset-b'; await vue.nextTick();
  assert.equal(racing.runId.value, '', 'asset switches clear the old run association');
  oldRead.resolve({status:'succeeded',results:[]});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(racing.result.value, null, 'old asset response cannot repopulate the new scope');
  const latePost = deferred();
  const closingRuntime = runtime(() => latePost.promise);
  const closing = closingRuntime.component('ScenarioDebugPanel', { getDraft: () => liveDraft, environments: [] });
  closingRuntime.mount();
  const pendingSubmit = closing.start();
  await new Promise(resolve => setImmediate(resolve));
  closingRuntime.unmount();
  latePost.reject(new Error('late failure')); await pendingSubmit;
  assert.equal(closing.error.value, '', 'unmounted submissions cannot write errors');
  assert.equal(closing.runId.value, '');
  assert.equal(closingRuntime.listeners.size, 0, 'visibility listener is removed on unmount');
  racingRuntime.unmount();
  const schedules = api.component('SchedulePlansPanel');
  schedules.suiteId.value = 'suite'; schedules.suiteVersion.value = 1; schedules.environment.value = 'test';
  schedules.versions.value = [{version: 1, change_note: 'published'}];
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

  const receptionRuntime = runtime(call => {
    if (call.path === '/api/v1/business-datasources') return [{ id: 'yanji-test', schema: 'yanji', configuration: 'passed' }];
    if (call.path.endsWith('/preflight')) return { configuration: 'passed', connection: 'not_verified', permission: 'not_verified', errors: [] };
    if (call.path === '/api/v1/imports/yanji-reception') return { assets: [{ id: 'reception' }], note: 'draft only' };
    return [];
  });
  const receptionEditor = receptionRuntime.component('ScenarioAssetsPanel', { kind: 'scenarios' });
  receptionEditor.targetRef.value = 'target'; receptionEditor.identityRef.value = 'identity';
  receptionEditor.bindingRef.value = 'binding'; receptionEditor.expectedUserId.value = 'user';
  await receptionEditor.loadDatasources();
  receptionEditor.datasourceRef.value = 'yanji-test';
  await vue.nextTick();
  await receptionEditor.preflightDatasource(false);
  assert.equal(receptionEditor.datasourcePreflight.value.connection, 'not_verified', 'configuration checks cannot claim a live DB connection');
  assert.equal(receptionRuntime.calls.find(call => call.path.endsWith('/preflight')).body.execute_query, false);
  receptionEditor.bindingRef.value = 'another-binding';
  await vue.nextTick();
  assert.equal(receptionEditor.datasourcePreflight.value, null, 'changing the binding invalidates old preflight evidence');
  receptionEditor.name.value = 'unsaved editor content';
  await receptionEditor.importReceptions();
  assert.equal(receptionEditor.name.value, 'unsaved editor content', 'import must preserve the current edit buffer');
  const receptionImport = receptionRuntime.calls.find(call => call.path === '/api/v1/imports/yanji-reception');
  assert.equal(receptionImport.body.datasource_ref, 'yanji-test');
  assert.equal(receptionImport.body.binding_ref, 'another-binding');
  assert.equal(receptionRuntime.calls.some(call => /\/publish$|\/runs$/.test(call.path)), false, 'import never publishes or runs');

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
