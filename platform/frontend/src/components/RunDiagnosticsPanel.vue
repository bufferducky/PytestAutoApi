<template>
  <section class="diagnostics">
    <h3>失败诊断与证据</h3>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <button type="button" @click="load">刷新诊断</button>
    <button type="button" v-if="diagnostic" @click="copySummary">复制脱敏问题摘要</button>
    <p v-if="notice" class="state-banner state-banner--info">{{ notice }}</p>
    <template v-if="diagnostic">
      <p>状态 {{ diagnostic.status }} · {{ diagnostic.transport_mode }} / {{ diagnostic.validation_scope }} · 清理 {{ diagnostic.cleanup_status }}</p>
      <p>运行 {{ diagnostic.run_id }} / attempt {{ diagnostic.attempt_id || '历史未记录' }}；证据 {{ diagnostic.evidence_completeness }}</p>
      <p>环境 {{ diagnostic.environment_name || diagnostic.environment_id || '未绑定' }}；触发 {{ diagnostic.trigger_source }}</p>
      <p>版本 {{ JSON.stringify(diagnostic.asset_ref || diagnostic.scenario_refs) }}</p>
      <div class="counts"><span v-for="(value,key) in diagnostic.counts" :key="key">{{ key }}：{{ value }}</span></div>
      <aside v-if="diagnostic.first_failure" class="state-banner state-banner--error">
        <strong>首次失败：{{ diagnostic.first_failure.category }} / {{ diagnostic.first_failure.case_id || '运行级' }}</strong>
        <p>{{ diagnostic.first_failure.message }}</p><p>下一步：{{ diagnostic.first_failure.next_action }}</p>
      </aside>
      <ol>
        <li v-for="item in diagnostic.timeline" :key="item.case_id">
          <h4>{{ item.phase }} · {{ item.title }} · {{ item.status }}</h4>
          <p>{{ item.category }}：{{ item.message }}；{{ item.next_action }}</p>
          <p v-if="item.depends_on.length">依赖：{{ item.depends_on.join(', ') }}</p>
          <div v-for="(step,index) in item.steps" :key="index">
            <div class="table-shell"><table><thead><tr><th>断言 / 规则</th><th>来源</th><th>预期</th><th>实际</th><th>结果</th></tr></thead>
              <tbody><tr v-for="(assertion,i) in (step.assertions || [])" :key="i">
                <td>{{ assertion.name }} / {{ assertion.rule_version }}</td><td>{{ assertion.source_ref }}</td>
                <td>{{ JSON.stringify(assertion.expected) }}</td><td>{{ assertion.actual_missing ? '字段缺失' : JSON.stringify(assertion.actual) }}</td><td>{{ assertion.status }}：{{ assertion.message }}</td>
              </tr></tbody>
            </table></div>
            <details><summary>请求 / 响应 / 轮询与重试证据</summary><pre>{{ JSON.stringify(step,null,2) }}</pre></details>
          </div>
        </li>
      </ol>
      <details><summary>公开身份 / 项目快照与资源别名</summary><pre>{{ JSON.stringify({context:diagnostic.context_snapshots,resources:diagnostic.resources},null,2) }}</pre></details>
      <h4>关联复跑与版本对比</h4>
      <button type="button" :disabled="['queued','running'].includes(diagnostic.status)" @click="rerunFailed">仅复跑失败场景（从准备阶段重建）</button>
      <p>原运行：{{ diagnostic.original_run_id || '本次是原始运行' }}。复跑保留失败记录，不覆盖历史。</p>
      <label>对比 run ID <input v-model="otherRunId" /></label><button type="button" :disabled="!otherRunId" @click="compare">比较版本 / 环境 / 首次失败</button>
      <pre v-if="comparison">{{ comparison }}</pre>
      <h4>附件</h4>
      <p>REDACTED 表示脱敏，不是 null；未核验媒体不能外发。缺失、损坏或过期会明确提示。</p>
      <ul><li v-for="artifact in diagnostic.artifacts" :key="artifact.artifact_id">
        {{ artifact.content_type }} · {{ artifact.byte_size }} bytes · {{ artifact.availability }} · {{ artifact.redaction_status }}
        <a :href="artifactUrl(artifact.artifact_id)" target="_blank" rel="noopener">查看 / 下载</a>
        <button type="button" @click="pin(artifact)">{{ artifact.pinned ? '取消保留' : '标记保留' }}</button>
      </li></ul>
      <form @submit.prevent="attach">
        <label>关联步骤 ID（可选）<input v-model="stepId" /></label>
        <label>脱敏 JSON 附件 <textarea v-model="attachment" rows="5" /></label>
        <button>保存 JSON 附件</button>
      </form>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Failure { case_id: string | null; category: string; message?: string; next_action: string }
interface Assertion { name: string; rule_version?: string; source_ref?: string; expected: unknown; actual: unknown; actual_missing?: boolean; status: string; message?: string }
interface Step { assertions?: Assertion[]; [key: string]: unknown }
interface Timeline extends Failure { case_id: string; title: string; status: string; phase: string; depends_on: string[]; steps: Step[] }
interface Artifact { artifact_id: string; content_type: string; byte_size: number; availability: string; redaction_status: string; pinned: boolean }
interface Diagnostic { run_id: string; attempt_id?: string; status: string; transport_mode: string; validation_scope: string;
  cleanup_status: string; evidence_completeness: string; environment_id?: string; environment_name?: string; trigger_source: string;
  asset_ref?: unknown; scenario_refs: unknown[]; counts: Record<string,number>; first_failure: Failure | null;
  timeline: Timeline[]; context_snapshots: unknown; resources: unknown[]; original_run_id?: string; artifacts: Artifact[] }
const props=defineProps<{runId:string}>();
const diagnostic=ref<Diagnostic | null>(null), error=ref(''), notice=ref(''), otherRunId=ref(''), comparison=ref('');
const attachment=ref('{}'),stepId=ref('');let openedAt=new Date().toISOString(),generation=0;
async function load() { const mine=++generation; error.value='';
  try { const result=await apiClient.get<Diagnostic>(`/runs/${props.runId}/diagnostics`); if(mine===generation) diagnostic.value=result; }
  catch(cause) { if(mine===generation){diagnostic.value=null;error.value=resolveApiErrorMessage(cause,'诊断读取失败');} }
}
const artifactUrl=(id:string)=>`${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/,'')}/artifacts/${encodeURIComponent(id)}/content?run_id=${encodeURIComponent(props.runId)}`;
async function copySummary(){ try {
  const result=await apiClient.get(`/runs/${props.runId}/diagnostic-export`);
  await navigator.clipboard.writeText(JSON.stringify(result,null,2));
  await apiClient.post(`/runs/${props.runId}/diagnostic-timing`,{opened_at:openedAt,summary_at:new Date().toISOString(),scope:'browser_open_to_summary_copy'});
  notice.value='已复制脱敏摘要，定位时长按本次打开到复制记录；不代表研发修复耗时。';
}catch(cause){error.value=resolveApiErrorMessage(cause,'摘要复制失败');} }
async function rerunFailed(){try{const run=await apiClient.post<{run_id:string}>(`/runs/${props.runId}/rerun?failed_only=true`);notice.value=`已创建局部复跑 ${run.run_id}；它不代表完整套件通过。`;otherRunId.value=run.run_id;}catch(cause){error.value=resolveApiErrorMessage(cause,'失败场景复跑提交失败');}}
async function compare(){try{comparison.value=JSON.stringify(await apiClient.get(`/runs/${props.runId}/comparison`,{other_run_id:otherRunId.value}),null,2);}catch(cause){error.value=resolveApiErrorMessage(cause,'对比失败');}}
async function attach(){try{await apiClient.post(`/runs/${props.runId}/artifacts`,{step_id:stepId.value || null,content_type:'application/json',content:JSON.parse(attachment.value)});await load();}catch(cause){error.value=resolveApiErrorMessage(cause,'附件保存失败');}}
async function pin(artifact:Artifact){try{await apiClient.post(`/artifacts/${artifact.artifact_id}/pin`,{pinned:!artifact.pinned});await load();}catch(cause){error.value=resolveApiErrorMessage(cause,'保留操作失败');}}
watch(()=>props.runId,()=>{openedAt=new Date().toISOString();diagnostic.value=null;comparison.value='';notice.value='';void load();},{immediate:true});
const timer=setInterval(()=>{if(diagnostic.value && ['queued','running'].includes(diagnostic.value.status))void load();},1500);
onUnmounted(()=>{generation++;clearInterval(timer);});
</script>
<style scoped>
.diagnostics { min-width:0; overflow-wrap:anywhere; padding:1rem; border:1px solid #ddd; border-radius:.8rem; }
.counts { display:flex; gap:.5rem; flex-wrap:wrap; } li { margin-block:.8rem; } label { display:grid; gap:.3rem; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:30rem; overflow:auto; }
td { max-width:18rem; overflow-wrap:anywhere; } textarea,input { max-width:100%; }
</style>
