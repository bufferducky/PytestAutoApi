<template>
  <section class="page-grid">
    <details><summary aria-label="目标系统、身份与项目绑定">目标系统、身份与项目绑定<HelpHint topic="profileKind" /></summary><ContextProfilesPanel /></details>
    <div class="content-grid">
      <PlaceholderPanel
        title="环境目录"
        description="配置基础地址与环境变量，供场景和套件运行使用。"
      >
        <template #actions>
          <div class="action-row">
            <button
              class="action-button action-button--secondary"
              type="button"
              :disabled="saving || deleting || detailLoading"
              @click="startCreateMode()"
            >
              新增环境
            </button>
            <button class="action-button" type="button" :disabled="loading" @click="loadEnvironments()">
              {{ loading ? '加载中...' : '重新加载' }}
            </button>
          </div>
        </template>

        <p v-if="note" class="state-banner state-banner--info" role="status">{{ note }}</p>
        <p v-if="errorMessage" class="state-banner state-banner--error" role="alert">{{ errorMessage }}</p>
        <p v-if="environments.length" class="panel-tip">选择一条环境配置进行编辑。</p>

        <div v-if="loading && !environments.length" class="empty-copy">正在加载环境配置...</div>

        <div v-else-if="!loading && !environments.length" class="empty-copy">
          暂无环境，请填写表单创建第一个执行环境。
        </div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>环境</th>
                <th aria-label="Base URL">Base URL<HelpHint topic="baseUrl" /></th>
                <th aria-label="鉴权方式">鉴权方式<HelpHint topic="authMode" /></th>
                <th aria-label="状态">状态<HelpHint topic="environmentStatus" /></th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in environments"
                :key="item.id"
                class="environment-row"
                :class="{ 'environment-row--selected': item.id === selectedEnvironmentId }"
                tabindex="0"
                role="button"
                :aria-selected="item.id === selectedEnvironmentId"
                @click="startEditMode(item.id)"
                @keydown.enter.prevent="startEditMode(item.id)"
                @keydown.space.prevent="startEditMode(item.id)"
              >
                <td>
                  <div class="environment-name-row">
                    <span class="environment-name">{{ item.name }}</span>
                    <span v-if="item.id === selectedEnvironmentId" class="environment-current">当前编辑</span>
                  </div>
                </td>
                <td>{{ item.baseUrl }}</td>
                <td>{{ item.authMode }}</td>
                <td>
                  <StatusTag
                    :label="environmentStatusLabelMap[item.status]"
                    :tone="item.status === 'online' ? 'success' : 'warning'"
                  />
                </td>
                <td>
                  <button
                    class="action-link"
                    type="button"
                    :disabled="detailLoading && item.id === selectedEnvironmentId"
                    @click.stop="startEditMode(item.id)"
                  >
                    编辑
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PlaceholderPanel>

      <PlaceholderPanel
        :title="formPanelTitle"
        :description="formPanelDescription"
      >
        <p v-if="detailLoading" class="empty-copy">正在加载环境详情...</p>

        <form class="environment-form" @submit.prevent="submitEnvironment">
          <fieldset :disabled="saving || deleting || detailLoading" class="editor-fields">
          <section v-if="formMode === 'edit' && currentEnvironmentDetail" class="environment-hero">
            <div class="environment-hero__header">
              <div>
                <p class="environment-hero__eyebrow">当前编辑</p>
                <h3 class="environment-hero__title">{{ currentEnvironmentDetail.name }}</h3>
              </div>
              <StatusTag
                :label="environmentStatusLabelMap[currentEnvironmentDetail.status]"
                :tone="currentEnvironmentDetail.status === 'online' ? 'success' : 'warning'"
              />
            </div>

            <div class="detail-pill-row">
              <span class="detail-pill">ID：{{ currentEnvironmentDetail.id }}</span>
              <span class="detail-pill">
                变量数：{{ Object.keys(currentEnvironmentDetail.variables).length }}
              </span>
              <span class="detail-pill">Base URL：{{ currentEnvironmentDetail.baseUrl }}</span>
            </div>


          </section>

          <div class="form-grid">
            <label class="field-stack">
              <span>环境名称</span>
              <input
                v-model.trim="formState.name"
                type="text"
                maxlength="32"
                placeholder="例如：预发联调环境"
                required
              />
            </label>

            <label class="field-stack"><span class="field-caption"><span>Base URL</span><HelpHint topic="baseUrl" /></span><input
                v-model.trim="formState.baseUrl"
                type="url"
                placeholder="https://staging.example.com"
                required
              aria-label="Base URL" />
            </label>

            <label class="field-stack"><span class="field-caption"><span>鉴权方式</span><HelpHint topic="authMode" /></span><select v-model="formState.authMode" aria-label="鉴权方式">
                <option v-for="item in authModeOptions" :key="item" :value="item">
                  {{ item }}
                </option>
              </select>
            </label>

            <label class="field-stack"><span class="field-caption"><span>状态</span><HelpHint topic="environmentStatus" /></span><select v-model="formState.status" aria-label="状态">
                <option value="draft">待配置</option>
                <option value="online">可用</option>
              </select>
            </label>
          </div>

          <EnvironmentVariablesEditor v-model="variablesText" @validity="variablesValid = $event" />
          <p v-if="dirty" role="status">有未保存修改</p>
          <div class="form-actions">
            <button class="action-button" type="submit" :disabled="saving || deleting || detailLoading || !variablesValid">
              {{ primaryActionLabel }}
            </button>
            <button
              v-if="formMode === 'edit'"
              class="action-button action-button--secondary"
              type="button"
              :disabled="saving || deleting || detailLoading"
              @click="startCreateMode()"
            >
              取消编辑
            </button>
            <button
              v-if="formMode === 'edit'"
              class="action-button action-button--danger"
              type="button"
              :disabled="deleting || saving || detailLoading"
              @click="removeEnvironment"
            >
              {{ deleting ? '删除中...' : '删除环境' }}
            </button>
            <p class="form-tip">{{ formTip }}</p>
          </div>
          </fieldset>
        </form>


      </PlaceholderPanel>
    </div>
  </section>
</template>

<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import ContextProfilesPanel from '@/components/ContextProfilesPanel.vue';
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import EnvironmentVariablesEditor from '@/components/EnvironmentVariablesEditor.vue';
import { apiClient } from '@/api/client';

import { managementApi } from '@/api';
import PlaceholderPanel from '@/components/common/PlaceholderPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import type {
  CreateEnvironmentPayload,
  EnvironmentDetail,
  EnvironmentSummary,
  UpdateEnvironmentPayload,
} from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

type EnvironmentFormMode = 'create' | 'edit';

// 环境页先把“平台主真源里的环境资源”做实。
// 真执行接入时，run/schedule 都应该引用这里的环境，而不是继续拼散落配置。
const environments = ref<EnvironmentSummary[]>([]);
const loading = ref(false);
const detailLoading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const note = ref('');
const errorMessage = ref('');
const formMode = ref<EnvironmentFormMode>('create');
const selectedEnvironmentId = ref('');
const currentEnvironmentDetail = ref<EnvironmentDetail | null>(null);

const environmentStatusLabelMap = {
  online: '可用',
  draft: '待配置',
} as const;

const authModeOptions = [
  '账号密码登录 + Token 注入',
  'Cookie + 单点登录',
  '自定义签名插件',
] as const;

const formState = ref<CreateEnvironmentPayload>({
  name: '',
  baseUrl: '',
  authMode: authModeOptions[0],
  status: 'draft',
});

const variablesText = ref('{}'), variablesValid = ref(true);
const snapshot = () => JSON.stringify([formState.value, variablesText.value]);
const savedSnapshot = ref(snapshot());
const dirty = computed(() => snapshot() !== savedSnapshot.value || !variablesValid.value);
const mayDiscard = () => !dirty.value || window.confirm('有未保存修改，确认放弃？');
let detailSequence = 0, listSequence = 0;
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = ''; } };
onBeforeRouteLeave(() => !saving.value && !deleting.value && mayDiscard());
onBeforeUnmount(() => { ++detailSequence; ++listSequence; window.removeEventListener('beforeunload', beforeUnload); });

const resetFormState = () => {
  formState.value = {
    name: '',
    baseUrl: '',
    authMode: authModeOptions[0],
    status: 'draft',
  };
};

const applyFormState = (payload: UpdateEnvironmentPayload) => {
  formState.value = {
    name: payload.name ?? '',
    baseUrl: payload.baseUrl ?? '',
    authMode: payload.authMode ?? authModeOptions[0],
    status: payload.status ?? 'draft',
  };
};

const formPanelTitle = computed(() =>
  formMode.value === 'edit' ? '编辑环境' : '新增环境',
);

const formPanelDescription = computed(() =>
  formMode.value === 'edit'
    ? '保存后更新环境配置，环境变量会按当前类型保存。'
    : '填写名称与基础地址，创建可供测试运行使用的环境。'
);

const primaryActionLabel = computed(() => {
  if (formMode.value === 'edit') {
    return saving.value ? '保存中...' : '保存修改';
  }
  return saving.value ? '保存中...' : '保存环境';
});

const formTip = computed(() =>
  formMode.value === 'edit'
    ? '保存后会刷新左侧目录，并保持当前环境选中。'
    : '保存成功后会自动切到新环境的编辑态，便于继续补充配置。'
);

const resetCreateState = () => {
  ++detailSequence;
  formMode.value = 'create';
  selectedEnvironmentId.value = '';
  currentEnvironmentDetail.value = null;
  detailLoading.value = false;
  resetFormState();
  variablesText.value = '{}'; variablesValid.value = true; savedSnapshot.value = snapshot();
};

const startCreateMode = () => {
  if (saving.value || deleting.value || !mayDiscard()) return;
  resetCreateState();
};

const startEditMode = async (environmentId: string, options?: { silent?: boolean }) => {
  if (saving.value || deleting.value) return;
  if (!options?.silent && environmentId === selectedEnvironmentId.value) return;
  if (!options?.silent && !mayDiscard()) return;
  const sequence = ++detailSequence;
  detailLoading.value = true;
  if (!options?.silent) { note.value = ''; errorMessage.value = ''; }
  try {
    const detail = await managementApi.getEnvironmentDetail(environmentId);
    if (sequence !== detailSequence) return;
    selectedEnvironmentId.value = environmentId; formMode.value = 'edit';
    currentEnvironmentDetail.value = detail; applyFormState(detail);
    variablesText.value = JSON.stringify(detail.variables, null, 2); variablesValid.value = true;
    savedSnapshot.value = snapshot();
  } catch (error) {
    if (sequence === detailSequence) errorMessage.value = resolveApiErrorMessage(error, '环境详情更新失败，保留原有内容。');
  } finally { if (sequence === detailSequence) detailLoading.value = false; }
};

const loadEnvironments = async (_options?: { preferredId?: string; preserveSelection?: boolean }) => {
  const sequence = ++listSequence;
  loading.value = true; errorMessage.value = '';
  try {
    const items = await managementApi.listEnvironments();
    if (sequence !== listSequence) return;
    environments.value = items;
  } catch (error) {
    if (sequence === listSequence) errorMessage.value = resolveApiErrorMessage(error, '环境目录更新失败，保留原有内容。');
  } finally { if (sequence === listSequence) loading.value = false; }
};

const submitEnvironment = async () => {
  if (saving.value || deleting.value || detailLoading.value) return;
  saving.value = true;
  note.value = '';
  errorMessage.value = '';

  try {
    if (!variablesValid.value) throw new Error('请先修正环境变量');
    const variables: unknown = JSON.parse(variablesText.value);
    if (!variables || typeof variables !== 'object' || Array.isArray(variables)) throw new Error('环境变量必须为 JSON 对象');
    const payload = { name: formState.value.name, base_url: formState.value.baseUrl, auth_mode: formState.value.authMode, status: formState.value.status, variables, expected_revision: currentEnvironmentDetail.value?.revision };
    const result = formMode.value === 'edit' && selectedEnvironmentId.value
      ? await apiClient.patch<{id: string}>(`/environments/${selectedEnvironmentId.value}`, payload)
      : await apiClient.post<{id: string}>('/environments', payload);
    selectedEnvironmentId.value = result.id; formMode.value = 'edit';
    savedSnapshot.value = snapshot();
    note.value = '环境已保存。';
    saving.value = false;
    await startEditMode(result.id, { silent: true });
    await loadEnvironments();
  } catch (error) {
    errorMessage.value = resolveApiErrorMessage(error, '保存环境失败，请稍后重试。');
  } finally {
    saving.value = false;
  }
};

const removeEnvironment = async () => {
  if (detailLoading.value || saving.value || deleting.value || !selectedEnvironmentId.value || !currentEnvironmentDetail.value) {
    return;
  }

  const shouldDelete = window.confirm(`确认删除环境「${currentEnvironmentDetail.value.name}」吗？`);
  if (!shouldDelete) {
    return;
  }

  deleting.value = true;
  note.value = '';
  errorMessage.value = '';

  try {
    const deleted = await managementApi.deleteEnvironment(selectedEnvironmentId.value);
    resetCreateState();
    await loadEnvironments();
    note.value = `环境已删除：${deleted.name}。`;
  } catch (error) {
    errorMessage.value = resolveApiErrorMessage(error, '删除环境失败，请稍后重试。');
  } finally {
    deleting.value = false;
  }
};

onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload);
  void loadEnvironments();
});
</script>

<style scoped>
.editor-fields { border:0; padding:0; margin:0; min-width:0; display:grid;gap:1rem; }
.detail-pill { max-width:100%;overflow-wrap:anywhere; }
.action-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.panel-tip {
  margin: 0;
  color: var(--color-ink-subtle);
  line-height: 1.75;
}

.environment-row {
  cursor: pointer;
  transition: background 180ms ease, transform 180ms ease;
}

.environment-row:hover {
  background: rgba(95, 124, 255, 0.05);
}

.environment-row--selected {
  background: rgba(95, 124, 255, 0.08);
}

.environment-name-row {
  display: flex;
  gap: 0.55rem;
  align-items: center;
  flex-wrap: wrap;
}

.environment-name {
  font-weight: 700;
}

.environment-current {
  display: inline-flex;
  align-items: center;
  min-height: 1.45rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
  font-size: 0.78rem;
}

.action-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-accent-strong);
  cursor: pointer;
}

.action-link:disabled {
  opacity: 0.65;
  cursor: wait;
}

.environment-form {
  display: grid;
  gap: 1rem;
}

.environment-hero {
  display: grid;
  gap: 0.85rem;
  padding: 1rem;
  border-radius: 1rem;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.environment-hero__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.environment-hero__eyebrow {
  margin: 0 0 0.35rem;
  color: var(--color-ink-subtle);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.environment-hero__title {
  margin: 0;
  font-size: 1.05rem;
}

.detail-pill-row {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.detail-pill {
  display: inline-flex;
  align-items: center;
  min-height: 1.8rem;
  padding: 0.18rem 0.65rem;
  border-radius: 999px;
  background: rgba(95, 124, 255, 0.1);
  color: var(--color-accent-strong);
  font-size: 0.82rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}

.field-stack {
  display: grid;
  gap: 0.45rem;
  color: var(--color-ink-muted);
  font-size: 0.92rem;
}

.field-stack span {
  font-weight: 600;
  color: var(--color-ink-base);
}

.form-actions {
  display: flex;
  gap: 0.9rem;
  align-items: center;
  flex-wrap: wrap;
}

.form-tip {
  margin: 0;
  color: var(--color-ink-subtle);
  line-height: 1.7;
}

@media (max-width: 720px) {
  .action-row,
  .environment-hero__header,
  .detail-pill-row,
  .form-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
