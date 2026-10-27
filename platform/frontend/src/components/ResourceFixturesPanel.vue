<template>
  <section class="resource-panel">
    <h3>测试数据、专属资源池与媒体</h3>
    <p>创建依赖已确认接口；池中只能登记专属测试对象。过期资源需对账，不能自动重新分配。</p>
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info">{{ message }}</p>
    <el-button native-type="button" :disabled="busy" @click="load">刷新</el-button>
    <el-tabs v-model="resourceTab" aria-label="测试资源分类"><el-tab-pane label="定义版本" name="definitions" /><el-tab-pane label="资源池" name="pool" /><el-tab-pane label="媒体数据" name="media" /></el-tabs>
    <section v-show="resourceTab==='definitions'"><form @submit.prevent="saveFixture">
      <h4 aria-label="新增 fixture 定义版本">新增 fixture 定义版本<HelpHint topic="fixture" /></h4>
      <label><span class="field-caption"><span>已有定义 ID（空则新建）</span><HelpHint topic="fixture" /></span><UiInput v-model="definitionId" aria-label="已有定义 ID（空则新建）"  /></label>
      <label>名称 <UiInput v-model="name" required  /></label>
      <label><span class="field-caption"><span>策略</span><HelpHint topic="strategy" /></span><UiSelect v-model="strategy" aria-label="策略"><option>create</option><option>lease</option><option>read_only</option></UiSelect></label>
      <label><input type="checkbox" v-model="contract" aria-label="已确认创建/查询/恢复契约" /><span class="field-caption">已确认创建/查询/恢复契约<HelpHint topic="contract" /></span></label>
      <label><span class="field-caption"><span>资源池 ID（lease/read_only）</span><HelpHint topic="pool" /></span><UiInput v-model="poolId" aria-label="资源池 ID（lease/read_only）"  /></label>
      <label><span class="field-caption"><span>只读精确对象 ID</span><HelpHint topic="objectId" /></span><UiInput v-model="objectId" aria-label="只读精确对象 ID"  /></label>
      <label><input type="checkbox" v-model="restore" aria-label="借用后必须恢复原关联" /><span class="field-caption">借用后必须恢复原关联<HelpHint topic="restore" /></span></label>
      <label><span class="field-caption"><span>创建请求 JSON</span><HelpHint topic="acquire" /></span><UiInput type="textarea" v-model="acquire" rows="4" aria-label="创建请求 JSON"  /></label>
      <label><span class="field-caption"><span>原值查询 JSON（需恢复时）</span><HelpHint topic="resourceSnapshot" /></span><UiInput type="textarea" v-model="snapshot" rows="4" aria-label="原值查询 JSON（需恢复时）"  /></label>
      <label><span class="field-caption"><span>删除/恢复请求 JSON</span><HelpHint topic="release" /></span><UiInput type="textarea" v-model="release" rows="4" aria-label="删除/恢复请求 JSON"  /></label>
      <el-button :disabled="busy" native-type="submit">保存新版本</el-button>
    </form>
    <p>在场景的迁移/扩展元数据中声明 fixtures：name、definition_id、version、depends_on；在请求中用 fixtures.名称.id。发布检查资源契约与只读限制。</p>
    <JsonResult v-if="definitions.length" :value="definitions" title="定义版本记录" /><el-empty v-else description="暂无资源定义" :image-size="45" />
    </section><section v-show="resourceTab==='pool'"><form @submit.prevent="savePool">
      <h4 aria-label="登记专属池对象">登记专属池对象<HelpHint topic="pool" /></h4>
      <label><span class="field-caption"><span>池 ID</span><HelpHint topic="pool" /></span><UiInput v-model="poolName" required aria-label="池 ID"  /></label>
      <label><span class="field-caption"><span>目标 ID</span><HelpHint topic="target" /></span><UiInput v-model="target" required aria-label="目标 ID"  /></label>
      <label><span class="field-caption"><span>租户 ID</span><HelpHint topic="tenantId" /></span><UiInput v-model="tenant" aria-label="租户 ID"  /></label>
      <label><span class="field-caption"><span>项目 ID</span><HelpHint topic="projectId" /></span><UiInput v-model="project" aria-label="项目 ID"  /></label>
      <label><span class="field-caption"><span>对象 ID</span><HelpHint topic="objectId" /></span><UiInput v-model="poolObject" required aria-label="对象 ID"  /></label>
      <label><input type="checkbox" v-model="dedicated" aria-label="确认为可恢复的专属测试对象" /><span class="field-caption">确认为可恢复的专属测试对象<HelpHint topic="dedicated" /></span></label>
      <el-button :disabled="busy || !dedicated" native-type="submit">登记</el-button>
    </form>
    <div class="table-shell"><table><thead><tr><th>池/对象</th><th aria-label="状态">状态<HelpHint topic="leaseState" /></th><th aria-label="owner / generation">owner / generation<HelpHint topic="leaseState" /></th><th>到期</th></tr></thead><tbody>
      <tr v-for="row in leases" :key="String(row.id)"><td>{{ row.pool_id }} / {{ row.object_id }}</td><td>{{ row.state }}</td><td>{{ row.owner }} / {{ row.generation }}</td><td>{{ row.expires_at }}</td></tr>
    </tbody></table></div>
    </section><section v-show="resourceTab==='media'"><h4>登记合成/脱敏媒体 manifest<HelpHint topic="media" /></h4>
      <p>文件必须位于 Files/test-media，声明 SHA-256、大小、格式、时长、来源授权、语言/噪声及适用场景。这里只校验与登记，不上传或下载客户录音。</p>
      <UiInput type="textarea" v-model="mediaManifest" rows="12" aria-label="媒体manifest"  />
      <el-button native-type="button" :disabled="busy" @click="saveMedia">校验并登记</el-button>
      <JsonResult :value="media" title="媒体登记记录" />
    </section>
  </section>
</template>
<script setup lang="ts">
import JsonResult from '@/components/common/JsonResult.vue';
import HelpHint from '@/components/common/HelpHint.vue';
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

const resourceTab=ref('definitions');
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
