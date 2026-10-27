<template>
  <section class="diagnostics">
    <h3 aria-label="失败诊断与证据">失败诊断与证据<HelpHint topic="evidence" /></h3>
    <p v-if="error" role="alert" class="state-banner state-banner--error">{{ error }}（已有证据保留，可能不是最新）</p>
    <el-button native-type="button" :disabled="loading" @click="load">{{ loading ? '更新中…' : '刷新诊断' }}</el-button>
    <el-button native-type="button" v-if="diagnostic" @click="copySummary">复制脱敏问题摘要</el-button>
    <p v-if="notice" class="state-banner state-banner--info">{{ notice }}</p>
    <template v-if="diagnostic">
      <p>状态 {{ statusLabel(diagnostic.status) }} · {{ diagnostic.transport_mode }} / {{ diagnostic.validation_scope }} · 清理 {{ diagnostic.cleanup_status }}</p>
      <p>运行 {{ diagnostic.run_id }} / attempt {{ diagnostic.attempt_id || '历史未记录' }}；证据 {{ diagnostic.evidence_completeness }}</p>
      <p>环境 {{ diagnostic.environment_name || diagnostic.environment_id || '未绑定' }}；触发 {{ diagnostic.trigger_source }}</p>
      <p>版本 {{ JSON.stringify(diagnostic.asset_ref || diagnostic.scenario_refs) }}</p>
      <div class="counts"><span v-for="(value,key) in diagnostic.counts" :key="key">{{ key }}：{{ value }}</span></div>
      <aside v-if="diagnostic.first_failure" class="state-banner state-banner--error">
        <strong>首次失败：{{ diagnostic.first_failure.category }} / {{ diagnostic.first_failure.case_id || '运行级' }}</strong>
        <p>{{ diagnostic.first_failure.message }}</p><p>下一步：{{ diagnostic.first_failure.next_action }}</p>
      </aside>
      <h4>步骤证据 · 失败优先</h4><ol>
        <li v-for="item in orderedTimeline" :key="item.case_id"><details :open="isFailure(item.status)"><summary>{{ item.title }} · {{ statusLabel(item.status) }}</summary>
          <h4>{{ item.phase }} · {{ item.title }} · {{ statusLabel(item.status) }}</h4>
          <p>{{ item.category }}：{{ item.message }}；{{ item.next_action }}</p>
          <p v-if="item.depends_on.length">依赖：{{ item.depends_on.join(', ') }}</p>
          <RunStepEvidence v-for="(step,index) in item.steps" :key="index" :step="step" :failed="isFailure(item.status)" />
          </details>
        </li>
      </ol>
      <details><summary aria-label="公开身份 / 项目快照与资源别名">公开身份 / 项目快照与资源别名<HelpHint topic="snapshot" /></summary><pre>{{ JSON.stringify({context:diagnostic.context_snapshots,resources:diagnostic.resources},null,2) }}</pre></details>
      <details><summary>关联复跑与版本对比</summary>
      <span class="action-help"><el-button native-type="button" :disabled="['queued','running'].includes(diagnostic.status)" @click="rerunFailed">仅复跑失败场景（从准备阶段重建）</el-button><HelpHint topic="failedRerun" /></span>
      <p>原运行：{{ diagnostic.original_run_id || '本次是原始运行' }}。复跑保留失败记录，不覆盖历史。</p>
      <label><span class="field-caption"><span>对比 run ID</span><HelpHint topic="compare" /></span><UiInput v-model="otherRunId" aria-label="对比 run ID"  /></label><span class="action-help"><el-button native-type="button" :disabled="!otherRunId" @click="compare">比较版本 / 环境 / 首次失败</el-button><HelpHint topic="compare" /></span>
      <pre v-if="comparison">{{ comparison }}</pre>
      </details><details><summary>附件与证据保留</summary>
      <p>REDACTED 表示脱敏，不是 null；未核验媒体不能外发。缺失、损坏或过期会明确提示。</p>
      <ul><li v-for="artifact in diagnostic.artifacts" :key="artifact.artifact_id">
        {{ artifact.content_type }} · {{ artifact.byte_size }} bytes · {{ artifact.availability }} · {{ artifact.redaction_status }}
        <a :href="artifactUrl(artifact.artifact_id)" target="_blank" rel="noopener">查看 / 下载</a>
        <span class="action-help"><el-button native-type="button" @click="pin(artifact)">{{ artifact.pinned ? '取消保留' : '标记保留' }}</el-button><HelpHint topic="pin" /></span>
      </li></ul>
      <form @submit.prevent="attach">
        <label><span class="field-caption"><span>关联步骤 ID（可选）</span><HelpHint topic="attachmentStep" /></span><UiInput v-model="stepId" aria-label="关联步骤 ID（可选）"  /></label>
        <label><span class="field-caption"><span>脱敏 JSON 附件</span><HelpHint topic="attachment" /></span><UiInput type="textarea" v-model="attachment" rows="5" aria-label="脱敏 JSON 附件"  /></label>
        <span class="action-help"><el-button native-type="submit">保存 JSON 附件</el-button><HelpHint topic="attachment" /></span>
      </form></details>
    </template>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import RunStepEvidence from '@/components/RunStepEvidence.vue';
import { getRunStatusMeta, normalizeRunStatus } from '@/utils/runStatus';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
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
const statusLabel = (value:string) => { const label = getRunStatusMeta(normalizeRunStatus(value)).label; return diagnostic.value?.validation_scope === 'debug' ? (normalizeRunStatus(value) === 'success' ? '调试断言通过' : `调试 · ${label}`) : label; };
const isFailure = (value:string) => ['failed','error','blocked','timed_out','interrupted'].includes(value);
const props=defineProps<{runId:string}>();
const diagnostic=ref<Diagnostic | null>(null), error=ref(''), notice=ref(''), otherRunId=ref(''), comparison=ref('');
const loading=ref(false);
const orderedTimeline=computed(()=>[...(diagnostic.value?.timeline || [])].sort((a,b)=>Number(isFailure(b.status))-Number(isFailure(a.status))));
const attachment=ref('{}'),stepId=ref('');let openedAt=new Date().toISOString(),generation=0;
async function load() { const mine=++generation; error.value=''; loading.value=true;
  try { const result=await apiClient.get<Diagnostic>(`/runs/${props.runId}/diagnostics`); if(mine===generation) diagnostic.value=result; }
  catch(cause) { if(mine===generation){error.value=resolveApiErrorMessage(cause,'诊断读取失败');} }
  finally { if(mine===generation) loading.value=false; }
}
const artifactUrl=(id:string)=>`${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/,'')}/artifacts/${encodeURIComponent(id)}/content?run_id=${encodeURIComponent(props.runId)}`;
async function copySummary(){ try {
  const result=await apiClient.get(`/runs/${props.runId}/diagnostic-export`);
  await navigator.clipboard.writeText(JSON.stringify(result,null,2));
  await apiClient.post(`/runs/${props.runId}/diagnostic-timing`,{opened_at:openedAt,summary_at:new Date().toISOString(),scope:'browser_open_to_summary_copy'});
  notice.value='已复制脱敏摘要，定位时长按本次打开到复制记录；不代表研发修复耗时。';
}catch(cause){error.value=resolveApiErrorMessage(cause,'摘要复制失败');} }
async function rerunFailed(){try{const run=await apiClient.post<{run_id:string}>(`/runs/${props.runId}/rerun?failed_only=true`);notice.value=`已创建局部复跑 ${run.run_id}；它不代表完整套件通过。`;otherRunId.value=run.run_id;}catch(cause){error.value=resolveApiErrorMessage(cause,'失败场景复跑提交失败');}}
async function compare(){const runId=props.runId, other=otherRunId.value;try{const result=await apiClient.get(`/runs/${runId}/comparison`,{other_run_id:other});if(runId===props.runId && other===otherRunId.value)comparison.value=JSON.stringify(result,null,2);}catch(cause){if(runId===props.runId)error.value=resolveApiErrorMessage(cause,'对比失败');}}
async function attach(){try{await apiClient.post(`/runs/${props.runId}/artifacts`,{step_id:stepId.value || null,content_type:'application/json',content:JSON.parse(attachment.value)});await load();}catch(cause){error.value=resolveApiErrorMessage(cause,'附件保存失败');}}
async function pin(artifact:Artifact){try{await apiClient.post(`/artifacts/${artifact.artifact_id}/pin`,{pinned:!artifact.pinned});await load();}catch(cause){error.value=resolveApiErrorMessage(cause,'保留操作失败');}}
watch(()=>props.runId,()=>{openedAt=new Date().toISOString();diagnostic.value=null;comparison.value='';notice.value='';otherRunId.value='';stepId.value='';attachment.value='{}';void load();},{immediate:true});
const timer=setInterval(()=>{if(!document.hidden && !loading.value && diagnostic.value && ['queued','running'].includes(diagnostic.value.status))void load();},1500);
const resume=()=>{if(!document.hidden)void load();};
onMounted(()=>document.addEventListener('visibilitychange',resume));
onUnmounted(()=>{generation++;clearInterval(timer);document.removeEventListener('visibilitychange',resume);});
</script>
<style scoped>
.diagnostics { min-width:0; overflow-wrap:anywhere; padding:1rem; border:1px solid #ddd; border-radius:.8rem; }
.counts { display:flex; gap:.5rem; flex-wrap:wrap; } li { margin-block:.8rem; } label { display:grid; gap:.3rem; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:30rem; overflow:auto; }
td { max-width:18rem; overflow-wrap:anywhere; } textarea,input { max-width:100%; }
</style>
