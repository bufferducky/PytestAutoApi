<template>
  <section class="debug-panel" aria-label="当前草稿调试" tabindex="-1">
    <h3>{{ stepId ? `单步骤调试 · ${stepId}` : '当前整场景调试' }}</h3>
    <p>使用当前未保存内容，不保存或发布。{{ stepId ? '仅发送所选步骤；不会自动执行前置业务步骤。' : '将执行场景内的准备、业务与清理步骤。' }}</p>
    <div class="debug-fields">
      <label>调试环境 <select v-model="environment"><option value="">按目标自动确定</option><option v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</option></select></label>
      <label>被测构建 <input v-model="build" placeholder="未知则留空" /></label>
      <label>本次公开参数 JSON <textarea v-model="parameters" rows="3" /></label>
      <label v-if="stepId">前置 outputs 输入 JSON <textarea v-model="inputs" rows="3" placeholder='{"create":{"id":"public-item-id"}}' /></label>
    </div>
    <button type="button" :disabled="busy || refreshing || active" @click="start">确认范围并真实调试</button>
    <button v-if="runId" type="button" :disabled="busy || refreshing" @click="refresh">刷新调试结果</button>
    <button v-if="active" type="button" :disabled="busy" @click="cancel">取消调试</button>
    <p v-if="error" role="alert" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="runId" role="status">调试 {{ runId }} · {{ result ? statusLabel(result.status) : '读取中' }} · {{ runScope }}</p>
    <template v-if="result">
      <p v-if="failure" class="state-banner state-banner--error">首个失败步骤：{{ failure.step_id || failure.name }} · {{ statusLabel(failure.status) }}</p>
      <ol><li v-for="(step, index) in debugSteps" :key="index">
        <details :open="isFailure(step.status)"><summary>{{ step.step_id || step.name || index + 1 }} · {{ statusLabel(step.status) }}</summary>
          <p v-if="step.error || step.message">{{ step.error || step.message }}</p>
          <RunStepEvidence :step="step" :failed="isFailure(step.status)" />
        </details>
      </li></ol>
      <details><summary>完整调试记录</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import RunStepEvidence from '@/components/RunStepEvidence.vue';
import { getRunStatusMeta, normalizeRunStatus } from '@/utils/runStatus';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
import { debugInputs } from '@/utils/debugInputs';
const props = defineProps<{ getDraft: () => Record<string, unknown>; assetId?: string; revision?: number; stepId?: string; environments: { id: string; name: string }[] }>();
const environment = ref(''), build = ref(''), parameters = ref('{}'), inputs = ref('{}');
const busy = ref(false), refreshing = ref(false), error = ref(''), runId = ref(''), runScope = ref('');
const statusLabel = (status: unknown) => status === 'cancelling' ? '取消中' : getRunStatusMeta(normalizeRunStatus(String(status))).label;
const isFailure = (status: unknown) => ['failed', 'error', 'blocked', 'timed_out', 'interrupted'].includes(String(status));
const result = ref<Record<string, unknown> | null>(null);
const active = computed(() => !!runId.value && (!result.value || ['queued', 'running', 'cancelling', 'pending'].includes(String(result.value.status))));
const debugSteps = computed<Record<string, unknown>[]>(() => {
  const data = result.value?.steps || result.value?.step_results || result.value?.results;
  if (!Array.isArray(data)) return [];
  return data.flatMap(item => Array.isArray(item.steps) && item.steps.length ? item.steps : [item]);
});
const failure = computed(() => debugSteps.value.find(step => ['failed', 'error', 'blocked', 'timed_out', 'interrupted'].includes(String(step.status))));
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false, generation = 0, requestSequence = 0;
const current = (scope: number) => !disposed && scope === generation;
function stop() { if (timer) clearTimeout(timer); timer = undefined; }
function resetScope() {
  ++generation; ++requestSequence; stop();
  busy.value = false; refreshing.value = false; error.value = ''; runId.value = ''; runScope.value = ''; result.value = null; inputs.value = '{}';
}
watch(() => [props.assetId, props.stepId], resetScope);
function visibilityChanged() {
  stop();
  if (!document.hidden && active.value) void refresh();
}
onMounted(() => document.addEventListener('visibilitychange', visibilityChanged));
onBeforeUnmount(() => {
  disposed = true; ++generation; ++requestSequence; stop();
  document.removeEventListener('visibilitychange', visibilityChanged);
});
async function refresh() {
  if (disposed || !runId.value || refreshing.value || document.hidden) return;
  const scope = generation, sequence = ++requestSequence, id = runId.value;
  refreshing.value = true; stop();
  try {
    const data = await apiClient.get<Record<string, unknown>>(`/runs/${id}`);
    if (!current(scope) || sequence !== requestSequence || id !== runId.value) return;
    result.value = data; error.value = '';
    if (active.value && !document.hidden) timer = setTimeout(() => void refresh(), 1500);
  } catch (cause) {
    if (current(scope) && sequence === requestSequence) error.value = resolveApiErrorMessage(cause, '调试结果更新失败，保留上次结果；可手动刷新。');
  } finally { if (current(scope) && sequence === requestSequence) refreshing.value = false; }
}
async function start() {
  if (disposed || busy.value || refreshing.value || active.value) return;
  const generationAtStart = generation;
  busy.value = true; error.value = '';
  try {
    const draft = JSON.parse(JSON.stringify(props.getDraft())) as Record<string, unknown>;
    const selected = (draft.steps as Record<string, unknown>[] | undefined)?.find(step => step.step_id === props.stepId);
    if (props.stepId && !selected) throw new Error('所选步骤已删除或改名，请重新选择调试步骤。');
    const supplied = selected ? debugInputs(selected, inputs.value) : undefined;
    const params: unknown = JSON.parse(parameters.value);
    if (!params || typeof params !== 'object' || Array.isArray(params)) throw new Error('公开参数必须为对象');
    const scope = selected ? [selected] : (draft.steps as Record<string, unknown>[] || []);
    if (!scope.length) throw new Error('请先添加步骤');
    const description = scope.map(step => `${step.step_id}: ${(step.request as Record<string, unknown>)?.method || step.type} ${(step.request as Record<string, unknown>)?.url || ''} (${step.operation_kind})`).join('\n');
    if (!window.confirm(`确认真实执行${selected ? '单步骤（不执行前置步骤）' : '整场景（含准备与清理）'}？\n环境：${environment.value || '按目标确定'}\n${description}\n可能产生业务写入；当前草稿不会保存或发布。`)) return;
    const scopeLabel = `${draft.name || '未命名场景'} · ${props.assetId || '未保存草稿'}${props.revision ? ` r${props.revision}` : ''} · ${props.stepId || '整场景'} · ${props.environments.find(item => item.id === environment.value)?.name || environment.value || '按目标确定环境'}`;
    const response = await apiClient.post<{ run_id: string }>('/scenarios/debug', { draft, asset_id: props.assetId, revision: props.revision, step_id: props.stepId || undefined, inputs: supplied, environment_id: environment.value || undefined, parameters: params, build: build.value.trim() || 'unspecified', live_confirmed: true });
    if (!current(generationAtStart)) return;
    stop(); runId.value = response.run_id; runScope.value = scopeLabel; result.value = null; await refresh();
  } catch (cause) { if (current(generationAtStart)) error.value = resolveApiErrorMessage(cause, '调试提交失败'); }
  finally { if (current(generationAtStart)) busy.value = false; }
}
async function cancel() {
  if (disposed || busy.value || !active.value) return;
  const scope = generation, id = runId.value;
  busy.value = true; stop(); ++requestSequence; refreshing.value = false;
  try {
    await apiClient.post(`/runs/${id}/cancel`);
    if (current(scope) && id === runId.value) await refresh();
  } catch (cause) { if (current(scope)) error.value = resolveApiErrorMessage(cause, '取消失败'); }
  finally { if (current(scope)) busy.value = false; }
}
</script>
<style scoped>
.debug-panel { min-width: 0; display: grid; gap: 10px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-medium); background: white; }
.debug-panel h3, .debug-panel p { margin: 0; overflow-wrap: anywhere; } .debug-fields { min-width: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; } label { display: grid; gap: 5px; min-width: 0; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 28rem; overflow: auto; } @media(max-width:540px) { .debug-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
