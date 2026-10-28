<template>
  <section class="page-grid" :aria-busy="loading">
    <div class="section-heading">
      <div class="toolbar quick-actions" aria-label="快捷执行入口">
        <RouterLink class="action-button" to="/cases">编写与调试</RouterLink>
        <RouterLink class="action-button action-button--secondary" to="/suites">执行固定版本套件</RouterLink>
        <RouterLink class="action-button action-button--secondary" to="/runs">查看执行结果</RouterLink>
      </div>
      <div class="toolbar"><small v-if="loadedAt">更新于 {{ loadedAt }}</small><el-button :disabled="loading" @click="reload" native-type="submit">{{ loading ? '更新中…' : '刷新' }}</el-button></div>
    </div>
    <p v-if="error" role="alert" class="state-banner state-banner--error">{{ error }} 已加载内容继续保留。</p>
    <div v-if="overview.metrics.length" class="metrics-grid"><MetricCard v-for="metric in overview.metrics" :key="metric.key" :metric="metric" /></div>
    <div class="workbench-grid">
      <ContentPanel :title="recentAssets.length ? '最近资产' : '资产目录'" :description="recentAssets.length ? '本机最近打开或保存的场景与套件。' : '尚无本机访问记录，按名称展示已保存资产。'">
        <div v-if="visibleAssets.length" class="work-list">
          <RouterLink v-for="asset in visibleAssets" :key="asset.id" class="work-row" :to="{ path: asset.kind === 'scenarios' ? '/cases' : '/suites', query: { assetId: asset.id } }">
            <span class="work-row__body"><strong>{{ asset.draft.name }}</strong><small>{{ asset.kind === 'scenarios' ? '场景' : '套件' }} · 草稿 r{{ asset.revision }}</small></span><span aria-hidden="true">→</span>
          </RouterLink>
        </div>
        <p v-else class="empty-copy">{{ loading ? '正在加载资产…' : '还没有资产。创建场景，保存后即可继续编辑。' }}</p>
      </ContentPanel>
      <ContentPanel title="失败待处理" description="最近失败与异常，独立于最近运行列表查询。点击查看诊断。">
        <div v-if="failedRuns.length" class="work-list">
          <RouterLink v-for="run in failedRuns" :key="run.id" class="work-row" :to="{ path: '/runs', query: { runId: run.id } }">
            <span class="work-row__body"><strong :title="run.name">{{ run.name }}</strong><small>{{ run.runNumber ? `#${run.runNumber} · ` : '' }}{{ run.errorSummary || run.note || run.startedAt }}</small></span><StatusTag :label="runLabel(run)" :tone="getRunStatusMeta(run.status).tone" />
          </RouterLink>
        </div>
        <p v-else class="empty-copy">{{ loading ? '正在检查运行…' : '暂无失败与异常记录。' }}</p>
      </ContentPanel>
    </div>
    <ContentPanel title="最近运行" description="保留历史结果标识，点击进入执行详情。">
      <div v-if="overview.recentRuns.length" class="work-list">
        <RouterLink v-for="run in overview.recentRuns.slice(0, 6)" :key="run.id" class="work-row" :to="{ path: '/runs', query: { runId: run.id } }">
          <span class="work-row__body"><strong :title="run.name">{{ run.name }}</strong><small>{{ run.runNumber ? `#${run.runNumber} · ` : '' }}{{ run.startedAt }} · {{ run.duration }}</small></span>
          <StatusTag :label="runLabel(run)" :tone="getRunStatusMeta(run.status).tone" />
        </RouterLink>
      </div>
      <p v-else class="empty-copy">{{ loading ? '正在加载运行…' : '暂无运行记录。可先调试草稿，或发布固定版本后正式执行。' }}</p>
    </ContentPanel>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { dashboardApi } from '@/api/modules/dashboard';
import { apiClient } from '@/api/client';
import { normalizeRunSummary } from '@/api/adapters/runs';
import MetricCard from '@/components/common/MetricCard.vue';
import ContentPanel from '@/components/common/ContentPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import { useAppStore } from '@/stores/app';
import type { DashboardOverview, RunSummary } from '@/types/platform';
import { getRunStatusMeta } from '@/utils/runStatus';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
interface Asset { id: string; revision: number; draft: { name: string }; kind: 'scenarios' | 'suites' }
const appStore = useAppStore();
const assets = ref<Asset[]>([]);
const overview = ref<DashboardOverview>({ metrics: [], focusItems: [], recentRuns: [] });
const loading = ref(false);
const loadedAt = ref('');
const error = ref('');
const recentAssets = computed(() => appStore.recentAssetIds.flatMap((id) => assets.value.filter((asset) => asset.id === id)));
const visibleAssets = computed(() => (recentAssets.value.length ? recentAssets.value : [...assets.value].sort((a, b) => a.draft.name.localeCompare(b.draft.name))).slice(0, 6));
const failedRuns = ref<RunSummary[]>([]);
const runLabel = (run: RunSummary) => {
  const prefix = run.validationScope === 'debug' || run.businessScope === 'draft_debug' ? '草稿调试 · '
    : run.validationScope === 'historical_demo' ? '演示历史 · ' : run.transportMode === 'mock' ? '模拟历史 · ' : '';
  return prefix + getRunStatusMeta(run.status).label;
};
async function reload() {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  // 各区域独立更新；某个请求失败不会擦除另一块的历史数据。
  const results = await Promise.allSettled([
    dashboardApi.getOverview().then((result) => { overview.value = result.data; }),
    // 不能只过滤首页最近三条：后续成功运行不应把已有失败入口挤掉。
    Promise.all(['failed', 'error', 'blocked', 'timed_out', 'interrupted'].map(status =>
      apiClient.get<{ items: Record<string, unknown>[] }>('/runs', { status, limit: 6 }),
    )).then(groups => {
      failedRuns.value = groups.flatMap(group => group.items)
        .sort((a, b) => Date.parse(String(b.created_at)) - Date.parse(String(a.created_at)))
        .slice(0, 6).map(normalizeRunSummary);
    }),
    Promise.all([apiClient.get<Omit<Asset, 'kind'>[]>('/scenarios'), apiClient.get<Omit<Asset, 'kind'>[]>('/suite-assets')]).then(([scenarios, suites]) => {
      assets.value = [...scenarios.map((asset) => ({ ...asset, kind: 'scenarios' as const })), ...suites.map((asset) => ({ ...asset, kind: 'suites' as const }))];
    }),
  ]);
  const failure = results.find((result) => result.status === 'rejected');
  if (failure?.status === 'rejected') error.value = resolveApiErrorMessage(failure.reason, '工作台更新失败。');
  else loadedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  loading.value = false;
}
onMounted(() => { void reload(); });
</script>
<style scoped>
.quick-actions a { text-decoration: none; display: inline-flex; align-items: center; }
small { color: var(--color-ink-subtle); font-size: 11px; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.workbench-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.workbench-grid > *, .metrics-grid > * { min-width: 0; }
.work-list { display: grid; }
.work-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px 2px; border-bottom: 1px solid var(--color-border); text-decoration: none; color: var(--color-ink-base); transition: background 140ms; }
.work-row:hover { background: var(--color-bg-secondary); }
.work-row:last-child { border-bottom: 0; }
.work-row__body { flex: 1 1 160px; min-width: 0; overflow-wrap: anywhere; }
.work-row strong { display: block; font-size: 13px; font-weight: 600; }
.work-row small { display: block; margin-top: 3px; }
@media (max-width: 760px) { .workbench-grid { grid-template-columns: minmax(0, 1fr); } .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 360px) { .metrics-grid { grid-template-columns: minmax(0, 1fr); } }
</style>

<style scoped>
.work-row__body strong { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; overflow-wrap:anywhere; }
</style>
