<template>
  <section class="page-grid runs-page">
    <div class="run-pagination"><span>{{ sourceLabel }} · {{ lastLoadedAt || '等待更新' }}</span><span v-if="loading">正在更新…</span></div>
    <div class="content-grid">
      <ContentPanel
        title="最近运行列表"
        description="筛选运行记录，选择一条查看详情与失败诊断。"
      >
        <template #actions>
          <button class="action-button" type="button" :disabled="loading" @click="reloadRuns">
            {{ loading ? '加载中...' : '重新加载' }}
          </button>
        </template>

        <details class="run-filter-panel"><summary aria-label="筛选运行记录 环境 / 构建 / 状态 / 时间范围">筛选运行记录 <span>环境 / 构建 / 状态 / 时间范围</span><HelpHint topic="runStatus" /></summary>
        <form class="run-filters" @submit.prevent="applyFilters">
          <label><span class="field-caption"><span>环境</span><HelpHint topic="filterEnvironment" /></span><select v-model="serverFilters.environment_id" aria-label="环境"><option value="">全部环境</option><option v-for="item in environments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>目标</span><HelpHint topic="filterTarget" /></span><select v-model="serverFilters.target_id" aria-label="目标"><option value="">全部目标</option><option v-for="item in targets" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>被测构建</span><HelpHint topic="filterBuild" /></span><input v-model="serverFilters.build" aria-label="被测构建" /></label>
          <label><span class="field-caption"><span>历史模式筛选</span><HelpHint topic="transport" /></span><select v-model="serverFilters.transport_mode" aria-label="历史模式筛选"><option value="">全部（统计分开）</option><option value="live">真实</option><option value="mock">模拟</option></select></label>
          <label><span class="field-caption"><span>场景</span><HelpHint topic="filterScenario" /></span><select v-model="serverFilters.scenario_id" aria-label="场景"><option value="">全部场景</option><option v-for="item in scenarios" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>发布版本</span><HelpHint topic="filterVersion" /></span><select v-model="serverFilters.scenario_version" :disabled="!serverFilters.scenario_id || versionsLoading" aria-label="发布版本"><option value="">{{ versionsLoading ? '正在加载版本…' : serverFilters.scenario_id ? '全部发布版本' : '请先选择场景' }}</option><option v-for="item in scenarioVersions" :key="item.version" :value="String(item.version)">v{{ item.version }}{{ item.change_note ? ' · ' + item.change_note : '' }}</option></select></label>
          <label><span class="field-caption"><span>终态</span><HelpHint topic="runStatus" /></span><select v-model="serverFilters.status" aria-label="终态"><option value="">全部</option><option v-for="state in ['queued','running','succeeded','failed','error','blocked','skipped','cancelled','timed_out','interrupted']" :key="state" :value="state">{{ getRunStatusMeta(normalizeRunStatus(state)).label }}</option></select></label>
          <label><span class="field-caption"><span>错误类型</span><HelpHint topic="errorCategory" /></span><select v-model="serverFilters.category" aria-label="错误类型"><option value="">全部</option><option v-for="(label,kind) in errorCategoryLabels" :key="kind" :value="kind">{{ label }}</option></select></label>
          <label><span class="field-caption"><span>开始时间（本地时区）</span><HelpHint topic="isoTime" /></span><input v-model="serverFilters.since" type="datetime-local" aria-label="开始时间（本地时区）" /></label>
          <label><span class="field-caption"><span>结束时间（本地时区）</span><HelpHint topic="isoTime" /></span><input v-model="serverFilters.until" type="datetime-local" aria-label="结束时间（本地时区）" /></label>
          <button :disabled="loading">按真实条件筛选</button>
        </form></details>
        <div class="run-pagination"><p>共 {{ totalRuns }} 条；当前第 {{ Math.floor(pageOffset / 20) + 1 }} 页</p>
        <button type="button" :disabled="loading || pageOffset === 0" @click="pageOffset -= 20; reloadRuns()">上一页</button>
        <button type="button" :disabled="loading || pageOffset + 20 >= totalRuns" @click="pageOffset += 20; reloadRuns()">下一页</button>
        <span class="action-help"><button type="button" @click="loadTrends" :disabled="!serverFilters.environment_id || !serverFilters.transport_mode || !serverFilters.scenario_id || !serverFilters.scenario_version">查看固定维度趋势</button><HelpHint topic="trend" /></span></div>
        <pre v-if="trendResult">{{ trendResult }}</pre>
        <p v-if="actionMessage" class="state-banner state-banner--info">{{ actionMessage }}</p>
        <p v-if="note" class="state-banner state-banner--info">{{ note }}</p>
        <p v-if="errorMessage" class="state-banner state-banner--error">{{ errorMessage }}</p>
        <p v-if="runs.length" class="panel-tip">选择运行记录查看详情，支持键盘 Enter 或空格。</p>

        <div v-if="loading && !runs.length" class="empty-copy">正在加载运行记录...</div>

        <div v-else-if="!loading && !runs.length" class="empty-copy">
          没有匹配的运行记录，请调整筛选条件或提交一次测试。
        </div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>运行名称</th>
                <th>目标</th>
                <th>环境</th>
                <th>触发人</th>
                <th>开始时间</th>
                <th aria-label="耗时">耗时<HelpHint topic="elapsed" /></th>
                <th aria-label="模式">模式<HelpHint topic="transport" /></th>
                <th aria-label="业务范围">业务范围<HelpHint topic="evidence" /></th>
                <th aria-label="状态">状态<HelpHint topic="runStatus" /></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in runs"
                :key="item.id"
                class="run-row"
                :class="{ 'run-row--selected': item.id === selectedRunId }"
                tabindex="0"
                role="button"
                :aria-selected="item.id === selectedRunId"
                @click="selectRun(item.id)"
                @keydown.enter.prevent="selectRun(item.id)"
                @keydown.space.prevent="selectRun(item.id)"
              >
                <td>
                  <div class="run-name-row">
                    <div class="run-name">{{ item.name }}</div>
                    <span v-if="item.id === selectedRunId" class="run-current">当前查看</span>
                  </div>
                  <div v-if="item.rawStatus" class="run-subtle">
                    原始状态：{{ item.rawStatus }}
                  </div>
                </td>
                <td>{{ item.target }}</td>
                <td>{{ item.environmentLabel || '未绑定' }}</td>
                <td>{{ item.starter }}</td>
                <td>{{ item.startedAt }}</td>
                <td>{{ item.duration }}</td>
                <td>{{ isDebugRun(item) ? '草稿调试' : item.validationScope === 'historical_demo' ? '迁入演示历史' : item.transportMode === 'live' ? '真实测试' : item.transportMode === 'mock' ? 'Mock（模拟）' : '历史未记录' }}</td>
                <td>{{ isDebugRun(item) ? '草稿调试（不计正式回归）' : item.businessScope === 'yanji_query' ? '言迹查询 smoke' : item.businessScope === 'yanji_web' ? '言迹测试 Web（范围见步骤）' : item.businessScope === 'historical_demo' ? '演示历史' : '未分类（不表示言迹覆盖）' }}</td>
                <td>
                  <StatusTag
                    :label="runStatusLabel(item)"
                    :tone="getRunStatusMeta(item.status).tone"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </ContentPanel>

      <ContentPanel
        title="运行详情"
        description="查看执行上下文、步骤结果与诊断证据。"
      >
        <template #actions>
          <div class="action-row">
            <button
              class="action-button action-button--secondary"
              type="button"
              :disabled="detailLoading || !selectedRunId"
              @click="reloadSelectedRunDetail"
            >
              {{ detailLoading ? '加载中...' : '刷新详情' }}
            </button>
            <span class="action-help"><button
              class="action-button"
              type="button"
              :disabled="rerunLoading || !canRerunSelected"
              @click="rerunSelectedRun"
            >
              {{ rerunLoading ? '复跑中...' : '快速复跑' }}
            </button><HelpHint topic="rerun" /></span>
          </div>
        </template>

        <p v-if="detailErrorMessage" role="alert" class="state-banner state-banner--error">{{ detailErrorMessage }}（已有结果保留，可能不是最新）</p>
        <div v-if="selectedRun" class="detail-stack">
          <header class="detail-hero__header"><h3>{{ selectedRun.name }}</h3><StatusTag :label="runStatusLabel(selectedRun)" :tone="getRunStatusMeta(selectedRun.status).tone" /></header>
          <p v-if="isDebugRun(selectedRun)" class="state-banner state-banner--info">草稿调试 · 独立快照，不作为正式回归或发布证据。</p>
          <nav class="action-row" aria-label="结果分组"><button v-for="tab in resultTabs" :key="tab.key" type="button" :aria-pressed="resultTab === tab.key" @click="resultTab = tab.key">{{ tab.label }}</button>
            <button v-if="['queued','running'].includes(selectedRun.status)" type="button" @click="cancelSelected">请求取消</button>
          </nav>
          <section v-show="resultTab === 'overview'" class="detail-section">
            <p>{{ selectedRun.environmentLabel || '未绑定环境' }} · {{ selectedRun.startedAt }} · {{ selectedRun.duration }}</p>
            <p>{{ selectedRunDetail?.statusMessage || selectedRun.errorSummary || selectedRunInsight?.summary }}</p>
            <p>验证范围：{{ selectedRunDetail?.validationScope || '历史未记录' }} · 清理：{{ selectedRunDetail?.cleanupStatus || '未记录' }}</p>
            <p>{{ isDebugRun(selectedRun) ? '调试证据不计正式回归' : selectedRunDetail?.eligibleForRelease ? '当前断言/清理完整，发布仍以固定构建报告为准' : '证据不完整或尚未验证' }}</p>
            <details><summary>运行快照与原始结果</summary><pre>{{ selectedPayloadJson }}</pre><pre>{{ JSON.stringify(selectedRunDetail?.results || [], null, 2) }}</pre></details>
          </section>
          <RunDiagnosticsPanel v-if="selectedRunId && source === 'api'" v-show="resultTab === 'steps'" :key="selectedRunId" :run-id="selectedRunId" />
          <section v-show="resultTab === 'resources'" class="detail-section">
            <h3>测试资源与清理</h3>
            <span class="action-help"><button type="button" @click="resourcePreflight" :disabled="source !== 'api' || selectedRun.transportMode !== 'live'">资源/清理预检</button><HelpHint topic="cleanupPreflight" /></span>
            <span class="action-help" v-if="cleanupToken"><button type="button" @click="retryResourceCleanup">执行本次预检清理</button><HelpHint topic="cleanup" /></span>
            <pre v-if="resourceInfo">{{ resourceInfo }}</pre><p v-else>预检后查看资源与清理计划。</p>
          </section>
        </div>

        <div v-else class="empty-copy">请选择一条运行记录后查看详情。</div>
      </ContentPanel>
    </div>
    <details><summary aria-label="证据保留与回收（高级）">证据保留与回收（高级）<HelpHint topic="retention" /></summary><EvidenceRetentionPanel /></details>
  </section>
</template>

<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import RunDiagnosticsPanel from '@/components/RunDiagnosticsPanel.vue';
import EvidenceRetentionPanel from '@/components/EvidenceRetentionPanel.vue';
import { apiClient } from '@/api/client';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { executionApi, managementApi } from '@/api';
import MetricCard from '@/components/common/MetricCard.vue';
import ContentPanel from '@/components/common/ContentPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import type { ApiDataSource, DashboardMetric, RunDetail, RunSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';
import { getRunStatusInsight, getRunStatusMeta, normalizeRunStatus } from '@/utils/runStatus';

interface RunDetailField {
  key: string;
  label: string;
  value: string;
}

interface RunRemarkBlock {
  key: string;
  title: string;
  body: string;
  tone: 'info' | 'error' | 'neutral';
}

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const route = useRoute();
const router = useRouter();

const runs = ref<RunSummary[]>([]);
const resultTab = ref('steps');
const resultTabs = [{key:'overview',label:'概览'},{key:'steps',label:'步骤证据'},{key:'resources',label:'资源'}];
const isDebugRun = (run: RunSummary) => run.validationScope === 'debug' || run.businessScope === 'draft_debug' || ('payload' in run && isRecord(run.payload) && run.payload.run_purpose === 'debug');
const runStatusLabel = (run:RunSummary) => isDebugRun(run) ? (run.status === 'success' ? '调试断言通过' : `调试 · ${getRunStatusMeta(run.status).label}`) : run.transportMode === 'mock' && run.status === 'success' ? '模拟断言通过' : getRunStatusMeta(run.status).label;
const errorCategoryLabels:Record<string,string> = {config:'配置错误',authentication:'身份认证',context:'执行上下文',data:'测试数据',network:'网络连接',assertion:'断言失败',executor:'执行器',external_service:'外部服务',device:'设备',unknown:'未知错误'};
const targets = ref<{id:string;name:string}[]>([]);
const scenarioVersions = ref<{version:number;change_note?:string}[]>([]);
const versionsLoading = ref(false);
let versionRequestToken = 0;
const environments = ref<{id:string;name:string}[]>([]), scenarios = ref<{id:string;name:string}[]>([]);
async function loadFilterOptions() {
  const results = await Promise.allSettled([managementApi.listEnvironments(), apiClient.get<{id:string;name:string}[]>('/scenarios', {limit:200}), apiClient.get<{id:string;name:string}[]>('/targets')]);
  if (results[0].status === 'fulfilled') environments.value = results[0].value;
  if (results[1].status === 'fulfilled') scenarios.value = results[1].value;
  if (results[2].status === 'fulfilled') targets.value = results[2].value;
  if (results.some(item => item.status === 'rejected')) errorMessage.value = '筛选选项更新失败，请刷新重试。';
}
let listRequestToken = 0;
const totalRuns=ref(0),pageOffset=ref(0),trendResult=ref('');
const serverFilters=ref({environment_id:'',target_id:'',build:'',transport_mode:'',scenario_id:'',scenario_version:'',status:'',category:'',since:'',until:''});
watch(() => serverFilters.value.scenario_id, async (scenarioId) => {
  const token = ++versionRequestToken;
  serverFilters.value.scenario_version = '';
  scenarioVersions.value = [];
  versionsLoading.value = !!scenarioId;
  if (!scenarioId) return;
  try {
    const versions = await apiClient.get<{version:number;change_note?:string}[]>(`/scenarios/${encodeURIComponent(scenarioId)}/versions`);
    if (token === versionRequestToken) scenarioVersions.value = versions;
  } catch (cause) {
    if (token === versionRequestToken) errorMessage.value = resolveApiErrorMessage(cause, '发布版本读取失败，请重新选择场景');
  } finally { if (token === versionRequestToken) versionsLoading.value = false; }
});
const applyFilters=async()=>{pageOffset.value=0;await loadRuns();};
const loadTrends=async()=>{try{trendResult.value=JSON.stringify(await apiClient.get('/run-trends',{
  environment_id:serverFilters.value.environment_id,transport_mode:serverFilters.value.transport_mode,
  scenario_id:serverFilters.value.scenario_id,scenario_version:Number(serverFilters.value.scenario_version),
}),null,2);}catch(cause){errorMessage.value=resolveApiErrorMessage(cause,'趋势读取失败');}};
const loading = ref(false);
const detailLoading = ref(false);
const rerunLoading = ref(false);
const errorMessage = ref('');
const detailErrorMessage = ref('');
const actionMessage = ref('');
const note = ref('');
const source = ref<ApiDataSource>('api');
const lastLoadedAt = ref('');
const selectedRunId = ref('');
const selectedRunDetail = ref<RunDetail | null>(null);

const sourceLabelMap: Record<ApiDataSource, string> = {
  api: '真实接口',
  compatibility: '兼容聚合',
  mock: '历史模拟来源',
};

const sourceLabel = computed(() => sourceLabelMap[source.value]);
const routeRunId = computed(() => (typeof route.query.runId === 'string' ? route.query.runId : ''));

let detailRequestToken = 0;

const summaryMetrics = computed<DashboardMetric[]>(() => {
  const successCount = runs.value.filter((item) => item.status === 'success' && item.transportMode === 'live' && !isDebugRun(item)).length;
  const failedCount = runs.value.filter(
    (item) => ['failed','error','timed_out','interrupted'].includes(item.status),
  ).length;
  const inflightCount = runs.value.filter(
    (item) => item.status === 'queued' || item.status === 'running',
  ).length;

  return [
    {
      key: 'runs-total',
      label: '运行总数',
      value: String(runs.value.length),
      description: '当前页已经拿到并展示的运行记录数量',
      trend: source.value === 'api' ? '来自真实后端' : '历史来源数据',
    },
    {
      key: 'runs-success',
      label: '真实断言通过（本页）',
      value: String(successCount),
      description: '方便快速判断最近一批运行是否稳定',
      trend: failedCount ? `失败/告警 ${failedCount}` : '暂无失败',
    },
    {
      key: 'runs-inflight',
      label: '排队/执行中',
      value: String(inflightCount),
      description: '排障时先判断是否还在执行或卡在等待调度',
      trend: inflightCount ? '建议关注最新队列' : '当前无积压',
    },
  ];
});

const legendItems = computed(() => [
  {
    key: 'queued',
    ...getRunStatusMeta('queued'),
    description: '后端常见原始值：queued / pending',
  },
  {
    key: 'running',
    ...getRunStatusMeta('running'),
    description: '后端常见原始值：running / in_progress',
  },
  {
    key: 'success',
    ...getRunStatusMeta('success'),
    description: '后端常见原始值：succeeded / passed',
  },
  {
    key: 'failed',
    ...getRunStatusMeta('failed'),
    description: '后端常见原始值：failed / error',
  },
  {
    key: 'warning',
    ...getRunStatusMeta('warning'),
    description: '后端常见原始值：warning / partial_success',
  },
]);

const updateRouteRunId = (runId: string) => {
  const nextQuery = { ...route.query };

  if (runId) {
    nextQuery.runId = runId;
  } else {
    delete nextQuery.runId;
  }

  void router.replace({ query: nextQuery });
};

const applySelectedRunId = (runId: string) => {
  selectedRunId.value = runId;
  if (routeRunId.value !== runId) {
    updateRouteRunId(runId);
  }
};

const selectRun = (runId: string) => {
  applySelectedRunId(runId);
};

/**
 * 详情面板只维护“当前选中的 run id”。
 * 这样列表重新加载后，只需要决定选中谁，不必再维护一份可能过期的详情对象。
 */
const syncSelectedRun = (nextRuns: RunSummary[], preferredRunId = routeRunId.value) => {
  if (preferredRunId) { applySelectedRunId(preferredRunId); return; }
  if (!nextRuns.length) return;

  if (selectedRunId.value && nextRuns.some((item) => item.id === selectedRunId.value)) {
    if (routeRunId.value !== selectedRunId.value) {
      updateRouteRunId(selectedRunId.value);
    }
    return;
  }

  applySelectedRunId(nextRuns[0].id);
};

const selectedRun = computed(() => selectedRunDetail.value?.id === selectedRunId.value ? selectedRunDetail.value : runs.value.find((item) => item.id === selectedRunId.value) ?? null);
const selectedRunMeta = computed(() => {
  const run = selectedRun.value;
  return run ? getRunStatusMeta(run.status) : null;
});

/**
 * 状态映射、说明文案和排障建议统一收口在 `runStatus.ts`。
 * RunsPage 只负责“加载数据 + 选中记录 + 组装详情视图”，避免页面里散落一堆状态判断。
 */
const selectedRunInsight = computed(() => {
  const run = selectedRun.value;
  return run ? getRunStatusInsight(run.status) : null;
});

const rerunnableSuiteId = computed(
  () => selectedRunDetail.value?.suiteId || selectedRun.value?.suiteId || '',
);
const canRerunSelected = computed(
  () => !!selectedRun.value && selectedRun.value.transportMode === 'live' && !['queued','running'].includes(selectedRun.value.status),
);

/**
 * target 目前仍是松散字符串契约，所以这里只做轻量拆分：
 * - `suite/payment-regression` -> 套件 + payment-regression
 * - 其他未知前缀 -> 自定义目标
 */
const inferTargetContext = (target: string) => {
  const normalizedTarget = target.trim();

  if (!normalizedTarget) {
    return {
      kind: '未标记',
      identifier: '未提供',
    };
  }

  const segments = normalizedTarget.split('/').filter(Boolean);
  const targetKindLabelMap: Record<string, string> = {
    suite: '套件',
    case: '用例',
    schedule: '调度任务',
    env: '环境',
    environment: '环境',
  };

  return {
    kind: targetKindLabelMap[segments[0]?.toLowerCase() ?? ''] ?? '自定义目标',
    identifier: segments.slice(1).join('/') || normalizedTarget,
  };
};

const selectedContextFields = computed<RunDetailField[]>(() => {
  const run = selectedRun.value;
  const detail = selectedRunDetail.value;

  if (!run) {
    return [];
  }

  const targetContext = inferTargetContext(run.target);

  return [
    {
      key: 'target',
      label: '目标',
      value: run.target,
    },
    {
      key: 'target-kind',
      label: '目标类型',
      value: targetContext.kind,
    },
    {
      key: 'target-identifier',
      label: '目标标识',
      value: targetContext.identifier,
    },
    {
      key: 'suite-id',
      label: '套件 ID',
      value: detail?.suiteId || run.suiteId || '未回传',
    },
    {
      key: 'environment',
      label: '环境',
      value: run.environmentLabel || '未绑定',
    },
    {
      key: 'requested-by',
      label: '请求人',
      value: detail?.requestedBy || run.starter,
    },
    {
      key: 'trigger-source',
      label: '触发来源',
      value: detail?.triggerSource || '未回传',
    },
    {
      key: 'started-at',
      label: '开始时间',
      value: run.startedAt,
    },
    {
      key: 'duration',
      label: '耗时',
      value: run.duration,
    },
    {
      key: 'source',
      label: '数据源',
      value: sourceLabel.value,
    },
    {
      key: 'raw-status',
      label: '原始状态',
      value: run.rawStatus || '未回传，按展示状态处理',
    },
  ];
});

const buildStatusRemark = (run: RunSummary) => {
  switch (run.status) {
    case 'queued':
      return '当前运行还在等待调度，优先确认队列是否积压、worker 是否空闲。';
    case 'running':
      return '当前运行仍在进行中，建议先从长耗时步骤和外部依赖入手排查。';
    case 'success':
      return '当前运行已经成功完成，如果业务仍异常，下一步应该继续核对日志和结果数据。';
    case 'failed':
      return '当前运行已经失败，建议优先查看失败步骤、错误摘要以及最近变更。';
    case 'warning':
      return '当前运行处于告警态，代表还有需要人工确认的非阻塞异常。';
    default:
      return '当前运行状态需要进一步确认。';
  }
};

const selectedRemarkBlocks = computed<RunRemarkBlock[]>(() => {
  const run = selectedRun.value;
  const detail = selectedRunDetail.value;

  if (!run) {
    return [];
  }

  const primaryBody = detail?.statusMessage || run.errorSummary || buildStatusRemark(run);
  const blocks: RunRemarkBlock[] = [
    {
      key: 'status-remark',
      title: detail?.statusMessage ? '执行状态说明' : run.status === 'failed' ? '异常提示' : '运行备注',
      body: primaryBody,
      tone: run.status === 'failed' ? 'error' : 'info',
    },
  ];

  if (run.note) {
    blocks.push({
      key: 'run-note',
      title: '执行侧备注',
      body: run.note,
      tone: 'neutral',
    });
  }

  if (note.value) {
    blocks.push({
      key: 'data-source-note',
      title: '数据源备注',
      body: note.value,
      tone: 'info',
    });
  }

  if (run.rawStatus) {
    blocks.push({
      key: 'status-mapping-note',
      title: '状态映射',
      body: `原始状态：${run.rawStatus}；当前展示为“${getRunStatusMeta(run.status).label}”。`,
      tone: 'neutral',
    });
  }

  return blocks;
});

const selectedEnvironmentSnapshotJson = computed(() => {
  const environment = selectedRunDetail.value?.payload.environment;

  if (!isRecord(environment)) {
    return '';
  }

  return JSON.stringify(environment, null, 2);
});

const selectedPayloadJson = computed(() => {
  if (!selectedRunDetail.value) {
    return '';
  }

  return JSON.stringify(selectedRunDetail.value.payload, null, 2);
});

const loadSelectedRunDetail = async () => {
  if (!selectedRunId.value || source.value !== 'api') {
    ++detailRequestToken;
    detailLoading.value = false;
    detailErrorMessage.value = '';
    selectedRunDetail.value = null;
    return;
  }

  const requestToken = ++detailRequestToken;
  detailLoading.value = true;
  detailErrorMessage.value = '';
  if (selectedRunDetail.value?.id !== selectedRunId.value) selectedRunDetail.value = null;

  try {
    const detail = await executionApi.getRunDetail(selectedRunId.value);
    if (requestToken !== detailRequestToken) {
      return;
    }

    selectedRunDetail.value = detail;
  } catch (error) {
    if (requestToken !== detailRequestToken) {
      return;
    }

    detailErrorMessage.value = resolveApiErrorMessage(error, '运行详情加载失败，请稍后重试。');
  } finally {
    if (requestToken === detailRequestToken) {
      detailLoading.value = false;
    }
  }
};

const reloadSelectedRunDetail = async () => {
  await loadSelectedRunDetail();
};

const rerunSelectedRun = async () => {
  if (!canRerunSelected.value) {
    return;
  }

  rerunLoading.value = true;
  detailErrorMessage.value = '';

  try {
    const detail = await executionApi.rerun(selectedRunId.value);
    actionMessage.value = `已基于原运行快照创建关联复跑：${detail.id}。`;
    await loadRuns({ preferredRunId: detail.id });
  } catch (error) {
    detailErrorMessage.value = resolveApiErrorMessage(error, '快速复跑失败，请稍后重试。');
  } finally {
    rerunLoading.value = false;
  }
};

const reloadRuns = async () => {
  await loadRuns();
};

/**
 * 页面只关心“要展示什么状态”：
 * 真实接口、来源标识、最后更新时间、默认选中项，
 * 都在加载函数里一次性收口，避免模板里再分散处理。
 */
const loadRuns = async (options?: { preferredRunId?: string }) => {
  const token = ++listRequestToken;
  loading.value = true;
  errorMessage.value = '';

  try {
    const query:Record<string,string | number>={limit:20,offset:pageOffset.value};
    for(const [key,value] of Object.entries(serverFilters.value))if(value)query[key]=key === 'scenario_version' ? Number(value) : ['since','until'].includes(key) ? new Date(value).toISOString() : value;
    const result = await managementApi.listRuns({query});
    if (token !== listRequestToken) return;
    totalRuns.value=result.total ?? result.data.length;
    runs.value = result.data;
    source.value = result.source;
    note.value = result.note ?? '';
    const before = selectedRunId.value;
    syncSelectedRun(result.data, options?.preferredRunId || routeRunId.value);
    if (before === selectedRunId.value) await loadSelectedRunDetail();
    lastLoadedAt.value = new Date().toLocaleString('zh-CN', { hour12: false });
  } catch (error) {
    if (token !== listRequestToken) return;
    errorMessage.value = resolveApiErrorMessage(error, '运行记录加载失败，请稍后重试。');
  } finally {
    if (token === listRequestToken) loading.value = false;
  }
};

watch(routeRunId, (runId) => {
  if (!runId) {
    return;
  }

  if (runId !== selectedRunId.value) {
    selectedRunId.value = runId;
  }
});

watch(
  () => [selectedRunId.value, source.value],
  () => {
    void loadSelectedRunDetail();
  },
);

const resourceInfo = ref(''), cleanupToken = ref('');
watch(selectedRunId, () => { resourceInfo.value = ''; cleanupToken.value = ''; });
const resourcePreflight = async () => {
  const runId = selectedRunId.value;
  cleanupToken.value = '';
  try {
    const resources = await apiClient.get(`/runs/${runId}/resources`);
    const plan = await apiClient.post<{preflight_token: string; ready: string[]}>(`/runs/${runId}/cleanup-preflight`);
    if (runId !== selectedRunId.value) return;
    resourceInfo.value = JSON.stringify({resources, plan}, null, 2);
    cleanupToken.value = plan.ready.length ? plan.preflight_token : '';
  } catch(cause) { if (runId === selectedRunId.value) detailErrorMessage.value = resolveApiErrorMessage(cause, '资源预检失败'); }
};
const retryResourceCleanup = async () => {
  const runId = selectedRunId.value, token = cleanupToken.value;
  if (!token) return;
  cleanupToken.value = '';
  try {
    const result = await apiClient.post(`/runs/${runId}/cleanup`, {preflight_token:token});
    if (runId === selectedRunId.value) resourceInfo.value = JSON.stringify(result, null, 2);
  } catch(cause) { if (runId === selectedRunId.value) detailErrorMessage.value = resolveApiErrorMessage(cause, '清理失败，请重新预检后重试'); }
};
const cancelSelected = async () => {
  try {
    await executionApi.cancelRun(selectedRunId.value);
    await loadRuns();
  } catch (error) {
    detailErrorMessage.value = resolveApiErrorMessage(error, '取消失败');
  }
};
let refreshTimer: ReturnType<typeof setInterval> | undefined;
const resumeRefresh = () => { if (!document.hidden) { void loadRuns(); } };
onUnmounted(() => { listRequestToken++; detailRequestToken++; versionRequestToken++; if (refreshTimer) clearInterval(refreshTimer); document.removeEventListener('visibilitychange', resumeRefresh); });
onMounted(() => {
  void loadFilterOptions();
  document.addEventListener('visibilitychange', resumeRefresh);
  void loadRuns();
  refreshTimer = setInterval(() => {
    if (!document.hidden && !loading.value && (runs.value.some(run => ['queued', 'running'].includes(run.status)) || (selectedRun.value && ['queued','running'].includes(selectedRun.value.status)))) {
      void loadRuns();
    }
  }, 2500);
});
</script>

<style scoped>
.content-grid { grid-template-columns:minmax(0,1fr); }
pre { max-width:100%; max-height:28rem; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; }
.detail-stack { min-width:0; }

.run-filters {display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.5rem;}
.run-filters label {display:grid;gap:.25rem;}
.hero-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(245, 249, 255, 0.92)),
    linear-gradient(135deg, rgba(255, 195, 113, 0.16), transparent);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: var(--shadow-soft);
}

/* 与仪表盘一致：标题与元信息按可用空间换行，避免标题列归零。 */
.hero-banner > div:first-child {
  flex: 1 1 24rem;
  min-width: 0;
}

.hero-banner__eyebrow {
  margin: 0 0 0.55rem;
  color: var(--color-accent-strong);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero-banner__title {
  margin: 0;
  font-size: clamp(1.5rem, 2vw, 2rem);
  line-height: 1.2;
  letter-spacing: -0.04em;
}

.hero-banner__copy {
  max-width: 46rem;
  margin: 0.85rem 0 0;
  color: var(--color-ink-muted);
  line-height: 1.8;
}

.hero-banner__meta {
  flex: 1 1 18rem;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-content: flex-start;
  justify-content: flex-end;
}

.hero-banner__pill {
  max-width: 100%;
  overflow-wrap: anywhere;
  display: inline-flex;
  align-items: center;
  min-height: 2.3rem;
  padding: 0.5rem 0.85rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: var(--color-ink-base);
  font-size: 0.88rem;
  box-shadow: var(--shadow-soft);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

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

.run-name {
  font-weight: 700;
}

.run-name-row {
  display: flex;
  gap: 0.55rem;
  align-items: center;
  flex-wrap: wrap;
}

.run-current {
  display: inline-flex;
  align-items: center;
  min-height: 1.45rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
  font-size: 0.74rem;
  font-weight: 700;
}

.run-subtle {
  margin-top: 0.35rem;
  color: var(--color-ink-subtle);
  font-size: 0.82rem;
}

.run-row {
  cursor: pointer;
  outline: none;
}

.run-row td {
  transition:
    background-color 160ms ease,
    color 160ms ease;
}

.run-row:hover td {
  background: rgba(248, 250, 252, 0.88);
}

.run-row--selected td {
  background: rgba(219, 234, 254, 0.65);
}

.run-row:focus-visible {
  outline: 2px solid rgba(59, 130, 246, 0.38);
  outline-offset: -2px;
}

.side-stack,
.status-legend {
  display: grid;
  gap: 1rem;
}

.detail-snapshot {
  display: grid;
  gap: 0.85rem;
}

.detail-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem;
}

.detail-hero,
.detail-section {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.85rem;
  padding: 1rem;
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.detail-hero {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(239, 246, 255, 0.88)),
    linear-gradient(135deg, rgba(59, 130, 246, 0.08), transparent);
}

.detail-hero__header,
.detail-section__header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.85rem;
  justify-content: space-between;
  align-items: flex-start;
}

.detail-hero__header > div {
  min-width: 0;
  overflow-wrap: anywhere;
}

.detail-hero__eyebrow {
  margin: 0 0 0.4rem;
  color: var(--color-accent-strong);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.detail-hero__title,
.detail-section__title {
  margin: 0;
  font-size: 1rem;
}

.detail-hero__copy,
.detail-section__copy {
  margin: 0;
  color: var(--color-ink-muted);
  line-height: 1.8;
}

.detail-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.detail-pill {
  display: inline-flex;
  align-items: center;
  min-height: 2rem;
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: var(--color-ink-base);
  font-size: 0.82rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin: 0;
}

.detail-grid__item {
  padding: 0.85rem 0.9rem;
  border-radius: 0.95rem;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.detail-grid__item dt {
  margin: 0;
  color: var(--color-ink-subtle);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.detail-grid__item dd {
  margin: 0.45rem 0 0;
  color: var(--color-ink-base);
  line-height: 1.75;
  word-break: break-word;
}

.remark-list {
  display: grid;
  gap: 0.75rem;
}

.remark-card {
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border: 1px solid transparent;
}

.remark-card h4,
.remark-card p {
  margin: 0;
}

.remark-card h4 {
  font-size: 0.92rem;
}

.remark-card p {
  margin-top: 0.45rem;
  line-height: 1.8;
}

.remark-card--info {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.remark-card--error {
  background: rgba(244, 63, 94, 0.08);
  border-color: rgba(244, 63, 94, 0.12);
  color: #be123c;
}

.remark-card--neutral {
  background: rgba(15, 23, 42, 0.04);
  border-color: rgba(148, 163, 184, 0.14);
  color: var(--color-ink-base);
}

.snapshot-card {
  display: grid;
  gap: 0.6rem;
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.snapshot-card h4,
.snapshot-card pre {
  margin: 0;
}

.snapshot-card h4 {
  font-size: 0.92rem;
}

.snapshot-card pre {
  padding: 0.85rem 0.95rem;
  border-radius: 0.9rem;
  background: rgba(15, 23, 42, 0.94);
  color: rgba(226, 232, 240, 0.96);
  overflow-x: auto;
  line-height: 1.65;
  font-size: 0.84rem;
}

.status-legend__row {
  display: grid;
  gap: 0.55rem;
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  background: rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.status-legend__row p {
  margin: 0;
  color: var(--color-ink-muted);
  line-height: 1.75;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .hero-banner__meta {
    justify-content: flex-start;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
.hero-banner { padding: 20px; background: #fff; border-radius: var(--radius-large); box-shadow: var(--shadow-soft); }
.hero-banner__title { font-size: 22px; letter-spacing: -.5px; }
.hero-banner__eyebrow { font-size: 11px; letter-spacing: .6px; }
.hero-banner__copy { margin-top: 8px; font-size: 12px; }
.hero-banner__pill { border-radius: 5px; padding: 5px 9px; min-height: 28px; font-size: 11px; box-shadow: none; background: #f6f7f9; border: 0; }
.run-filter-panel { border: 1px solid var(--color-border); border-radius: 7px; }
.run-filter-panel summary span { margin-left: 10px; color: var(--color-ink-subtle); font-size: 11px; font-weight: 400; }
.run-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr)); gap: 12px; padding: 0 14px 14px; }
.run-filters label { display: grid; gap: 6px; }
.run-filters button { align-self: end; }
.run-pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.run-pagination p { margin-right: auto; font-size: 12px; color: var(--color-ink-subtle); }
.detail-snapshot { border: 1px solid var(--color-border); border-radius: 7px; }
.snapshot-card { margin: 12px; }
.metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (max-width:1600px) { .content-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width:760px) { .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width:420px) { .metrics-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
