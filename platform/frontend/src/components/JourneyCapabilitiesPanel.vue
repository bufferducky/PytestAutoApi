<template>
  <section class="journeys">
    <h3>Web / Android关键旅程能力</h3><p>驱动能力、测试构建和业务契约缺失时明确阻塞。受控session协议测试不是公司Web/真机通过。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p><button type="button" @click="load">刷新能力与风险</button>
    <pre>{{ capabilities }}</pre><pre>{{ readiness }}</pre>
    <form @submit.prevent="resolveIsolation"><label><span class="field-caption"><span>隔离记录 ID</span><HelpHint topic="resolveQuarantine" /></span><input v-model="quarantineId" required aria-label="隔离记录 ID" /></label><label><span class="field-caption"><span>修复/验证依据</span><HelpHint topic="resolveQuarantine" /></span><textarea v-model="resolutionReason" required aria-label="修复/验证依据" /></label><span class="action-help"><button>追加解除隔离记录（保留历史）</button><HelpHint topic="resolveQuarantine" /></span></form>
    <form @submit.prevent="save">
      <label>旅程名称<input v-model="name" required /></label><label><span class="field-caption"><span>runner</span><HelpHint topic="runner" /></span><select v-model="runner" aria-label="runner"><option>web</option><option>android</option></select></label>
      <label><span class="field-caption"><span>已确认的业务风险编号（可选）</span><HelpHint topic="riskId" /></span><select v-model="riskId" aria-label="已确认的业务风险编号（可选）"><option value="">仅机制/调试，不归入W/A风险</option><option v-for="id in (runner === 'web' ? ['W01','W02','W03','W04'] : ['A01','A02','A03','A04'])" :key="id">{{ id }}</option></select></label>
      <label><span class="field-caption"><span>构建标识</span><HelpHint topic="build" /></span><input v-model="build" placeholder="真实结果绑定的构建" aria-label="构建标识" /></label>
      <label><span class="field-caption"><span>目标系统</span><HelpHint topic="target" /></span><select v-model="target" required aria-label="目标系统"><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span class="field-caption"><span>身份</span><HelpHint topic="identity" /></span><select v-model="identity" aria-label="身份"><option value="">无</option><option v-for="item in identities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span class="field-caption"><span>项目绑定</span><HelpHint topic="binding" /></span><select v-model="binding" aria-label="项目绑定"><option value="">无</option><option v-for="item in bindings" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label><span class="field-caption"><span>Chromium精确版本</span><HelpHint topic="browserVersion" /></span><input v-model="browserVersion" aria-label="Chromium精确版本" /></label><label><span class="field-caption"><span>设备配置ID / 版本</span><HelpHint topic="device" /></span><input v-model="device" aria-label="设备配置 ID" /><input v-model.number="deviceVersion" type="number" min="1" aria-label="设备配置版本" /></label>
      <label><input v-model="confirmed" type="checkbox" aria-label="业务旅程契约已确认" /><span class="field-caption">业务旅程契约已确认<HelpHint topic="contract" /></span></label><label><input v-model="synthetic" type="checkbox" aria-label="只使用合成/已核验脱敏测试数据" /><span class="field-caption">只使用合成/已核验脱敏测试数据<HelpHint topic="synthetic" /></span></label>
      <label><input v-model="captureTrace" type="checkbox" aria-label="原生Web trace（仅合成且无凭证身份）" /><span class="field-caption">原生Web trace（仅合成且无凭证身份）<HelpHint topic="recording" /></span></label>
      <label><input v-model="captureVideo" type="checkbox" aria-label="Web录屏（同上限制）" /><span class="field-caption">Web录屏（同上限制）<HelpHint topic="recording" /></span></label>
      <details><summary aria-label="言迹测试 Web 查询 smoke">言迹测试 Web 查询 smoke<HelpHint topic="yanjiPack" /></summary><p>复用所选测试目标/身份/项目和 Chromium 版本。登录、菜单、接诊查询及 API 归属回读不代表完整 W01—W04 验收。</p><label><span class="field-caption"><span>预期测试用户 ID</span><HelpHint topic="expectedUser" /></span><input v-model="expectedUserId" aria-label="预期测试用户 ID" /></label><span class="action-help"><button type="button" :disabled="!target || !identity || !binding || !browserVersion || !expectedUserId" @click="importYanjiWeb">创建测试 Web 查询旅程</button><HelpHint topic="yanjiPack" /></span></details>
      <label><span class="field-caption"><span>资源声明JSON（name / definition_id / version / depends_on）</span><HelpHint topic="fixture" /></span><textarea v-model="fixturesJson" rows="4" aria-label="资源声明JSON（name / definition_id / version / depends_on）" /></label>
      <label><span class="field-caption"><span>动作JSON（语义定位或显式api_assert回读）</span><HelpHint topic="journeyActions" /></span><textarea v-model="actions" rows="10" aria-label="动作JSON（语义定位或显式api_assert回读）" /></label><button>保存旅程版本</button>
    </form>
    <p>设备配置通过公开JSON登记，必须提供设备secret_ref、Android版本、App包名/版本/SHA256、本机Appium地址与能力；页面不读取设备序列号原值。</p>
    <details><summary aria-label="设备公开配置JSON">设备公开配置JSON<HelpHint topic="device" /></summary><textarea v-model="deviceJson" rows="8" /><button type="button" @click="saveDevice">登记设备版本</button></details>
    <ul><li v-for="row in journeys" :key="row.id+'-'+row.version">{{ row.data.name }} v{{ row.version }}
      <span class="action-help"><button type="button" @click="preflight(row)">能力预检</button><HelpHint topic="journeyPreflight" /></span><span class="action-help"><button type="button" @click="run(row)">提交（缺能力会阻塞）</button><HelpHint topic="journeyRun" /></span>
      <label><span class="field-caption"><span>隔离原因</span><HelpHint topic="quarantine" /></span><input v-model="reason" aria-label="隔离原因" /></label><label><span class="field-caption"><span>到期（时区ISO）</span><HelpHint topic="isoTime" /></span><input v-model="expires" aria-label="到期（时区ISO）" /></label><span class="action-help"><button type="button" @click="quarantine(row)">标记隔离/仍未验证</button><HelpHint topic="quarantine" /></span>
    </li></ul><pre>{{ result }}</pre>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { onMounted,ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Profile {id:string;name:string}
interface Journey {id:string;version:number;data:{name:string}}
const router=useRouter();
const error=ref(''),capabilities=ref(''),readiness=ref(''),result=ref(''),journeys=ref<Journey[]>([]);
const targets=ref<Profile[]>([]),identities=ref<Profile[]>([]),bindings=ref<Profile[]>([]),expectedUserId=ref('');
const riskId=ref(''),build=ref('unspecified');
const name=ref(''),runner=ref('web'),target=ref(''),identity=ref(''),binding=ref(''),browserVersion=ref(''),device=ref(''),deviceVersion=ref(1),confirmed=ref(false),synthetic=ref(false);
const actions=ref('[{"step_id":"open","name":"打开目标","action":"navigate","path":"/"},{"step_id":"check","name":"验证可见状态","action":"assert_visible","selector":{"strategy":"testid","value":"请按真实页面填写"}}]');
const fixturesJson=ref('[]'),captureTrace=ref(false),captureVideo=ref(false);
const deviceJson=ref('{}'),reason=ref(''),expires=ref(''),quarantineId=ref(''),resolutionReason=ref('');
async function act(fn:()=>Promise<void>){error.value='';try{await fn();}catch(cause){error.value=resolveApiErrorMessage(cause,'旅程操作失败');}}
async function load(){await act(async()=>{const capability=await apiClient.get<{web:{chromium_version?:string}}>('/runner-capabilities');capabilities.value=JSON.stringify(capability,null,2);if(!browserVersion.value) browserVersion.value=capability.web?.chromium_version || ''; readiness.value=JSON.stringify(await apiClient.get('/journey-readiness'),null,2);[journeys.value,targets.value,identities.value,bindings.value]=await Promise.all([apiClient.get<Journey[]>('/journeys'),apiClient.get<Profile[]>('/targets'),apiClient.get<Profile[]>('/identity-profiles'),apiClient.get<Profile[]>('/context-bindings')]);});}
async function save(){await act(async()=>{result.value=JSON.stringify(await apiClient.post('/journeys',{name:name.value,risk_id:riskId.value || null,runner_type:runner.value,target_ref:target.value,identity_ref:identity.value||null,identity_binding_ref:binding.value||null,chromium_version:browserVersion.value||null,device_profile_id:device.value||null,device_profile_version:device.value?deviceVersion.value:null,contract_confirmed:confirmed.value,synthetic_test_data:synthetic.value,capture_trace:captureTrace.value,capture_video:captureVideo.value,actions:JSON.parse(actions.value),fixtures:JSON.parse(fixturesJson.value)}),null,2);await load();});}
async function importYanjiWeb(){await act(async()=>{result.value=JSON.stringify(await apiClient.post('/journeys/import-yanji-query',{target_ref:target.value,identity_ref:identity.value,binding_ref:binding.value,chromium_version:browserVersion.value,expected_user_id:expectedUserId.value}),null,2);await load();});}
async function saveDevice(){await act(async()=>{result.value=JSON.stringify(await apiClient.post('/device-profiles',JSON.parse(deviceJson.value)),null,2);});}
async function preflight(row:Journey){await act(async()=>{result.value=JSON.stringify(await apiClient.post(`/journeys/${row.id}/versions/${row.version}/preflight`),null,2);});}
async function run(row:Journey){await act(async()=>{const run=await apiClient.post<{run_id:string}>(`/journeys/${row.id}/versions/${row.version}/runs`,{build:build.value,transport_mode:'live'});await router.push({name:'runs',query:{runId:run.run_id}});});}
async function quarantine(row:Journey){await act(async()=>{await apiClient.post(`/journeys/${row.id}/versions/${row.version}/quarantine`,{reason:reason.value,expires_at:expires.value});await load();});}
async function resolveIsolation(){await act(async()=>{result.value=JSON.stringify(await apiClient.post(`/journey-quarantines/${quarantineId.value}/resolve`,{reason:resolutionReason.value}),null,2);await load();});}
onMounted(()=>{void load();});
</script>
<style scoped>.journeys {padding:1.2rem;background:var(--color-surface,white);border-radius:1rem;}form,label {display:grid;gap:.4rem;margin-block:.5rem;}input,textarea {max-width:100%;}pre {white-space:pre-wrap;overflow-wrap:anywhere;max-height:25rem;overflow:auto;}</style>
