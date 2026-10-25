<template>
  <section class="page-grid">
    <section class="hero-banner">
      <div>
        <p class="hero-banner__eyebrow">工作台总览</p>
        <h2 class="hero-banner__title">管理测试资产，查看真实执行结果。</h2>
        <p class="hero-banner__copy">
          统计来自真实测试运行，迁入演示历史不计入真实统计。
        </p>
      </div>

      <div class="hero-banner__meta">
        <button class="action-button" type="button" :disabled="dashboardStore.loading" @click="reload">刷新数据</button>
        <span class="hero-banner__pill">{{ appStore.phaseLabel }}</span>
        <span class="hero-banner__pill">数据源：{{ sourceLabel }}</span>
        <span class="hero-banner__pill" v-if="dashboardStore.lastLoadedAt">
          更新于 {{ dashboardStore.lastLoadedAt }}
        </span>
      </div>
    </section>

    <p v-if="dashboardStore.note" class="state-banner state-banner--info">{{ dashboardStore.note }}</p>
    <p v-if="dashboardStore.errorMessage" class="state-banner state-banner--error">
      {{ dashboardStore.errorMessage }}
    </p>

    <div v-if="dashboardStore.loading && !dashboardStore.overview.metrics.length" class="empty-copy">
      正在加载仪表盘数据...
    </div>

    <div v-else-if="dashboardStore.overview.metrics.length" class="metrics-grid">
      <MetricCard
        v-for="metric in dashboardStore.overview.metrics"
        :key="metric.key"
        :metric="metric"
      />
    </div>

    <div v-else class="empty-card">
      <p class="empty-copy">当前没有可展示的仪表盘统计数据。</p>
      <button class="action-button" type="button" :disabled="dashboardStore.loading" @click="reload">
        {{ dashboardStore.loading ? '加载中...' : '重新加载' }}
      </button>
    </div>

    <div class="content-grid">
      <PlaceholderPanel
        v-if="dashboardStore.overview.focusItems.length"
        title="当前重点"
        description="这些卡片用于提示团队近期最值得产品化的平台能力。"
      >
        <template #actions>
          <button class="action-button" type="button" :disabled="dashboardStore.loading" @click="reload">
            {{ dashboardStore.loading ? '加载中...' : '刷新数据' }}
          </button>
        </template>

        <div v-if="dashboardStore.loading && !dashboardStore.overview.focusItems.length" class="empty-copy">
          正在整理当前重点...
        </div>

        <div v-else-if="dashboardStore.overview.focusItems.length" class="focus-list">
          <article
            v-for="item in dashboardStore.overview.focusItems"
            :key="item.id"
            class="focus-item"
          >
            <div class="focus-item__header">
              <h3>{{ item.title }}</h3>
              <StatusTag :label="focusLabelMap[item.status]" :tone="focusToneMap[item.status]" />
            </div>
            <p class="focus-item__meta">归属：{{ item.owner }}</p>
            <p class="focus-item__summary">{{ item.summary }}</p>
          </article>
        </div>

        <div v-else class="empty-copy">当前暂无重点事项，等后端补齐 overview 后可展示更细粒度建议。</div>
      </PlaceholderPanel>

      <PlaceholderPanel
        title="最近运行"
        description="最近创建的运行记录；历史演示结果单独标注。"
      >
        <div v-if="dashboardStore.loading && !dashboardStore.overview.recentRuns.length" class="empty-copy">
          正在整理最近运行...
        </div>

        <div v-else-if="dashboardStore.overview.recentRuns.length" class="run-list">
          <article
            v-for="run in dashboardStore.overview.recentRuns"
            :key="run.id"
            class="run-item"
          >
            <div class="run-item__header">
              <div>
                <h3>{{ run.name }}</h3>
                <p>{{ run.target }}</p>
              </div>
              <StatusTag
                :label="run.validationScope === 'historical_demo' ? '演示历史 · ' + getRunStatusMeta(run.status).label : run.transportMode === 'mock' ? '模拟历史 · ' + getRunStatusMeta(run.status).label : getRunStatusMeta(run.status).label"
                :tone="getRunStatusMeta(run.status).tone"
              />
            </div>
            <dl class="run-item__meta">
              <div>
                <dt>触发人</dt>
                <dd>{{ run.starter }}</dd>
              </div>
              <div>
                <dt>开始时间</dt>
                <dd>{{ run.startedAt }}</dd>
              </div>
              <div>
                <dt>耗时</dt>
                <dd>{{ run.duration }}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div v-else class="empty-copy">
          当前没有可展示的最近运行摘要。若后端只有 health/live，本区会先保持空态而不伪造真实记录。
        </div>
      </PlaceholderPanel>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';

import MetricCard from '@/components/common/MetricCard.vue';
import PlaceholderPanel from '@/components/common/PlaceholderPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import { useAppStore } from '@/stores/app';
import { useDashboardStore } from '@/stores/dashboard';
import type { ApiDataSource } from '@/types/platform';
import { getRunStatusMeta } from '@/utils/runStatus';

const appStore = useAppStore();
const dashboardStore = useDashboardStore();

const focusToneMap = {
  stable: 'success',
  attention: 'attention',
  planned: 'neutral',
} as const;

const focusLabelMap = {
  stable: '稳定',
  attention: '需关注',
  planned: '规划中',
} as const;

const sourceLabelMap: Record<ApiDataSource, string> = {
  api: '真实接口',
  compatibility: '兼容聚合',
  mock: '历史模拟来源',
};

const sourceLabel = computed(() => sourceLabelMap[dashboardStore.source]);

// 页面本身不再区分接口来源 的细节，统一交给 store + API 适配层收口。
const reload = async () => {
  await dashboardStore.loadOverview();
};

onMounted(async () => {
  if (!dashboardStore.overview.metrics.length && !dashboardStore.loading) {
    await reload();
  }
});
</script>

<style scoped>
.hero-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(245, 249, 255, 0.92)),
    linear-gradient(135deg, rgba(96, 165, 250, 0.16), transparent);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: var(--shadow-soft);
}

/* 元信息不能用 auto 网格列抢光标题宽度；空间不足时整块换行。 */
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

.empty-card {
  display: grid;
  gap: 1rem;
  justify-items: start;
  padding: 1.2rem;
  border-radius: 1.2rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-soft);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.focus-list,
.run-list {
  display: grid;
  gap: 1rem;
}

.focus-item,
.run-item {
  padding: 1rem;
  border-radius: 1rem;
  background: rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.focus-item__header,
.run-item__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.focus-item__header h3,
.run-item__header h3 {
  margin: 0;
  font-size: 1rem;
}

.focus-item__meta,
.run-item__header p {
  margin: 0.4rem 0 0;
  color: var(--color-ink-subtle);
}

.focus-item__summary {
  margin: 0.8rem 0 0;
  line-height: 1.8;
  color: var(--color-ink-muted);
}

.run-item__meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.9rem 0 0;
}

.run-item__meta dt {
  color: var(--color-ink-subtle);
  font-size: 0.82rem;
}

.run-item__meta dd {
  margin: 0.28rem 0 0;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .hero-banner__meta {
    justify-content: flex-start;
  }

  .metrics-grid,
  .run-item__meta {
    grid-template-columns: 1fr;
  }
}
</style>
