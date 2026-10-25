<template>
  <section class="coverage-panel">
    <h3>逆向证据与业务风险覆盖账本</h3>
    <p>静态调用表达式不是已验证在线接口。导入只读本地归档，不发送业务请求；确认需留下依据与版本引用。</p>
    <button type="button" :disabled="busy" @click="importResearch">导入三端研究账本</button>
    <button type="button" :disabled="busy" @click="load">刷新覆盖</button>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="summary">静态观察 {{ summary.total_observations }}；已确认风险 {{ summary.confirmed_risks }}；近期有效 live 验证 {{ summary.verified_risks }}（{{ summary.freshness_days }} 天）</p>
    <label>目标端 <select v-model="system"><option value="">全部</option><option>center</option><option>saas</option><option>app</option></select></label>
    <label>检索风险/路径 <input v-model="search" /></label>
    <p>符合筛选 {{ filtered.length }} 条；当前页 {{ page + 1 }}</p>
    <button type="button" :disabled="page === 0" @click="page--">上一页</button>
    <button type="button" :disabled="(page + 1)*20 >= filtered.length" @click="page++">下一页</button>
    <table><thead><tr><th>端</th><th>风险 / 静态表达式</th><th>契约</th><th>覆盖</th><th>操作</th></tr></thead>
      <tbody><tr v-for="item in filtered.slice(page*20, (page+1)*20)" :key="item.id">
        <td>{{ item.system }}</td><td>{{ item.risk }}<br />{{ item.method }} {{ item.expression }}</td>
        <td>{{ item.contract_status }}</td><td>{{ item.coverage_status }}</td>
        <td><button type="button" @click="select(item)">查看 / 关联</button></td>
      </tr></tbody>
    </table>
    <form v-if="selected" @submit.prevent="save">
      <h4>证据：{{ selected.id }}</h4>
      <p>来源 {{ selected.source }} · 位置 {{ JSON.stringify(selected.location) }} · 日期 {{ selected.evidence_time }}</p>
      <p>原始字段未知：{{ selected.request_fields === null ? '是，不代表无需请求参数' : '查看来源' }}</p>
      <label>风险说明 <input v-model="risk" /></label>
      <label>核心风险编号（可选S01—S16）<input v-model="regressionId" placeholder="按已确认业务契约关联，不自动推断" /></label>
      <label><input type="checkbox" v-model="requiredForRelease" />此风险为发布必需（核心S风险自动必需）</label>
      <label>契约状态 <select v-model="status"><option>unconfirmed</option><option>confirmed</option><option>blocked</option></select></label>
      <label>契约依据 / 确认人 / 日期 <textarea v-model="note" rows="3" /></label>
      <label>场景引用 JSON（scenario_id/version）<textarea v-model="references" rows="4" /></label>
      <button :disabled="busy">保存关联与依据</button>
      <pre>{{ JSON.stringify(selected.latest_live_evidence, null, 2) }}</pre>
    </form>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Item { id: string; revision: number; system: string; risk: string; method: string; expression: string;
  regression_id?: string; required_for_release?: boolean; contract_status: string; contract_note?: string; scenario_refs: unknown[]; coverage_status: string;
  source: string; location: unknown; evidence_time: string; request_fields: unknown; latest_live_evidence: unknown; }
interface Summary { total_observations: number; confirmed_risks: number; verified_risks: number; freshness_days: number; items: Item[] }

const busy = ref(false), error = ref(''), summary = ref<Summary | null>(null);
const system = ref(''), search = ref(''), page = ref(0), selected = ref<Item | null>(null);
const regressionId=ref(''),requiredForRelease=ref(false);
const risk = ref(''), status = ref('unconfirmed'), note = ref(''), references = ref('[]');
const filtered = computed(() => (summary.value?.items || []).filter(item => (!system.value || item.system === system.value) &&
  `${item.risk} ${item.expression}`.includes(search.value)));
watch([system, search], () => { page.value = 0; });
function select(item: Item) { regressionId.value=item.regression_id || '';requiredForRelease.value=item.required_for_release===true; selected.value = item; risk.value = item.risk; status.value = item.contract_status;
  note.value = item.contract_note || ''; references.value = JSON.stringify(item.scenario_refs, null, 2); }
async function load() {
  
  busy.value = true; error.value = '';
  try { summary.value = await apiClient.get<Summary>('/coverage-summary'); }
  catch(cause) { error.value = resolveApiErrorMessage(cause, '覆盖读取失败'); }
  finally { busy.value = false; }
}
async function importResearch() { busy.value = true; error.value = '';
  try { await apiClient.post('/coverage-items/import-research'); await load(); }
  catch(cause) { error.value = resolveApiErrorMessage(cause, '研究导入失败'); }
  finally { busy.value = false; }
}
async function save() {
  if (!selected.value) return;
  busy.value = true; error.value = '';
  try {
    const saved = await apiClient.patch<Item>(`/coverage-items/${selected.value.id}`, { expected_revision: selected.value.revision,
      changes: { regression_id:regressionId.value || null,required_for_release:requiredForRelease.value,risk: risk.value, contract_status: status.value, contract_note: note.value, scenario_refs: JSON.parse(references.value) } });
    await load(); selected.value = summary.value?.items.find(item => item.id === saved.id) || saved;
  } catch(cause) { error.value = resolveApiErrorMessage(cause, '覆盖保存失败'); }
  finally { busy.value = false; }
}
onMounted(() => { void load(); });
</script>
<style scoped>
.coverage-panel { padding: 1.5rem; border-radius: 1rem; background: var(--color-surface, white); }
label,form { display: grid; gap: .4rem; margin-block: .5rem; }
table { width: 100%; overflow-wrap: anywhere; } td { max-width: 30rem; }
textarea { max-width: 100%; } pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
