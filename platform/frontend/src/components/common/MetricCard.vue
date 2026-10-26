<template>
  <article class="metric-card">
    <p class="metric-card__label">{{ metric.label }}<HelpHint v-if="helpTopic" :topic="helpTopic" /></p>
    <strong class="metric-card__value">{{ metric.value }}</strong>
    <p class="metric-card__description">{{ metric.description }}</p>
    <p class="metric-card__trend">{{ metric.trend }}</p>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import HelpHint from '@/components/common/HelpHint.vue';
import type { HelpTopic } from '@/content/helpTopics';
import type { DashboardMetric } from '@/types/platform';

const props = defineProps<{
  metric: DashboardMetric;
}>();
const metricTopics: Record<string, HelpTopic> = { runs: 'metricsTotal', queued: 'metricsInflight', running: 'metricsInflight', failed: 'metricsFailed', 'runs-total': 'metricsPage', 'runs-success': 'metricsSuccess', 'runs-inflight': 'metricsInflight' };
const helpTopic = computed(() => metricTopics[props.metric.key]);
</script>

<style scoped>
.metric-card { position: relative; padding: 20px; border-radius: var(--radius-large); background: white; border: 1px solid var(--color-border); box-shadow: var(--shadow-soft); }
.metric-card::before { content: ''; position: absolute; right: 20px; top: 23px; width: 7px; height: 7px; border-radius: 2px; background: #a8b8f4; }
.metric-card__label { margin: 0; padding-right: 16px; font-size: 12px; color: var(--color-ink-subtle); }
.metric-card__value { display: block; margin-top: 12px; font-size: 30px; font-weight: 650; line-height: 1.2; letter-spacing: -1px; font-variant-numeric: tabular-nums; }
.metric-card__description { margin: 10px 0 0; font-size: 11px; color: var(--color-ink-subtle); line-height: 1.7; }
.metric-card__trend { margin: 12px 0 0; color: var(--color-accent-strong); font-weight: 500; font-size: 11px; border-top: 1px solid #eff1f5; padding-top: 10px; }
</style>
