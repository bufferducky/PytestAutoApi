<template>
  <section class="plans">
    <h3>持久化回归计划</h3><p>固定套件版本；Asia/Shanghai默认。停机错过默认skip，通知默认关闭。R07缺资源/契约暂缓，不能给公司strict发布放行。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <button type="button" @click="load" :disabled="busy">刷新</button><button type="button" @click="selected=null;name=''" :disabled="busy">新计划</button>
    <form @submit.prevent="save">
      <label>名称<input v-model="name" required /></label>
      <label>发布套件 ID<input v-model="suiteId" required /></label><label>固定版本<input v-model.number="suiteVersion" type="number" min="1" /></label>
      <label>环境 ID<input v-model="environment" required /></label>
      <label>标准5段cron<input v-model="cron" placeholder="0 9 * * 1-5" required /></label><label>IANA时区<input v-model="timezone" required /></label>
      <label>错过策略<select v-model="missed"><option>skip</option><option>fire_once</option></select></label><label>执行槽忙<select v-model="busyPolicy"><option>queue</option><option>skip</option></select></label>
      <label>排队预算秒<input v-model.number="queueBudget" type="number" min="1" /></label><label>执行预算秒<input v-model.number="runBudget" type="number" min="1" /></label>
      <label>参数JSON<textarea v-model="parameters" rows="3" /></label>
      <button :disabled="busy">保存为暂停计划</button>
    </form>
    <div class="table-shell"><table><thead><tr><th>计划/版本</th><th>套件/环境</th><th>cron/时区</th><th>状态</th><th>操作</th></tr></thead><tbody>
      <tr v-for="plan in plans" :key="plan.id"><td>{{ plan.name }} r{{ plan.revision }}</td><td>{{ plan.suite_id }} v{{ plan.suite_version }} / {{ plan.environment_id }}</td>
        <td>{{ plan.cron }} / {{ plan.timezone }}</td><td>{{ plan.status }} · {{ plan.transport_mode || 'historical_unknown' }}<p v-if="plan.migration_required">{{ plan.migration_required }}</p></td>
        <td><button type="button" @click="edit(plan)" :disabled="plan.transport_mode !== 'live'">编辑</button><button type="button" @click="preview(plan)">预览5次</button>
          <button type="button" @click="change(plan,plan.status==='active'?'pause':'resume')" :disabled="!!plan.migration_required || plan.transport_mode !== 'live'">{{ plan.status==='active'?'暂停':'启用' }}</button>
          <button type="button" @click="triggers(plan)">触发记录</button><button type="button" @click="remove(plan)">删除计划</button></td>
      </tr></tbody></table></div>
    <pre>{{ previewResult }}</pre>
    <h4>调度/worker运维</h4><button type="button" @click="status">查看状态</button><button type="button" @click="pauseAll">暂停全部新触发</button><pre>{{ statusResult }}</pre>
    <h4>发布回归摘要</h4><label>run IDs（逗号分隔）<input v-model="reportRuns" /></label><label>构建标识<input v-model="build" /></label>
    <label>报告模式<select v-model="reportMode"><option>report_only</option><option>strict</option></select></label><button type="button" @click="report">生成摘要（不部署）</button><pre>{{ reportResult }}</pre>
  </section>
</template>
<script setup lang="ts">
import { onMounted,ref } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Plan {id:string;revision:number;name:string;suite_id:string;suite_version:number;environment_id:string;transport_mode:string;cron:string;timezone:string;status:string;missed_policy:string;busy_policy:string;queue_timeout_seconds:number;timeout_seconds:number;parameters:unknown;migration_required?:string}
const plans=ref<Plan[]>([]),selected=ref<Plan | null>(null),busy=ref(false),error=ref('');
const name=ref(''),suiteId=ref(''),suiteVersion=ref(1),environment=ref(''),cron=ref('0 9 * * 1-5'),timezone=ref('Asia/Shanghai'),missed=ref('skip'),busyPolicy=ref('queue');
const queueBudget=ref(300),runBudget=ref(300),parameters=ref('{}'),previewResult=ref(''),statusResult=ref('');
const reportRuns=ref(''),build=ref(''),reportMode=ref('report_only'),reportResult=ref('');
async function act(fn:()=>Promise<void>){busy.value=true;error.value='';try{await fn();}catch(cause){error.value=resolveApiErrorMessage(cause,'计划操作失败');}finally{busy.value=false;}}
async function load(){await act(async()=>{plans.value=await apiClient.get<Plan[]>('/schedule-plans');});}
function edit(plan:Plan){selected.value=plan;name.value=plan.name;suiteId.value=plan.suite_id;suiteVersion.value=plan.suite_version;environment.value=plan.environment_id;cron.value=plan.cron;timezone.value=plan.timezone;missed.value=plan.missed_policy;busyPolicy.value=plan.busy_policy;queueBudget.value=plan.queue_timeout_seconds;runBudget.value=plan.timeout_seconds;parameters.value=JSON.stringify(plan.parameters,null,2);}
async function save(){await act(async()=>{const definition={name:name.value,suite_id:suiteId.value,suite_version:suiteVersion.value,environment_id:environment.value,transport_mode:'live',cron:cron.value,timezone:timezone.value,missed_policy:missed.value,busy_policy:busyPolicy.value,status:'paused',queue_timeout_seconds:queueBudget.value,timeout_seconds:runBudget.value,parameters:JSON.parse(parameters.value)};
 const result=selected.value?await apiClient.patch<Plan>(`/schedules/${selected.value.id}`,{expected_revision:selected.value.revision,definition}):await apiClient.post<Plan>('/schedules',definition);await load();edit(result);});}
async function preview(plan:Plan){await act(async()=>{previewResult.value=JSON.stringify(await apiClient.get(`/schedules/${plan.id}/preview`),null,2);});}
async function change(plan:Plan,action:string){await act(async()=>{await apiClient.post(`/schedules/${plan.id}/${action}`,{expected_revision:plan.revision});await load();});}
async function remove(plan:Plan){if(!window.confirm('仅删除计划，不取消正在运行的任务，继续？'))return;await act(async()=>{await apiClient.request(`/schedules/${plan.id}`,{method:'DELETE',query:{revision:plan.revision}});await load();});}
async function triggers(plan:Plan){await act(async()=>{previewResult.value=JSON.stringify(await apiClient.get(`/schedules/${plan.id}/triggers`),null,2);});}
async function status(){await act(async()=>{statusResult.value=JSON.stringify(await apiClient.get('/scheduler/status'),null,2);});}
async function pauseAll(){await act(async()=>{await apiClient.post('/scheduler/pause-all');await load();});}
async function report(){await act(async()=>{reportResult.value=JSON.stringify(await apiClient.post('/release-reports',{run_ids:reportRuns.value.split(',').map(s=>s.trim()).filter(Boolean),mode:reportMode.value,build:build.value}),null,2);});}
onMounted(()=>{void load();});
</script>
<style scoped>
.plans {padding:1.2rem;background:var(--color-surface,white);border-radius:1rem;} form {display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.5rem;}label {display:grid;gap:.3rem;}input,textarea,select {max-width:100%;padding:.4rem;}pre {white-space:pre-wrap;overflow-wrap:anywhere;max-height:30rem;overflow:auto;}
</style>
