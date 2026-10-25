<template>
  <section class="resource-panel">
    <h3>测试数据、专属资源池与媒体</h3>
    <p>创建依赖已确认接口；池中只能登记专属测试对象。过期资源需对账，不能自动重新分配。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info">{{ message }}</p>
    <button type="button" :disabled="busy" @click="load">刷新</button>
    <form @submit.prevent="saveFixture">
      <h4>新增 fixture 定义版本</h4>
      <label>已有定义 ID（空则新建）<input v-model="definitionId" /></label>
      <label>名称 <input v-model="name" required /></label>
      <label>策略 <select v-model="strategy"><option>create</option><option>lease</option><option>read_only</option></select></label>
      <label><input type="checkbox" v-model="contract" />已确认创建/查询/恢复契约</label>
      <label>资源池 ID（lease/read_only）<input v-model="poolId" /></label>
      <label>只读精确对象 ID <input v-model="objectId" /></label>
      <label><input type="checkbox" v-model="restore" />借用后必须恢复原关联</label>
      <label>创建请求 JSON <textarea v-model="acquire" rows="4" /></label>
      <label>原值查询 JSON（需恢复时）<textarea v-model="snapshot" rows="4" /></label>
      <label>删除/恢复请求 JSON <textarea v-model="release" rows="4" /></label>
      <button :disabled="busy">保存新版本</button>
    </form>
    <p>在场景的迁移/扩展元数据中声明 fixtures：name、definition_id、version、depends_on；在请求中用 fixtures.名称.id。发布检查资源契约与只读限制。</p>
    <pre>{{ JSON.stringify(definitions, null, 2) }}</pre>
    <form @submit.prevent="savePool">
      <h4>登记专属池对象</h4>
      <label>池 ID <input v-model="poolName" required /></label>
      <label>目标 ID <input v-model="target" required /></label>
      <label>租户 ID <input v-model="tenant" /></label>
      <label>项目 ID <input v-model="project" /></label>
      <label>对象 ID <input v-model="poolObject" required /></label>
      <label><input type="checkbox" v-model="dedicated" />确认为可恢复的专属测试对象</label>
      <button :disabled="busy || !dedicated">登记</button>
    </form>
    <div class="table-shell"><table><thead><tr><th>池/对象</th><th>状态</th><th>owner / generation</th><th>到期</th></tr></thead><tbody>
      <tr v-for="row in leases" :key="String(row.id)"><td>{{ row.pool_id }} / {{ row.object_id }}</td><td>{{ row.state }}</td><td>{{ row.owner }} / {{ row.generation }}</td><td>{{ row.expires_at }}</td></tr>
    </tbody></table></div>
    <details><summary>登记合成/脱敏媒体 manifest</summary>
      <p>文件必须位于 Files/test-media，声明 SHA-256、大小、格式、时长、来源授权、语言/噪声及适用场景。这里只校验与登记，不上传或下载客户录音。</p>
      <textarea v-model="mediaManifest" rows="12" aria-label="媒体manifest" />
      <button type="button" :disabled="busy" @click="saveMedia">校验并登记</button>
      <pre>{{ JSON.stringify(media, null, 2) }}</pre>
    </details>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

const busy = ref(false), error = ref(''), message = ref('');
const definitions = ref<unknown[]>([]), leases = ref<Record<string, unknown>[]>([]), media = ref<unknown[]>([]);
const definitionId = ref(''), name = ref(''), strategy = ref('create'), contract = ref(false), poolId = ref(''), objectId = ref(''), restore = ref(true);
const acquire = ref('null');
const snapshot = ref('null'), release = ref('null');
const poolName = ref(''), target = ref(''), tenant = ref(''), project = ref(''), poolObject = ref(''), dedicated = ref(false);
const mediaManifest = ref('{}');
async function action(operation: () => Promise<void>) { busy.value = true; error.value = ''; message.value = '';
  try { await operation(); } catch(cause) { error.value = resolveApiErrorMessage(cause, '资源操作失败'); } finally { busy.value = false; } }
async function load() {  await action(async () => {
  [definitions.value, leases.value, media.value] = await Promise.all([
    apiClient.get<unknown[]>('/fixture-definitions'), apiClient.get<Record<string, unknown>[]>('/resource-leases'), apiClient.get<unknown[]>('/media-datasets')]);
}); }
async function saveFixture() { await action(async () => {
  const saved = await apiClient.post('/fixture-definitions', { ...(definitionId.value ? {id:definitionId.value}:{}), name:name.value,
    strategy:strategy.value, contract_confirmed:contract.value, pool_id:poolId.value || null, object_id:objectId.value || null,
    restore_required:restore.value, acquire_request:JSON.parse(acquire.value), snapshot_request:JSON.parse(snapshot.value), release_request:JSON.parse(release.value) });
  await load(); message.value = `已保存不可变定义：${JSON.stringify(saved)}`;
}); }
async function savePool() { await action(async () => { await apiClient.post('/resource-pool', { pool_id:poolName.value, object_id:poolObject.value,
  target_id:target.value, tenant_id:tenant.value, project_id:project.value, dedicated_test_resource:dedicated.value }); await load(); }); }
async function saveMedia() { await action(async () => { await apiClient.post('/media-datasets', JSON.parse(mediaManifest.value)); await load(); }); }
onMounted(() => { void load(); });
</script>
<style scoped>
.resource-panel { padding: 1.5rem; border-radius: 1rem; background: var(--color-surface, white); }
form,label { display: grid; gap: .4rem; margin-block: .5rem; } input,select,textarea { max-width:100%; padding:.4rem; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:20rem; overflow:auto; }
</style>
