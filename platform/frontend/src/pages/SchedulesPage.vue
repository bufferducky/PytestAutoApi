<template>
  <section class="page-grid">
    <SchedulePlansPanel @saved="loadSchedules" />
    <details><summary>调度任务概览</summary><div>
      <PlaceholderPanel
        title="调度任务"
        description="查看计划目标、运行环境与最近触发结果。"
      >
        <p v-if="errorMessage" class="state-banner state-banner--error">{{ errorMessage }}</p>
        <div v-if="loading && !schedules.length" class="empty-copy">正在加载调度任务...</div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>任务名</th>
                <th>Cron</th>
                <th>目标</th>
                <th>环境</th>
                <th>最近执行</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody><tr v-if="!schedules.length"><td colspan="6" class="empty-copy">暂无调度任务，请先创建回归计划。</td></tr>
              <tr v-for="item in schedules" :key="item.id">
                <td>{{ item.name }}</td>
                <td>{{ item.cron }}</td>
                <td>{{ item.target }}</td>
                <td>{{ item.environmentLabel || '未绑定' }}</td>
                <td>{{ item.lastRun }}</td>
                <td>
                  <StatusTag
                    :label="scheduleStatusLabelMap[item.status]"
                    :tone="item.status === 'active' ? 'success' : 'warning'"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PlaceholderPanel>

    </div></details>
  </section>
</template>

<script setup lang="ts">
import SchedulePlansPanel from '@/components/SchedulePlansPanel.vue';
import { onMounted, ref } from 'vue';

import { managementApi } from '@/api';
import PlaceholderPanel from '@/components/common/PlaceholderPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import type { ScheduleSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

// 调度页只承接轻量计划任务，不把真正长任务执行塞进前端页面。
const schedules = ref<ScheduleSummary[]>([]);
const loading = ref(false);
const errorMessage = ref('');

const scheduleStatusLabelMap = {
  active: '已启用',
  paused: '已暂停',
} as const;

let readSequence = 0;
const loadSchedules = async () => {
  const sequence = ++readSequence;
  loading.value = true;
  errorMessage.value = '';

  try {
    const items = await managementApi.listSchedules();
    if (sequence === readSequence) schedules.value = items;
  } catch (error) {
    if (sequence === readSequence) errorMessage.value = resolveApiErrorMessage(error, '调度概览更新失败，保留原有内容。');
  } finally {
    if (sequence === readSequence) loading.value = false;
  }
};

onMounted(() => {
  void loadSchedules();
});
</script>
