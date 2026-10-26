<template>
  <section class="evaluation">
    <h3 aria-label="AI / 语音评估历史">AI / 语音评估历史<HelpHint topic="evaluation" /></h3>
    <p class="state-banner state-banner--info" role="status">新评估已禁用：尚未接入真实评估服务。历史报告与详情仍可查询，历史模拟结果不代表真实验证。</p>
    <button type="button" disabled>新建评估（已禁用）</button>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <button type="button" @click="load">刷新历史版本</button>
    <details><summary aria-label="历史样本集与规则版本">历史样本集与规则版本<HelpHint topic="evaluation" /></summary>
      <pre>{{ JSON.stringify({ datasets, rubrics }, null, 2) }}</pre>
    </details>
    <label><span class="field-caption"><span>历史 run ID</span><HelpHint topic="evaluation" /></span><input v-model="queryRun" aria-label="历史 run ID" /></label>
    <button type="button" @click="report" :disabled="!queryRun.trim()">查看评估报告</button>
    <label><span class="field-caption"><span>对比 run ID</span><HelpHint topic="evaluationCompare" /></span><input v-model="otherRun" aria-label="对比 run ID" /></label>
    <span class="action-help"><button type="button" @click="compare" :disabled="!queryRun.trim() || !otherRun.trim()">同集合/规则/采样对比</button><HelpHint topic="evaluationCompare" /></span>
    <pre v-if="result">{{ result }}</pre>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
const error = ref(''), datasets = ref<unknown[]>([]), rubrics = ref<unknown[]>([]);
const queryRun = ref(''), otherRun = ref(''), result = ref('');
async function act(operation: () => Promise<void>) {
  error.value = '';
  try { await operation(); }
  catch (cause) { error.value = resolveApiErrorMessage(cause, '评估历史读取失败'); }
}
async function load() { await act(async () => {
  [datasets.value, rubrics.value] = await Promise.all([
    apiClient.get<unknown[]>('/evaluation-datasets'), apiClient.get<unknown[]>('/rubrics'),
  ]);
}); }
async function report() { result.value = ''; await act(async () => {
  result.value = JSON.stringify(await apiClient.get(`/evaluation-runs/${encodeURIComponent(queryRun.value.trim())}`), null, 2);
}); }
async function compare() { result.value = ''; await act(async () => {
  result.value = JSON.stringify(await apiClient.get(`/evaluation-runs/${encodeURIComponent(queryRun.value.trim())}/comparison`, { other_run_id: otherRun.value.trim() }), null, 2);
}); }
onMounted(() => { void load(); });
</script>
<style scoped>.evaluation {padding:1.2rem;background:var(--color-surface,white);border-radius:1rem;}form,label {display:grid;gap:.4rem;margin-block:.6rem;}input,textarea {max-width:100%;}pre {white-space:pre-wrap;overflow-wrap:anywhere;max-height:40rem;overflow:auto;}</style>
