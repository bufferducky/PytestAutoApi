<template>
  <section class="context-panel">
    <h3>目标系统、身份与项目绑定</h3>
    <p>配置只保存公开字段和 env:PYTA_SECRET_* 引用；凭证明文不回显。修改需携带当前 revision。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info">{{ message }}</p>
    <label>配置类型
      <select v-model="kind" @change="load">
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
          <label>环境
            <select v-model="environmentId" required>
              <option v-for="env in environments" :value="env.id" :key="env.id">{{ env.name }}</option>
            </select>
          </label>
          <label>基础地址 <input v-model="baseUrl" type="url" required /></label>
          <label><input v-model="requiresContext" type="checkbox" />要求项目上下文</label>
          <label>认证方式
            <select v-model="authMode"><option value="none">无认证</option><option value="password">密码登录</option></select>
          </label>
          <label>登录路径 <input v-model="loginPath" /></label>
          <label>令牌格式
            <select v-model="headerTemplate"><option value="{token}">原始 Token</option><option value="Bearer {token}">Bearer</option></select>
          </label>
          <label><input v-model="confirmed" type="checkbox" />登录契约已确认</label>
        </template>
        <template v-if="kind === 'identity-profiles'">
          <label>支持的目标 ID（逗号分隔）<input v-model="targetIds" required /></label>
          <label>账号引用 <input v-model="usernameRef" placeholder="env:PYTA_SECRET_USER" required /></label>
          <label>密码引用 <input v-model="passwordRef" placeholder="env:PYTA_SECRET_PASSWORD" required /></label>
          <label>角色说明 <input v-model="roleDescription" /></label>
        </template>
        <template v-if="kind === 'context-bindings'">
          <label>目标 ID <input v-model="targetId" required /></label>
          <label>身份 ID <input v-model="identityId" required /></label>
          <label>租户 ID <input v-model="tenantId" required /></label>
          <label>项目 ID <input v-model="projectId" required /></label>
        </template>
        <details><summary>高级公开配置（结构化 JSON）</summary>
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
      <label>环境 ID <input v-model="preEnvironment" required /></label>
      <label>目标 ID <input v-model="preTarget" required /></label>
      <label>身份 ID <input v-model="preIdentity" /></label>
      <label>项目绑定 ID <input v-model="preBinding" /></label>
      <label><input v-model="executeLogin" type="checkbox" />执行已确认登录与查询（否则只校验配置/引用）</label>
      <button :disabled="busy">预检</button>
    </form>
    <pre v-if="preResult">{{ preResult }}</pre>
  </section>
</template>

<script setup lang="ts">
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
const roleDescription = ref(''), targetIds = ref('');
const targetId = ref(''), identityId = ref(''), tenantId = ref(''), projectId = ref('');
const advanced = ref('{}');
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
  confirmed.value = auth.contract_confirmed === true;
  loginPath.value = text(auth.login_path) || '/api/v1/user/password_login';
  headerTemplate.value = text(auth.header_template) || '{token}';
  targetIds.value = Array.isArray(item.target_ids) ? item.target_ids.join(',') : '';
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
    profiles.value = await apiClient.get<RecordData[]>(`/${kind.value}`);
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
        header_template: headerTemplate.value, contract_confirmed: confirmed.value },
    });
    if (kind.value === 'identity-profiles') Object.assign(payload, {
      target_ids: targetIds.value.split(',').map(v => v.trim()).filter(Boolean),
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
</style>
