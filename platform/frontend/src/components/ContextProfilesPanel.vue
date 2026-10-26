<template>
  <section class="context-panel">
    <h3>目标系统、身份与项目绑定</h3>
    <p>维护目标地址、登录方式与项目上下文。凭证只保存引用，不回显明文。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info">{{ message }}</p>
    <label><span class="field-caption"><span>配置类型</span><HelpHint topic="profileKind" /></span><select v-model="kind" @change="load" aria-label="配置类型">
        <option value="targets">目标系统</option>
        <option value="identity-profiles">身份</option>
        <option value="context-bindings">租户 / 项目绑定</option>
      </select>
    </label>
    <button type="button" :disabled="busy" @click="newProfile">新增配置</button>
    <button type="button" :disabled="busy" @click="load">刷新</button>
    <div class="profiles-grid">
      <ul>
        <li v-for="item in profiles" :key="String(item.id)">
          <button type="button" @click="select(item)">{{ item.name }} · v{{ item.revision }}</button>
        </li>
        <li v-if="!profiles.length">暂无公开配置</li>
      </ul>
      <form @submit.prevent="save">
        <label>名称 <input v-model="name" required /></label>
        <template v-if="kind === 'targets'">
          <label><span class="field-caption"><span>环境</span><HelpHint topic="environment" /></span><select v-model="environmentId" required aria-label="环境">
              <option v-for="env in environments" :value="env.id" :key="env.id">{{ env.name }}</option>
            </select>
          </label>
          <label><span class="field-caption"><span>基础地址</span><HelpHint topic="baseUrl" /></span><input v-model="baseUrl" type="url" required aria-label="基础地址" /></label>
          <label><input v-model="requiresContext" type="checkbox" aria-label="要求项目上下文" /><span class="field-caption">要求项目上下文<HelpHint topic="requiresContext" /></span></label>
          <label><span class="field-caption"><span>认证方式</span><HelpHint topic="authMode" /></span><select v-model="authMode" aria-label="认证方式"><option value="none">无认证</option><option value="password">密码登录</option></select>
          </label>
          <label><span class="field-caption"><span>登录路径</span><HelpHint topic="loginPath" /></span><input v-model="loginPath" aria-label="登录路径" /></label>
          <label><span class="field-caption"><span>请求格式</span><HelpHint topic="requestMode" /></span><select v-model="requestMode" aria-label="请求格式"><option value="json">JSON</option><option value="form">表单</option></select></label>
          <label><span class="field-caption"><span>密码转换</span><HelpHint topic="passwordTransform" /></span><select v-model="passwordTransform" aria-label="密码转换"><option value="none">不转换（引用原值）</option><option value="md5">MD5</option></select></label>
          <label><span class="field-caption"><span>令牌字段路径</span><HelpHint topic="tokenPath" /></span><input v-model="tokenPath" aria-label="令牌字段路径" /></label>
          <label><span class="field-caption"><span>终端 User-Agent（可选）</span><HelpHint topic="userAgent" /></span><input v-model="userAgent" aria-label="终端 User-Agent（可选）" /></label>
          <label><span class="field-caption"><span>归属查询路径</span><HelpHint topic="scopePath" /></span><input v-model="scopePath" placeholder="/api/v1/user/role_info" aria-label="归属查询路径" /></label>
          <label><span class="field-caption"><span>租户回读字段</span><HelpHint topic="tenantPath" /></span><input v-model="tenantPath" placeholder="data.tenantId" aria-label="租户回读字段" /></label>
          <label><span class="field-caption"><span>项目回读字段</span><HelpHint topic="projectPath" /></span><input v-model="projectPath" placeholder="data.deptId" aria-label="项目回读字段" /></label>
          <label><input v-model="scopeConfirmed" type="checkbox" aria-label="此归属查询契约已确认" /><span class="field-caption">此归属查询契约已确认<HelpHint topic="contract" /></span></label>
          <label><span class="field-caption"><span>令牌格式</span><HelpHint topic="headerTemplate" /></span><select v-model="headerTemplate" aria-label="令牌格式"><option value="{token}">原始 Token</option><option value="Bearer {token}">Bearer</option></select>
          </label>
          <label><input v-model="confirmed" type="checkbox" aria-label="登录契约已确认" /><span class="field-caption">登录契约已确认<HelpHint topic="contract" /></span></label>
        </template>
        <template v-if="kind === 'identity-profiles'">
          <label><span class="field-caption"><span>支持的目标系统</span><HelpHint topic="targetIds" /></span><select v-model="targetIds" multiple required aria-label="支持的目标系统"><option v-for="item in targets" :key="String(item.id)" :value="String(item.id)">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>账号引用</span><HelpHint topic="secretRef" /></span><input v-model="usernameRef" placeholder="env:PYTA_SECRET_USER" required aria-label="账号引用" /></label>
          <label><span class="field-caption"><span>密码引用</span><HelpHint topic="secretRef" /></span><input v-model="passwordRef" placeholder="env:PYTA_SECRET_PASSWORD" required aria-label="密码引用" /></label>
          <label>角色说明 <input v-model="roleDescription" /></label>
        </template>
        <template v-if="kind === 'context-bindings'">
          <label><span class="field-caption"><span>目标系统</span><HelpHint topic="target" /></span><select v-model="targetId" required aria-label="目标系统"><option v-for="item in targets" :key="String(item.id)" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>身份</span><HelpHint topic="identity" /></span><select v-model="identityId" required aria-label="身份"><option v-for="item in identities" :key="String(item.id)" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>租户 ID</span><HelpHint topic="tenantId" /></span><input v-model="tenantId" required aria-label="租户 ID" /></label>
          <label><span class="field-caption"><span>项目 ID</span><HelpHint topic="projectId" /></span><input v-model="projectId" required aria-label="项目 ID" /></label>
        </template>
        <details><summary aria-label="高级公开配置（结构化 JSON）">高级公开配置（结构化 JSON）<HelpHint topic="profileAdvanced" /></summary>
          <p>可编辑 form、token_path、过期规则与已确认的查询预检。普通字段以表单为准，不填写秘密值。</p>
          <textarea v-model="advanced" rows="12" aria-label="高级公开配置" />
        </details>
        <p>ID：{{ selected?.id || '保存时生成' }}；版本：{{ selected?.revision || 1 }}</p>
        <button :disabled="busy" type="submit">保存公开配置</button>
        <button v-if="selected" :disabled="busy" type="button" @click="remove">删除</button>
      </form>
    </div>
    <h4>登录与项目预检</h4>
    <form @submit.prevent="preflight">
      <label><span class="field-caption"><span>预检环境</span><HelpHint topic="environment" /></span><select v-model="preEnvironment" required aria-label="预检环境"><option v-for="item in environments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label><span class="field-caption"><span>预检目标</span><HelpHint topic="target" /></span><select v-model="preTarget" required aria-label="预检目标"><option v-for="item in targets" :key="String(item.id)" :value="item.id">{{ item.name }}</option></select></label>
      <label><span class="field-caption"><span>预检身份</span><HelpHint topic="identity" /></span><select v-model="preIdentity" aria-label="预检身份"><option value="">无</option><option v-for="item in identities" :key="String(item.id)" :value="item.id">{{ item.name }}</option></select></label>
      <label><span class="field-caption"><span>预检项目绑定</span><HelpHint topic="binding" /></span><select v-model="preBinding" aria-label="预检项目绑定"><option value="">无</option><option v-for="item in bindings" :key="String(item.id)" :value="item.id">{{ item.name }}</option></select></label>
      <label><input v-model="executeLogin" type="checkbox" aria-label="执行已确认登录与查询（否则只校验配置/引用）" /><span class="field-caption">执行已确认登录与查询（否则只校验配置/引用）<HelpHint topic="executeLogin" /></span></label>
      <span class="action-help"><button :disabled="busy">预检</button><HelpHint topic="contextPreflight" /></span>
    </form>
    <pre v-if="preResult">{{ preResult }}</pre>
  </section>
</template>

<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import { managementApi } from '@/api/modules/management';
import type { EnvironmentSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

type RecordData = Record<string, unknown>;
const kind = ref('targets');
const profiles = ref<RecordData[]>([]);
const environments = ref<EnvironmentSummary[]>([]);
const selected = ref<RecordData | null>(null);
const busy = ref(false), error = ref(''), message = ref('');
const name = ref(''), environmentId = ref(''), baseUrl = ref('');
const requiresContext = ref(false), confirmed = ref(false), authMode = ref('none');
const loginPath = ref('/api/v1/user/password_login'), headerTemplate = ref('{token}');
const usernameRef = ref('env:PYTA_SECRET_USER'), passwordRef = ref('env:PYTA_SECRET_PASSWORD');
const roleDescription = ref(''), targetIds = ref<string[]>([]);
const targetId = ref(''), identityId = ref(''), tenantId = ref(''), projectId = ref('');
const advanced = ref('{}');
const requestMode = ref('json'), passwordTransform = ref('none'), tokenPath = ref('data.token'), userAgent = ref('');
const scopePath = ref(''), tenantPath = ref(''), projectPath = ref(''), scopeConfirmed = ref(false);
const targets = ref<RecordData[]>([]), identities = ref<RecordData[]>([]), bindings = ref<RecordData[]>([]);
const preEnvironment = ref(''), preTarget = ref(''), preIdentity = ref(''), preBinding = ref('');
const executeLogin = ref(false), preResult = ref('');
const text = (value: unknown) => typeof value === 'string' ? value : '';
const asRecord = (value: unknown): RecordData => typeof value === 'object' && value !== null && !Array.isArray(value) ? value as RecordData : {};

function select(item: RecordData) {
  selected.value = item;
  name.value = text(item.name);
  environmentId.value = text(item.environment_id) || '';
  baseUrl.value = text(item.base_url);
  requiresContext.value = item.requires_context === true;
  const auth = asRecord(item.auth);
  authMode.value = text(auth.mode) || 'none';
  requestMode.value = text(auth.request_mode) || 'json'; passwordTransform.value = text(auth.password_transform) || 'none'; tokenPath.value = text(auth.token_path) || 'data.token';
  userAgent.value = text(asRecord(item.request_headers)['User-Agent']);
  const scope = asRecord(Array.isArray(item.checks) ? item.checks.find(row => asRecord(row).name === 'scope') : null);
  scopePath.value = text(scope.path); tenantPath.value = text(scope.tenant_path); projectPath.value = text(scope.project_path); scopeConfirmed.value = scope.query_contract_confirmed === true;
  confirmed.value = auth.contract_confirmed === true;
  loginPath.value = text(auth.login_path) || '/api/v1/user/password_login';
  headerTemplate.value = text(auth.header_template) || '{token}';
  targetIds.value = Array.isArray(item.target_ids) ? item.target_ids.map(String) : [];
  usernameRef.value = text(item.username_secret_ref) || 'env:PYTA_SECRET_USER';
  passwordRef.value = text(item.password_secret_ref) || 'env:PYTA_SECRET_PASSWORD';
  roleDescription.value = text(item.role_description);
  targetId.value = text(item.target_id); identityId.value = text(item.identity_id);
  tenantId.value = text(item.tenant_id); projectId.value = text(item.project_id);
  advanced.value = JSON.stringify(item, null, 2);
  if (kind.value === 'targets') { preTarget.value = text(item.id); preEnvironment.value = environmentId.value; }
  if (kind.value === 'context-bindings') { preTarget.value = targetId.value; preBinding.value = text(item.id); preIdentity.value = identityId.value; }
}
function newProfile() { select({}); selected.value = null; }
async function load() {
  busy.value = true; error.value = '';
  try {
    const data = await Promise.all([apiClient.get<RecordData[]>(`/${kind.value}`), apiClient.get<RecordData[]>('/targets'), apiClient.get<RecordData[]>('/identity-profiles'), apiClient.get<RecordData[]>('/context-bindings')]);
    [profiles.value, targets.value, identities.value, bindings.value] = data;
    environments.value = await managementApi.listEnvironments();
    newProfile();
  } catch (cause) { error.value = resolveApiErrorMessage(cause, '公开配置读取失败'); }
  finally { busy.value = false; }
}
async function save() {
  busy.value = true; error.value = ''; message.value = '';
  try {
    const extra = asRecord(JSON.parse(advanced.value));
    const payload: RecordData = { ...extra, name: name.value };
    if (selected.value) { payload.id = selected.value.id; payload.revision = selected.value.revision; }
    else { delete payload.id; payload.revision = 1; }
    if (kind.value === 'targets') Object.assign(payload, {
      environment_id: environmentId.value, base_url: baseUrl.value, requires_context: requiresContext.value,
      auth: { ...asRecord(extra.auth), mode: authMode.value, login_path: loginPath.value,
        header_template: headerTemplate.value, contract_confirmed: confirmed.value,
        request_mode: requestMode.value, password_transform: passwordTransform.value, token_path: tokenPath.value },
      request_headers: { ...Object.fromEntries(Object.entries(asRecord(extra.request_headers)).filter(([key]) => key.toLowerCase() !== 'user-agent')), ...(userAgent.value ? {'User-Agent': userAgent.value} : {}) },
      checks: [...(Array.isArray(extra.checks) ? extra.checks.filter(row => asRecord(row).name !== 'scope') : []), ...(scopePath.value ? [{name: 'scope', path: scopePath.value, method: 'GET', query_contract_confirmed: scopeConfirmed.value, tenant_path: tenantPath.value || null, project_path: projectPath.value || null}] : [])],
    });
    if (kind.value === 'identity-profiles') Object.assign(payload, {
      target_ids: targetIds.value,
      username_secret_ref: usernameRef.value, password_secret_ref: passwordRef.value,
      role_description: roleDescription.value,
    });
    if (kind.value === 'context-bindings') Object.assign(payload, {
      target_id: targetId.value, identity_id: identityId.value, tenant_id: tenantId.value, project_id: projectId.value,
    });
    const response = selected.value
      ? await apiClient.patch<RecordData>(`/${kind.value}/${selected.value.id}`, payload)
      : await apiClient.post<RecordData>(`/${kind.value}`, payload);
    await load(); select(response); message.value = '已保存公开配置；秘密值不会回显。';
  } catch (cause) { error.value = resolveApiErrorMessage(cause, '保存失败，请检查引用和版本'); }
  finally { busy.value = false; }
}
async function remove() {
  if (!selected.value) return;
  busy.value = true; error.value = '';
  try {
    await apiClient.request(`/${kind.value}/${selected.value.id}`, { method: 'DELETE', query: { revision: Number(selected.value.revision) } });
    await load();
  } catch (cause) { error.value = resolveApiErrorMessage(cause, '删除失败，配置可能仍被引用'); }
  finally { busy.value = false; }
}
async function preflight() {
  busy.value = true; error.value = ''; preResult.value = '';
  try {
    const result = await apiClient.post(`/environments/${preEnvironment.value}/preflight`, {
      target_id: preTarget.value, identity_id: preIdentity.value || null,
      context_binding_id: preBinding.value || null, execute_login: executeLogin.value,
    });
    preResult.value = JSON.stringify(result, null, 2);
  } catch (cause) { error.value = resolveApiErrorMessage(cause, '预检失败'); }
  finally { busy.value = false; }
}
onMounted(() => { void load(); });
</script>

<style scoped>
.context-panel { padding: 1.5rem; background: var(--color-surface, #fff); border-radius: 1rem; }
.profiles-grid { display: grid; grid-template-columns: minmax(10rem, 1fr) minmax(16rem, 2fr); gap: 1rem; }
form { display: grid; gap: .6rem; }
label { display: grid; gap: .25rem; }
input, select, textarea { max-width: 100%; padding: .5rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 700px) { .profiles-grid { grid-template-columns: 1fr; } }
.profiles-grid { margin-top: 18px; gap: 24px; }
.profiles-grid > ul { margin: 0; padding: 8px; list-style: none; background: #f8fafc; border: 1px solid var(--color-border); border-radius: 8px; align-self: start; }
.profiles-grid li { margin: 0 0 6px; }
.profiles-grid li button { width: 100%; justify-content: flex-start; text-align: left; overflow-wrap: anywhere; }
.profiles-grid form { gap: 14px; }
input, select, textarea { padding: 9px 11px; }
</style>
