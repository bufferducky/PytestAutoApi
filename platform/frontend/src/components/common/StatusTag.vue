<template>
  <el-tag class="status-tag" :class="`status-tag--${tone}`" :type="tone === 'success' ? 'success' : tone === 'attention' ? 'danger' : tone === 'warning' ? 'warning' : tone === 'running' ? 'primary' : 'info'" effect="light" disable-transitions>{{ label }}</el-tag>
</template>

<script setup lang="ts">
import type { StatusTone } from '@/types/platform';

defineProps<{
  label: string;
  tone: StatusTone;
}>();
</script>

<style scoped>
.status-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  white-space: nowrap;
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.status-tag::before { content: ''; width: 5px; height: 5px; flex-shrink: 0; border-radius: 50%; background: currentColor; }

.status-tag--success {
  background: rgba(22, 163, 74, 0.12);
  color: #166534;
}

.status-tag--warning {
  background: rgba(245, 158, 11, 0.16);
  color: #9a3412;
}

.status-tag--running {
  background: rgba(59, 130, 246, 0.14);
  color: #1d4ed8;
}

.status-tag--neutral {
  background: rgba(100, 116, 139, 0.12);
  color: #334155;
}

.status-tag--attention {
  background: rgba(244, 63, 94, 0.12);
  color: #be123c;
}
</style>
