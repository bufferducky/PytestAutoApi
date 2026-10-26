<template>
  <section class="plans">
    <header class="section-heading"><div><h3>回归计划</h3><p>固定套件版本，配置触发时间。新计划默认暂停。</p></div><div class="toolbar"><button type="button" @click="load" :disabled="busy">刷新</button><button class="action-button" type="button" @click="reset" :disabled="busy">新计划</button></div></header>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="dirty" role="status">有未保存修改</p>
    <p v-if="error" class="state-banner state-banner--error" role="alert">{{ error }}</p>
    <form @submit.prevent="save"><fieldset :disabled="busy" class="plan-fields">
      <label>名称<input v-model="name" required /></label>
      <label>发布套件<select aria-label="发布套件" v-model="suiteId" required @change="loadVersions()"><option value="">选择套件</option><option v-if="suiteId && !suites.some(item => item.id === suiteId)" :value="suiteId">当前套件（目录不可用）：{{ suiteId }}</option><option v-for="suite in suites" :key="suite.id" :value="suite.id">{{ suite.draft.name }} · {{ suite.id }}</option></select></label>
      <label>固定发布版本<select aria-label="固定发布版本" v-model.number="suiteVersion" required :disabled="versionsLoading"><option :value="0">选择已发布版本</option><option v-if="suiteVersion && !versions.some(item => item.version === suiteVersion)" :value="suiteVersion">当前固定版本 v{{ suiteVersion }}（待核验）</option><option v-for="version in versions" :key="version.version" :value="version.version">v{{ version.version }} · {{ version.change_note || '已发布' }}</option></select><button v-if="suiteId" type="button" :disabled="versionsLoading" @click="loadVersions(true)">刷新发布版本</button></label>
      <label>运行环境<select aria-label="运行环境" v-model="environment" required><option value="">选择环境</option><option v-if="environment && !environments.some(item => item.id === environment)" :value="environment">当前环境（目录不可用）：{{ environment }}</option><option v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</option></select></label>
      <label>时间规则<select aria-label="时间规则" v-model="rule"><option value="weekdays">工作日</option><option value="daily">每天</option><option value="weekly">每周</option><option value="advanced">高级 Cron</option></select></label>
      <label v-if="rule !== 'advanced'">执行时间<input v-model="time" type="time" required /></label>
      <label v-if="rule === 'weekly'">星期<select aria-label="星期" v-model="weekday"><option v-for="(day, index) in ['周日','周一','周二','周三','周四','周五','周六']" :key="index" :value="String(index)">{{ day }}</option></select></label>
      <label v-if="rule === 'advanced'"><span class="field-caption"><span>标准5段cron</span><HelpHint topic="cron" /></span><input v-model="cron" placeholder="0 9 * * 1-5" required aria-label="标准5段cron" /></label>
      <label><span class="field-caption"><span>IANA时区</span><HelpHint topic="timezone" /></span><input v-model="timezone" required aria-label="IANA时区" /></label>
      <p class="rule-summary">{{ effectiveCron }} · {{ timezone }}。保存后可预览后续触发时间。</p>
      <label><span class="field-caption"><span>错过策略</span><HelpHint topic="missed" /></span><select v-model="missed" aria-label="错过策略"><option>skip</option><option>fire_once</option></select></label><label><span class="field-caption"><span>执行槽忙</span><HelpHint topic="busyPolicy" /></span><select v-model="busyPolicy" aria-label="执行槽忙"><option>queue</option><option>skip</option></select></label>
      <label><span class="field-caption"><span>排队预算秒</span><HelpHint topic="queueBudget" /></span><input v-model.number="queueBudget" type="number" min="1" max="86400" aria-label="排队预算秒" /></label><label><span class="field-caption"><span>执行预算秒</span><HelpHint topic="budget" /></span><input v-model.number="runBudget" type="number" min="1" max="86400" aria-label="执行预算秒" /></label>
      <label><span class="field-caption"><span>参数JSON</span><HelpHint topic="parameters" /></span><textarea v-model="parameters" rows="3" aria-label="参数JSON" /></label>
      <span class="action-help"><button :disabled="busy || versionsLoading">保存为暂停计划</button><HelpHint topic="scheduleSave" /></span>
    </fieldset></form>
    <div class="table-shell"><table><thead><tr><th aria-label="计划/版本">计划/版本<HelpHint topic="configurationRevision" /></th><th aria-label="套件/环境">套件/环境<HelpHint topic="suiteId" /></th><th aria-label="cron/时区">cron/时区<HelpHint topic="cron" /></th><th aria-label="状态">状态<HelpHint topic="scheduleState" /></th><th>操作</th></tr></thead><tbody><tr v-if="!plans.length"><td colspan="5" class="empty-copy">暂无回归计划，填写上方配置后保存。</td></tr>
      <tr v-for="plan in plans" :key="plan.id"><td>{{ plan.name }} r{{ plan.revision }}</td><td>{{ suites.find(item => item.id === plan.suite_id)?.draft.name || plan.suite_id }} v{{ plan.suite_version }} / {{ environments.find(item => item.id === plan.environment_id)?.name || plan.environment_id }}</td>
        <td>{{ plan.cron }} / {{ plan.timezone }}</td><td>{{ plan.status }} · {{ plan.transport_mode || 'historical_unknown' }}<p v-if="plan.migration_required">{{ plan.migration_required }}</p></td>
        <td><button type="button" @click="edit(plan)" :disabled="busy || plan.transport_mode !== 'live'">编辑</button><span class="action-help"><button type="button" @click="preview(plan)" :disabled="busy">预览5次</button><HelpHint topic="schedulePreview" /></span>
          <span class="action-help"><button type="button" @click="change(plan,plan.status==='active'?'pause':'resume')" :disabled="busy || !!plan.migration_required || plan.transport_mode !== 'live'">{{ plan.status==='active'?'暂停':'启用' }}</button><HelpHint topic="scheduleToggle" /></span>
          <span class="action-help"><button type="button" @click="triggers(plan)" :disabled="busy">触发记录</button><HelpHint topic="triggers" /></span><span class="action-help"><button type="button" @click="remove(plan)" :disabled="busy">删除计划</button><HelpHint topic="scheduleDelete" /></span></td>
      </tr></tbody></table></div>
    <section v-if="previewResult" aria-label="触发时间预览"><h4>后续触发时间 · {{ previewResult.timezone }}</h4><p>仅计算时间，不发送业务请求。</p><ol><li v-for="at in previewResult.times" :key="at"><time :datetime="at">{{ at }}</time></li></ol></section>
    <details v-if="triggerResult"><summary>触发记录</summary><pre>{{ triggerResult }}</pre></details>
    <details><summary aria-label="调度与执行器状态">调度与执行器状态<HelpHint topic="scheduler" /></summary><h4>调度 / worker 运维</h4><span class="action-help"><button type="button" @click="status">查看状态</button><HelpHint topic="scheduler" /></span><span class="action-help"><button type="button" @click="pauseAll">暂停全部新触发</button><HelpHint topic="pauseAll" /></span><pre>{{ statusResult }}</pre></details>
    <details><summary aria-label="生成发布回归摘要">生成发布回归摘要<HelpHint topic="report" /></summary><h4>发布回归摘要</h4><label><span class="field-caption"><span>run IDs（逗号分隔）</span><HelpHint topic="reportRuns" /></span><input v-model="reportRuns" aria-label="run IDs（逗号分隔）" /></label><label><span class="field-caption"><span>构建标识</span><HelpHint topic="build" /></span><input v-model="build" aria-label="构建标识" /></label>
    <label><span class="field-caption"><span>报告模式</span><HelpHint topic="reportMode" /></span><select v-model="reportMode" aria-label="报告模式"><option>report_only</option><option>strict</option></select></label><span class="action-help"><button type="button" @click="report">生成摘要（不部署）</button><HelpHint topic="report" /></span><pre>{{ reportResult }}</pre></details>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { managementApi } from '@/api';
import type { EnvironmentSummary } from '@/types/platform';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Plan {id:string;revision:number;name:string;suite_id:string;suite_version:number;environment_id:string;transport_mode:string;cron:string;timezone:string;status:string;missed_policy:string;busy_policy:string;queue_timeout_seconds:number;timeout_seconds:number;parameters:unknown;concurrency_keys?:string[];migration_required?:string}
const emit = defineEmits<{ saved: [] }>();
const plans = ref<Plan[]>([]), selected = ref<Plan | null>(null), busy = ref(false), error = ref(''), notice = ref('');
const suites = ref<{ id: string; draft: {name: string} }[]>([]), environments = ref<EnvironmentSummary[]>([]);
const versions = ref<{version: number; change_note: string}[]>([]), versionsLoading = ref(false);
const name = ref(''), suiteId = ref(''), suiteVersion = ref(0), environment = ref(''), cron = ref('0 9 * * 1-5'), timezone = ref('Asia/Shanghai'), missed = ref('skip'), busyPolicy = ref('queue');
const rule = ref('weekdays'), time = ref('09:00'), weekday = ref('1');
const effectiveCron = computed(() => { if (rule.value === 'advanced') return cron.value; const [hour, minute] = time.value.split(':'); return `${Number(minute)} ${Number(hour)} * * ${rule.value === 'weekdays' ? '1-5' : rule.value === 'weekly' ? weekday.value : '*'}`; });
const queueBudget = ref(300), runBudget = ref(300), parameters = ref('{}');
const previewResult = ref<{timezone: string; times: string[]} | null>(null), triggerResult = ref(''), statusResult = ref('');
const reportRuns = ref(''), build = ref(''), reportMode = ref('report_only'), reportResult = ref('');
const snapshot = () => JSON.stringify([name.value, suiteId.value, suiteVersion.value, environment.value, cron.value, timezone.value, missed.value, busyPolicy.value, queueBudget.value, runBudget.value, parameters.value, rule.value, time.value, weekday.value]);
const savedSnapshot = ref(snapshot());
const dirty = computed(() => snapshot() !== savedSnapshot.value);
const mayDiscard = () => !dirty.value || window.confirm('有未保存计划修改，确认放弃？');
let versionSequence = 0, listSequence = 0;
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value || busy.value) { event.preventDefault(); event.returnValue = ''; } };
onBeforeRouteLeave(() => !busy.value && mayDiscard());
onBeforeUnmount(() => { ++versionSequence; ++listSequence; window.removeEventListener('beforeunload', beforeUnload); });
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try { await fn(); } catch (cause) { error.value = resolveApiErrorMessage(cause, '操作失败，保留原有内容。'); } finally { busy.value = false; }
}
async function refreshPlans() {
  const sequence = ++listSequence;
  const result = await apiClient.get<Plan[]>('/schedule-plans');
  if (sequence === listSequence) {
    plans.value = result;
    if (selected.value) selected.value = result.find(plan => plan.id === selected.value?.id) ?? selected.value;
  }
}
async function load() {
  await act(async () => {
    // Each directory keeps its last successful value when another read fails.
    const results = await Promise.allSettled([
      refreshPlans(),
      apiClient.get<{id: string; draft: {name: string}}[]>('/suite-assets').then(value => { suites.value = value; }),
      managementApi.listEnvironments().then(value => { environments.value = value; }),
    ]);
    const failed = results.find(result => result.status === 'rejected');
    if (failed?.status === 'rejected') throw failed.reason;
  });
}
async function loadVersions(keepVersion = false) {
  const sequence = ++versionSequence, id = suiteId.value;
  if (!keepVersion) { versions.value = []; suiteVersion.value = 0; }
  if (!id) { versionsLoading.value = false; return; }
  versionsLoading.value = true;
  try {
    const result = await apiClient.get<{version: number; change_note: string}[]>(`/suites/${id}/versions`);
    if (sequence !== versionSequence) return;
    versions.value = result;
  } catch (cause) { if (sequence === versionSequence) error.value = resolveApiErrorMessage(cause, '发布版本更新失败，请重试。'); }
  finally { if (sequence === versionSequence) versionsLoading.value = false; }
}
function reset() {
  if (!mayDiscard()) return;
  ++versionSequence; versionsLoading.value = false;
  selected.value = null; name.value = suiteId.value = environment.value = ''; suiteVersion.value = 0; versions.value = [];
  cron.value = '0 9 * * 1-5'; timezone.value = 'Asia/Shanghai'; missed.value = 'skip'; busyPolicy.value = 'queue';
  rule.value = 'weekdays'; time.value = '09:00'; weekday.value = '1'; queueBudget.value = runBudget.value = 300; parameters.value = '{}';
  previewResult.value = null; triggerResult.value = statusResult.value = reportResult.value = reportRuns.value = build.value = ''; reportMode.value = 'report_only';
  notice.value = error.value = ''; savedSnapshot.value = snapshot();
}
function applyPlan(plan: Plan) {
  selected.value = plan; name.value = plan.name; suiteId.value = plan.suite_id; suiteVersion.value = plan.suite_version; environment.value = plan.environment_id;
  cron.value = plan.cron; rule.value = 'advanced'; timezone.value = plan.timezone; missed.value = plan.missed_policy; busyPolicy.value = plan.busy_policy;
  queueBudget.value = plan.queue_timeout_seconds; runBudget.value = plan.timeout_seconds; parameters.value = JSON.stringify(plan.parameters, null, 2);
  previewResult.value = null; triggerResult.value = ''; savedSnapshot.value = snapshot();
}
function edit(plan: Plan) { if (selected.value?.id === plan.id || !mayDiscard()) return; applyPlan(plan); versions.value = []; void loadVersions(true); }
async function save() {
  await act(async () => {
    if (!suiteId.value || !suiteVersion.value || !environment.value || versionsLoading.value) throw new Error('请选择套件、已发布版本和环境');
    if (!versions.value.some(item => item.version === suiteVersion.value)) throw new Error('请先成功读取并选择已发布版本');
    const values: unknown = JSON.parse(parameters.value);
    if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('参数必须为 JSON 对象');
    const definition = {name: name.value, suite_id: suiteId.value, suite_version: suiteVersion.value, environment_id: environment.value, transport_mode: 'live', cron: effectiveCron.value, timezone: timezone.value, missed_policy: missed.value, busy_policy: busyPolicy.value, status: 'paused', concurrency_keys: selected.value?.concurrency_keys ?? [], queue_timeout_seconds: queueBudget.value, timeout_seconds: runBudget.value, parameters: values};
    const result = selected.value ? await apiClient.patch<Plan>(`/schedules/${selected.value.id}`, {expected_revision: selected.value.revision, definition}) : await apiClient.post<Plan>('/schedules', definition);
    applyPlan(result); notice.value = '计划已保存并暂停。'; emit('saved');
    await refreshPlans();
  });
}
async function preview(plan: Plan) { await act(async () => { previewResult.value = await apiClient.get(`/schedules/${plan.id}/preview`); }); }
async function change(plan: Plan, action: string) {
  if (action === 'resume' && !window.confirm(`启用「${plan.name}」后将按计划发送真实请求，确认启用？`)) return;
  await act(async () => { await apiClient.post(`/schedules/${plan.id}/${action}`, {expected_revision: plan.revision}); emit('saved'); await refreshPlans(); });
}
async function remove(plan: Plan) {
  if (!window.confirm(`确认删除「${plan.name}」？不会取消正在运行的任务。`)) return;
  if (selected.value?.id === plan.id && !mayDiscard()) return;
  await act(async () => {
    await apiClient.request(`/schedules/${plan.id}`, {method: 'DELETE', query: {revision: plan.revision}});
    if (selected.value?.id === plan.id) { savedSnapshot.value = snapshot(); reset(); }
    emit('saved'); await refreshPlans();
  });
}
async function triggers(plan: Plan) { await act(async () => { triggerResult.value = JSON.stringify(await apiClient.get(`/schedules/${plan.id}/triggers`), null, 2); }); }
async function status() { await act(async () => { statusResult.value = JSON.stringify(await apiClient.get('/scheduler/status'), null, 2); }); }
async function pauseAll() {
  if (!window.confirm('确认暂停全部计划的新触发？已运行任务继续执行。')) return;
  await act(async () => { await apiClient.post('/scheduler/pause-all'); emit('saved'); await refreshPlans(); });
}
async function report() { await act(async () => { reportResult.value = JSON.stringify(await apiClient.post('/release-reports', {run_ids: reportRuns.value.split(',').map(value => value.trim()).filter(Boolean), mode: reportMode.value, build: build.value}), null, 2); }); }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void load(); });
</script>
<style scoped>
.plan-fields { display:contents; } .rule-summary {overflow-wrap:anywhere;align-self:end;} section,label,fieldset {min-width:0;} time {overflow-wrap:anywhere;}
.plans {padding:1.2rem;background:var(--color-surface,white);border-radius:1rem;} form {display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.5rem;}label {display:grid;gap:.3rem;}input,textarea,select {max-width:100%;padding:.4rem;}pre {white-space:pre-wrap;overflow-wrap:anywhere;max-height:30rem;overflow:auto;}
.plans { display: grid; gap: 16px; padding: 22px; border-radius: var(--radius-large); }
.plans > p { margin: 0; }
.plans > button { justify-self: start; margin: 0; }
form { gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); padding: 20px; background: #fafbfc; border: 1px solid var(--color-border); border-radius: 8px; }
form button { align-self: end; background: var(--color-accent-strong); color: white; border-color: var(--color-accent-strong); }
form > .action-help { align-self: end; }
input, select, textarea { padding: 9px 11px; }
details { border: 1px solid var(--color-border); border-radius: 7px; }
details h4 { margin: 14px; }
@media (max-width:540px) { .plans { padding: 16px; } form { padding: 14px; } }
</style>
