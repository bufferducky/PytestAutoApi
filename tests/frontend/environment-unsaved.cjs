// Exercise compiled Vue click handlers with an event argument, including both user entry points.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../platform/frontend');
const vue = require(root + '/node_modules/vue');
const ts = require(root + '/node_modules/typescript');
const { parse, compileScript, compileTemplate } = require(root + '/node_modules/@vue/compiler-sfc');
const source = fs.readFileSync(root + '/src/pages/EnvironmentsPage.vue', 'utf8');
const { descriptor } = parse(source);
const script = compileScript(descriptor, { id: 'environment-protection' });
function evaluate(source) {
  const module = { exports: {} };
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  new Function('require', 'module', 'exports', 'window', code)(load, module, module.exports, windowMock);
  return module.exports;
}
let shouldDiscard = false, confirmations = 0;
const windowMock = { confirm() { ++confirmations; return shouldDiscard; } };
const api = { deleteEnvironment: async () => ({ name: 'existing' }), listEnvironments: async () => [] };
function load(name) {
  if (name === 'vue') return { ...vue, resolveComponent: name => ({name}), onMounted() {}, onBeforeUnmount() {} };
  if (name === 'vue-router') return { onBeforeRouteLeave() {} };
  if (name === '@/api') return { managementApi: api };
  if (name === '@/utils/confirmation') return {confirmAction: async () => windowMock.confirm()};
  if (name === '@/utils/apiErrors') return { resolveApiErrorMessage: String };
  return {};
}
const setup = evaluate(script.content).default.setup({}, { expose() {} });
const template = compileTemplate({ source: descriptor.template.content, filename: 'EnvironmentsPage.vue', id: 'environment-protection', compilerOptions: { bindingMetadata: script.bindings } });
assert.deepEqual(template.errors, []);
const render = evaluate(template.code).render;
function buttons() {
  // Render only: child-panel slots are traversed explicitly without mounting unrelated components.
  const warn = console.warn; console.warn = () => {};
  try {
    const result = [];
    function visit(value) {
      if (Array.isArray(value)) { value.forEach(visit); return; }
      if (!value || typeof value !== 'object') return;
      if (value.type === 'button' || value.type?.name === 'el-button') result.push(value);
      if (Array.isArray(value.children)) visit(value.children);
      else if (value.children && typeof value.children === 'object') {
        if (value.type?.name !== 'el-table-column') for (const slot of Object.values(value.children)) if (typeof slot === 'function') visit(slot());
      }
    }
    visit(render({}, [], {}, vue.proxyRefs(setup), {}, {}));
    return result;
  } finally { console.warn = warn; }
}
function prepare() {
  setup.formMode.value = 'edit'; setup.selectedEnvironmentId.value = 'existing';
  setup.currentEnvironmentDetail.value = {id: 'existing', name: 'existing', status: 'draft', variables: {}};
  setup.formState.value.name = 'unsaved name'; setup.variablesText.value = '{"flag":false}';
}
(async () => {
  for (const label of ['新增环境', '取消编辑']) {
    prepare(); shouldDiscard = false; const before = confirmations;
    const button = buttons().find(item => { const children = typeof item.children?.default === 'function' ? item.children.default() : item.children; return (Array.isArray(children) ? children.map(child => child.children ?? child).join('') : String(children)).trim() === label; });
    assert(button, `Missing ${label} button`);
    await button.props.onClick(new Event('click'));
    assert.equal(confirmations, before + 1, `${label} must confirm even with an event argument`);
    assert.equal(setup.formState.value.name, 'unsaved name');
    assert.equal(setup.variablesText.value, '{"flag":false}');
    assert.equal(setup.selectedEnvironmentId.value, 'existing');
    shouldDiscard = true; await button.props.onClick(new Event('click'));
    assert.equal(setup.formMode.value, 'create'); assert.equal(setup.formState.value.name, '');
    assert.equal(setup.variablesText.value, '{}'); assert.equal(setup.dirty.value, false);
  }
  prepare(); shouldDiscard = false;
  await setup.startCreateMode(new Event('click'));
  assert.equal(setup.formState.value.name, 'unsaved name', 'handler itself must never interpret an event as force');
  shouldDiscard = true;
  for (const flag of ['saving', 'deleting']) {
    setup[flag].value = true; await setup.startCreateMode(new Event('click'));
    assert.equal(setup.formState.value.name, 'unsaved name'); setup[flag].value = false;
  }
  await setup.removeEnvironment();
  assert.equal(setup.formMode.value, 'create', 'confirmed successful deletion must reset without another discard prompt');
  console.log('PASS: both compiled environment click handlers protect edits; cancellation/acceptance, event argument, busy state and deletion reset');
})().catch(error => { console.error(error); process.exitCode = 1; });
