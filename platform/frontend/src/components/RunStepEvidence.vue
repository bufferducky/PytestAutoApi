<template>
  <article class="step-evidence"><el-tabs v-model="section" aria-label="步骤证据分区"><el-tab-pane label="响应" name="response" /><el-tab-pane label="请求" name="request" /><el-tab-pane label="断言" name="assertions" /><el-tab-pane label="变量提取" name="extractors" /><el-tab-pane label="完整证据" name="raw" /></el-tabs>
    <div v-if="section === 'assertions' && assertions.length" class="table-shell"><table><thead><tr><th>断言 / 规则</th><th>预期</th><th>实际</th><th>结果</th></tr></thead><tbody>
      <tr v-for="(assertion,index) in assertions" :key="index" :class="{'assertion-failed': !['passed','succeeded','success'].includes(String(assertion.status))}">
        <td>{{ assertion.name }}<small>{{ assertion.source_ref }} {{ assertion.rule_version }}</small></td>
        <td><pre>{{ format(assertion.expected) }}</pre></td><td><pre>{{ assertion.actual_missing ? '字段缺失' : format(assertion.actual) }}</pre></td>
        <td>{{ statusLabel(String(assertion.status)) }}<small>{{ assertion.message }}</small></td>
      </tr>
    </tbody></table></div>
<pre v-if="section==='request' || section==='response'">{{ format(step[section]) }}</pre><pre v-if="section==='extractors'">{{ format(step.extractors || step.outputs) }}</pre><pre v-if="section==='raw'">{{ format(step) }}</pre><el-empty v-if="section==='assertions' && !assertions.length" description="未记录断言" :image-size="40" />
  </article>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
import { getRunStatusMeta, normalizeRunStatus } from '@/utils/runStatus';
const props = defineProps<{step: Record<string,unknown>; failed?: boolean}>();
const assertions = computed(() => Array.isArray(props.step.assertions) ? props.step.assertions.filter((value): value is Record<string,unknown> => typeof value === 'object' && value !== null) : []);
const section=ref(props.failed ? 'assertions' : 'response');
const httpSections = [{key:'request',label:'请求（脱敏）'},{key:'response',label:'响应（脱敏）'}];
const format = (value:unknown) => value === undefined ? '未记录' : JSON.stringify(value,null,2);
const statusLabel = (value:string) => getRunStatusMeta(normalizeRunStatus(value)).label;
</script>
<style scoped>
.step-evidence { display:grid;gap:8px;min-width:0; }
.http-evidence { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px; }
pre { margin:0;max-height:24rem;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere; }
td { max-width:22rem;vertical-align:top; } small { display:block;overflow-wrap:anywhere; }
.assertion-failed { background:rgba(244,63,94,.06); }
@media(max-width:760px) { .http-evidence { grid-template-columns:minmax(0,1fr); } }
</style>
