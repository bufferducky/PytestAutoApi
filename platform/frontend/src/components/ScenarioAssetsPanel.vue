<template>
  <section class="asset-panel" :data-testid="'asset-editor-' + kind">
    <h3>{{ kind === 'scenarios' ? '业务场景资产' : '固定版本套件' }}</h3>
    <p>草稿可编辑，发布版本不可变。预检或计划预览不会发送业务请求；真实运行需要已确认契约。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info">{{ message }}</p>
    <button type="button" @click="newDraft" :disabled="busy">新增</button>
    <button type="button" @click="load" :disabled="busy">刷新</button>
    <div class="asset-grid">
      <ul><li v-for="item in assets" :key="item.id"><button type="button" @click="select(item)">
        {{ item.draft.name }} · 草稿 r{{ item.revision }}
      </button></li><li v-if="!assets.length">暂无资产</li></ul>
      <form @submit.prevent="save">
        <label>名称 <input v-model="name" required /></label>
        <label>优先级 <select v-model="priority"><option>P0</option><option>P1</option><option>P2</option></select></label>
        <label>标签（逗号分隔）<input v-model="tags" placeholder="smoke,core" /></label>
        <template v-if="kind === 'scenarios'">
          <label>目标系统 <select v-model="targetRef" required>
            <option v-for="target in targets" :key="target.id" :value="target.id">{{ target.name }} · {{ target.id }}</option>
          </select></label>
          <label>身份引用（可选）<input v-model="identityRef" /></label>
          <label>项目绑定引用（需要上下文的目标必填）<input v-model="bindingRef" /></label>
          <label>模块 <input v-model="moduleName" /></label>
          <label>参数 schema（名称 → type/required）<textarea v-model="parametersSchema" rows="3" /></label>
          <label>默认公开参数 <textarea v-model="parameters" rows="3" /></label>
          <fieldset v-for="(step, index) in steps" :key="index">
            <legend>步骤 {{ index + 1 }}</legend>
            <label>稳定 ID <input v-model="step.step_id" required /></label>
            <label>步骤名称 <input v-model="step.name" required /></label>
            <label>步骤类型 <select v-model="step.type"><option value="http">HTTP</option><option value="wait_until">等待异步终态</option></select></label>
            <label>阶段 <select v-model="step.phase"><option>setup</option><option>action</option><option>verify</option><option>cleanup</option></select></label>
            <label>依赖（逗号分隔的前置步骤 ID）<input v-model="step.dependenciesText" /></label>
            <label>方法 <select v-model="step.method"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label>
            <label>URL <input v-model="step.url" placeholder="{{host}}/api/v1/..." required /></label>
            <label>业务用途 <select v-model="step.operation_kind"><option value="query">查询</option><option value="write">写入</option></select></label>
            <label><input type="checkbox" v-model="step.contract_confirmed" />请求契约已确认，可进入真实运行预检</label>
            <label><input type="checkbox" v-model="step.safe_to_replay" />此查询已确认允许401后重放一次</label>
            <label>请求体 JSON <textarea v-model="step.bodyText" rows="3" /></label>
            <AssertionEditor v-model="step.assertionsText" />
            <fieldset v-if="step.type === 'wait_until'">
              <legend>有限状态轮询</legend>
              <label><input v-model="step.waitConfirmed" type="checkbox" />状态/查询契约已确认</label>
              <label>状态字段 <input v-model="step.stateSelector" /></label>
              <label>状态映射 JSON <textarea v-model="step.stateMapText" rows="4" /></label>
              <label>间隔（秒）<input v-model.number="step.pollInterval" type="number" min="0" step="any" /></label>
              <label>总等待预算（秒）<input v-model.number="step.pollDeadline" type="number" min="0.001" step="any" /></label>
              <label>最大次数 <input v-model.number="step.pollAttempts" type="number" min="1" /></label>
              <label>安全查询网络重试（0—3）<input v-model.number="step.networkRetries" type="number" min="0" max="3" /></label>
              <details><summary>高级等待策略 JSON（退避/谓词/轨迹上限）</summary><textarea v-model="step.waitPolicyText" rows="6" /></details>
            </fieldset>
            <label>提取 JSON（写 outputs.本步骤ID.*）<textarea v-model="step.extractorsText" rows="3" /></label>
            <button type="button" @click="steps.splice(index, 1)">删除步骤</button>
          </fieldset>
          <button type="button" @click="addStep">添加 HTTP 步骤</button>
        </template>
        <template v-else>
          <label>总预算（秒）<input v-model.number="budget" type="number" min="1" max="86400" /></label>
          <fieldset v-for="(ref, index) in scenarioRefs" :key="index">
            <legend>场景引用 {{ index + 1 }}</legend>
            <label>场景 ID <input v-model="ref.scenario_id" required /></label>
            <label>固定发布版本 <input v-model.number="ref.version" type="number" min="1" required /></label>
            <button type="button" @click="scenarioRefs.splice(index, 1)">移除</button>
          </fieldset>
          <button type="button" @click="scenarioRefs.push({ scenario_id: '', version: 1 })">添加固定场景版本</button>
        </template>
        <details v-if="kind === 'scenarios'"><summary>迁移与扩展元数据</summary>
          <p>迁移缺口解决后再更新 migration_blockers；不能删除仍然未知的业务契约来绕过预检。</p>
          <textarea v-model="draftExtras" rows="8" aria-label="迁移与扩展元数据" />
        </details>
        <p>ID：{{ selected?.id || '保存时生成' }} · revision：{{ selected?.revision || 1 }}</p>
        <button :disabled="busy">保存草稿</button>
        <button type="button" v-if="selected" @click="preflight" :disabled="busy">发布预检</button>
        <label>发布说明 <input v-model="changeNote" /></label>
        <button type="button" v-if="selected" @click="publish" :disabled="busy || !changeNote">发布不可变版本</button>
        <button type="button" v-if="selected" @click="copyAsset" :disabled="busy">复制</button>
        <button type="button" v-if="selected" @click="archive" :disabled="busy">归档草稿</button>
      </form>
    </div>
    <pre v-if="checkResult">{{ checkResult }}</pre>
    <section v-if="selected">
      <h4>已发布版本</h4>
      <label>选择版本 <select v-model.number="chosenVersion"><option v-for="version in versions" :key="version.version" :value="version.version">v{{ version.version }} · {{ version.change_note }}</option></select></label>
      <label>本次公开参数 JSON <textarea v-model="runParameters" rows="3" /></label>
      <button type="button" :disabled="busy || !chosenVersion" @click="plan">计划预览</button>
      <label><input v-model="liveConfirmed" type="checkbox" />已核对计划与测试数据/写入范围</label>
      <button type="button" :disabled="busy || !chosenVersion || !liveConfirmed" @click="run">提交运行</button>
      <button type="button" :disabled="busy || !chosenVersion" @click="exportAsset">查看脱敏导出</button>
    </section>
    <details v-if="kind === 'scenarios'"><summary>迁移已有资产（只创建草稿，不发送请求）</summary>
      <label>旧 YAML 路径 <input v-model="importSource" /></label>
      <label>导入类型 <select v-model="importKind"><option value="legacy">旧 YAML</option><option value="standard">标准发布 JSON</option></select></label>
      <label v-if="importKind === 'standard'">发布 JSON <textarea v-model="importText" rows="10" /></label>
      <button type="button" :disabled="busy" @click="importAsset">导入并显示迁移报告</button>
    </details>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import AssertionEditor from '@/components/AssertionEditor.vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

interface Step {
  step_id: string; name: string; type: string; phase: string;
  depends_on: string[]; operation_kind: string; contract_confirmed: boolean; safe_to_replay: boolean;
  request: { method: string; url: string; body: unknown; [key: string]: unknown };
  assertions: unknown[]; extractors: unknown[]; wait_policy?: Record<string, unknown> | null; [key: string]: unknown;
}
interface EditorStep extends Omit<Step, 'request'> {
  step_id: string; name: string; type: string; phase: string;
  operation_kind: string; contract_confirmed: boolean; safe_to_replay: boolean;
  request?: Step['request']; method: string; url: string; dependenciesText: string;
  bodyText: string; assertionsText: string; extractorsText: string;
  waitConfirmed: boolean; stateSelector: string; stateMapText: string; pollInterval: number;
  pollDeadline: number; pollAttempts: number; networkRetries: number; waitPolicyText: string;
}
interface Data {
  name: string; priority: string; tags?: string[]; target_ref?: string;
  identity_ref?: string | null; identity_binding_ref?: string | null; module?: string;
  parameters_schema?: Record<string, unknown>; parameters?: Record<string, unknown>;
  steps?: Step[]; scenarios?: {scenario_id: string; version: number}[]; timeout_seconds?: number;
  [key: string]: unknown;
}
interface Asset { id: string; revision: number; draft: Data }
interface Version { version: number; change_note: string }
const props = defineProps<{ kind: 'scenarios' | 'suites' }>();
const router = useRouter();

const assets = ref<Asset[]>([]), selected = ref<Asset | null>(null), targets = ref<{id: string; name: string}[]>([]);
const busy = ref(false), error = ref(''), message = ref(''), checkResult = ref('');
const name = ref(''), priority = ref('P1'), tags = ref('core'), moduleName = ref('未分类');
const targetRef = ref(''), identityRef = ref(''), bindingRef = ref('');
const draftExtras = ref('{}');
const parametersSchema = ref('{}'), parameters = ref('{}'), steps = ref<EditorStep[]>([]);
const scenarioRefs = ref<{scenario_id: string; version: number}[]>([]), budget = ref(300);
const changeNote = ref(''), versions = ref<Version[]>([]), chosenVersion = ref(0);
const runParameters = ref('{}'), liveConfirmed = ref(false);
const importSource = ref(''), importKind = ref('legacy'), importText = ref('{}');
const collection = () => props.kind === 'suites' ? '/suite-assets' : '/scenarios';
const url = () => `/${props.kind}/${selected.value?.id}`;
const split = (value: string) => value.split(',').map(v => v.trim()).filter(Boolean);
const parse = (value: string) => JSON.parse(value);
function newDraft() {
  selected.value = null; name.value = ''; priority.value = 'P1'; tags.value = 'core';
  steps.value = []; scenarioRefs.value = []; versions.value = []; chosenVersion.value = 0;
  parametersSchema.value = parameters.value = draftExtras.value = '{}'; checkResult.value = ''; liveConfirmed.value = false;
}
function addStep() {
  steps.value.push({ step_id: `step_${steps.value.length + 1}`, name: '新步骤', phase: 'verify', type: 'http',
    method: 'GET', url: '{{host}}/api/v1/...', operation_kind: 'query', contract_confirmed: false,
    dependenciesText: '', safe_to_replay: false, bodyText: 'null',
    assertionsText: '[{"name":"business-code","selector":"code","expected":200}]', extractorsText: '[]',
    waitConfirmed:false, stateSelector:'data.state', stateMapText:'{"pending":"pending","running":"running","success":"succeeded","failed":"failed"}',
    pollInterval:2, pollDeadline:60, pollAttempts:30, networkRetries:0, waitPolicyText:'{}' });
}
async function select(asset: Asset) {
  selected.value = asset; const d = asset.draft;
  name.value = d.name; priority.value = d.priority; tags.value = (d.tags || []).join(',');
  targetRef.value = d.target_ref || ''; identityRef.value = d.identity_ref || ''; bindingRef.value = d.identity_binding_ref || '';
  moduleName.value = d.module || ''; parametersSchema.value = JSON.stringify(d.parameters_schema || {}, null, 2);
  parameters.value = JSON.stringify(d.parameters || {}, null, 2);
  draftExtras.value = JSON.stringify({ source: d.source || {}, migration_warnings: d.migration_warnings || [], migration_blockers: d.migration_blockers || [], fixtures: d.fixtures || [] }, null, 2);
  steps.value = (d.steps || []).map((s: Step) => ({...s, dependenciesText: s.depends_on.join(','),
    method: s.request.method, url: s.request.url, bodyText: JSON.stringify(s.request.body, null, 2),
    assertionsText: JSON.stringify(s.assertions, null, 2), extractorsText: JSON.stringify(s.extractors, null, 2),
    waitConfirmed:s.wait_policy?.contract_confirmed === true, stateSelector:String(s.wait_policy?.state_selector || 'data.state'),
    stateMapText:JSON.stringify(s.wait_policy?.state_map || {},null,2), pollInterval:Number(s.wait_policy?.interval_seconds ?? 2),
    pollDeadline:Number(s.wait_policy?.deadline_seconds ?? 60),pollAttempts:Number(s.wait_policy?.max_attempts ?? 30),
    networkRetries:Number(s.wait_policy?.network_retries ?? 0),waitPolicyText:JSON.stringify(s.wait_policy || {},null,2) }));
  // API 列表进入 ref 后是 Vue Proxy，按引用契约复制字段，避免 structuredClone 抛错。
  scenarioRefs.value = (d.scenarios || []).map(ref => ({ scenario_id: ref.scenario_id, version: ref.version }));
  budget.value = d.timeout_seconds || 300;
  versions.value = await apiClient.get<Version[]>(url() + '/versions'); chosenVersion.value = versions.value[0]?.version || 0;
  checkResult.value = ''; liveConfirmed.value = false;
}
async function load() {
  
  busy.value = true; error.value = '';
  try { assets.value = await apiClient.get<Asset[]>(collection()); targets.value = await apiClient.get<{id: string; name: string}[]>('/targets'); }
  catch (cause) { error.value = resolveApiErrorMessage(cause, '资产读取失败'); }
  finally { busy.value = false; }
}
function draftData(): Data {
  const base = { ...selected.value?.draft, ...(props.kind === 'scenarios' ? parse(draftExtras.value) : {}), name: name.value, priority: priority.value, tags: split(tags.value) };
  if (props.kind === 'suites') return {...base, scenarios: scenarioRefs.value, timeout_seconds: budget.value};
  return { ...base, target_ref: targetRef.value, identity_ref: identityRef.value || null,
    identity_binding_ref: bindingRef.value || null, module: moduleName.value,
    parameters_schema: parse(parametersSchema.value), parameters: parse(parameters.value),
    steps: steps.value.map(s => {
      const { dependenciesText, method, url, bodyText, assertionsText, extractorsText,
        waitConfirmed,stateSelector,stateMapText,pollInterval,pollDeadline,pollAttempts,networkRetries,waitPolicyText,...original } = s;
      return { ...original, depends_on: split(dependenciesText), request: { ...s.request, method, url, body: parse(bodyText) },
        assertions: parse(assertionsText), extractors: parse(extractorsText),
        wait_policy:s.type === 'wait_until' ? {...parse(waitPolicyText),contract_confirmed:waitConfirmed,state_selector:stateSelector,
          state_map:parse(stateMapText),interval_seconds:pollInterval,deadline_seconds:pollDeadline,max_attempts:pollAttempts,network_retries:networkRetries} : null };
    }) };
}
async function action(operation: () => Promise<void>) {
  busy.value = true; error.value = ''; message.value = '';
  try { await operation(); } catch (cause) { error.value = resolveApiErrorMessage(cause, '操作失败'); }
  finally { busy.value = false; }
}
async function save() { await action(async () => {
  const asset = selected.value ? await apiClient.patch<Asset>(url() + '/draft', { expected_revision: selected.value.revision, draft: draftData() })
    : await apiClient.post<Asset>(collection(), draftData());
  await load(); await select(asset); message.value = '草稿已持久保存；尚未发布。';
}); }
async function preflight() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.post(url() + '/preflight'), null, 2); }); }
async function publish() { await action(async () => {
  await apiClient.post(url() + '/publish', { expected_revision: selected.value?.revision, change_note: changeNote.value });
  if (selected.value) await select(selected.value); message.value = '发布版本已冻结，编辑草稿不会改写它。';
}); }
async function copyAsset() { await action(async () => { const copy = await apiClient.post<Asset>(url() + '/copy'); await load(); await select(copy); }); }
async function archive() { await action(async () => { await apiClient.post(`${url()}/archive?revision=${selected.value?.revision}`); newDraft(); await load(); }); }
const runData = () => ({ transport_mode: 'live', parameters: parse(runParameters.value) });
async function plan() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.post(`${url()}/versions/${chosenVersion.value}/plan`, runData()), null, 2); }); }
async function run() { await action(async () => { const result = await apiClient.post<{run_id: string}>(`${url()}/versions/${chosenVersion.value}/runs`, runData()); await router.push({name: 'runs', query: {runId: result.run_id}}); }); }
async function exportAsset() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.get(`${url()}/versions/${chosenVersion.value}/export`), null, 2); }); }
async function importAsset() { await action(async () => {
  const body = importKind.value === 'standard' ? parse(importText.value)
    : { target_ref: targetRef.value, path: importSource.value };
  const result = await apiClient.post<Asset | {asset: Asset; report: unknown}>(`/imports/${importKind.value}`, body);
  await load(); await select('asset' in result ? result.asset : result);
  checkResult.value = JSON.stringify('asset' in result ? result.report : {}, null, 2);
}); }
onMounted(() => { void load(); });
</script>

<style scoped>
.asset-panel { padding: 1.5rem; border-radius: 1rem; background: var(--color-surface, white); }
.asset-grid { display: grid; grid-template-columns: minmax(10rem,1fr) minmax(16rem,3fr); gap: 1rem; }
form, fieldset { display: grid; min-width: 0; gap: .5rem; } label { display: grid; min-width: 0; gap: .25rem; }
input, select, textarea { max-width: 100%; padding: .45rem; } fieldset { margin-block: .5rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 35rem; overflow: auto; }
@media(max-width:700px) { .asset-grid { grid-template-columns: minmax(0, 1fr); } .asset-grid ul { padding-left: 1rem; } .asset-grid button { max-width: 100%; overflow-wrap: anywhere; } }
</style>
