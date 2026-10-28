<template>
  <details v-if="text.length > 240" class="evidence-value">
    <summary>{{ preview }} · 展开完整内容</summary>
    <pre>{{ text }}</pre>
  </details>
  <span v-else class="evidence-value">{{ text }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ value: unknown; summary?: string }>();
const text = computed(() => props.value === undefined ? '未记录' : typeof props.value === 'string' ? props.value : JSON.stringify(props.value, null, 2));
const preview = computed(() => {
  if (props.summary) return props.summary;
  const value = props.value;
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const labels: Record<string, string> = { missing_ids: '缺失', extra_ids: '多出', duplicate_ids: '重复', problems: '异常' };
    const differences = Object.entries(value).filter(([key, items]) => key in labels && Array.isArray(items));
    if (differences.length) return differences.map(([key, items]) => `${labels[key]} ${Array.isArray(items) ? items.length : 0} 项`).join('；');
  }
  return text.value.slice(0, 140) + '…';
});
</script>

<style scoped>
.evidence-value { white-space:pre-wrap; overflow-wrap:anywhere; }
details { margin-block:6px; }
summary { line-height:1.6; }
pre { max-height:18rem; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; margin-block:8px; }
</style>
