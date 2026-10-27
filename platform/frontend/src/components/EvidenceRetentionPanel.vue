<template>
  <section class="retention">
    <h3>证据保留与回收预览</h3><p>默认元数据90天、普通附件14天、失败附件30天。先预览，再只回收本次选择范围；活跃或保留标记的证据不会回收。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <form @submit.prevent="save">
      <label><span class="field-caption"><span>详细元数据保留天数</span><HelpHint topic="retentionDays" /></span><UiInput v-model.number="policy.metadata_days" type="number" min="1" max="3650" aria-label="详细元数据保留天数"  /></label>
      <label><span class="field-caption"><span>普通附件保留天数</span><HelpHint topic="retentionDays" /></span><UiInput v-model.number="policy.attachment_days" type="number" min="1" max="3650" aria-label="普通附件保留天数"  /></label>
      <label><span class="field-caption"><span>失败附件保留天数</span><HelpHint topic="retentionDays" /></span><UiInput v-model.number="policy.failure_attachment_days" type="number" min="1" max="3650" aria-label="失败附件保留天数"  /></label>
      <el-button native-type="submit">保存未来保留策略</el-button>
    </form>
    <span class="action-help"><el-button native-type="button" @click="preview">只读预览</el-button><HelpHint topic="retention" /></span>
    <pre v-if="plan">{{ JSON.stringify(plan,null,2) }}</pre>
    <label><input v-model="confirmed" type="checkbox" aria-label="已核对上方到期范围，保留其他证据" /><span class="field-caption">已核对上方到期范围，保留其他证据<HelpHint topic="reclaim" /></span></label>
    <span class="action-help"><el-button native-type="button" :disabled="!plan || !confirmed" @click="apply">回收预览中的到期证据</el-button><HelpHint topic="reclaim" /></span>
    <JsonResult v-if="result" :value="result" />
  </section>
</template>
<script setup lang="ts">
import JsonResult from '@/components/common/JsonResult.vue';
import HelpHint from '@/components/common/HelpHint.vue';
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Policy {metadata_days:number;attachment_days:number;failure_attachment_days:number}
interface Plan {ready:string[];preserved:string[];metadata_ready:string[];policy:Policy}

const policy=ref<Policy>({metadata_days:90,attachment_days:14,failure_attachment_days:30});
const plan=ref<Plan | null>(null),confirmed=ref(false),error=ref(''),result=ref('');
async function save(){try{policy.value=await apiClient.patch<Policy>('/artifact-retention/policy',policy.value);plan.value=null;confirmed.value=false;}catch(cause){error.value=resolveApiErrorMessage(cause,'策略保存失败');}}
async function preview(){try{plan.value=await apiClient.get<Plan>('/artifact-retention/preview');confirmed.value=false;}catch(cause){error.value=resolveApiErrorMessage(cause,'保留预览失败');}}
async function apply(){if(!plan.value)return;try{result.value=JSON.stringify(await apiClient.post('/artifact-retention/apply',{artifact_ids:plan.value.ready,run_ids:plan.value.metadata_ready}),null,2);plan.value=null;confirmed.value=false;}catch(cause){error.value=resolveApiErrorMessage(cause,'证据回收失败');}}
onMounted(async()=>{try{policy.value=await apiClient.get<Policy>('/artifact-retention/policy');}catch(cause){error.value=resolveApiErrorMessage(cause,'策略读取失败');}});
</script>
<style scoped>
.retention { padding:1.2rem; background:var(--color-surface,white); border-radius:1rem; } form,label {display:grid;gap:.4rem;margin-block:.6rem;}
pre {white-space:pre-wrap;overflow-wrap:anywhere;}
</style>
