<template>
  <section class="page-grid">
    <ScenarioAssetsPanel kind="scenarios" />
    <CoverageLedgerPanel />
    <ResourceFixturesPanel />
    <JourneyCapabilitiesPanel />
    <EvaluationQualityPanel />
    <div class="content-grid">
      <PlaceholderPanel
        title="用例目录"
        description="来自已保存的场景资产；编辑和发布请使用上方资产面板。"
      >
        <p v-if="errorMessage" class="state-banner state-banner--error">{{ errorMessage }}</p>
        <div v-if="loading" class="empty-copy">正在加载用例列表...</div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>用例</th>
                <th>模块</th>
                <th>方法</th>
                <th>优先级</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in cases" :key="item.id">
                <td>{{ item.name }}</td>
                <td>{{ item.module }}</td>
                <td>{{ item.method }}</td>
                <td>{{ item.priority }}</td>
                <td>
                  <StatusTag
                    :label="caseStatusLabelMap[item.status]"
                    :tone="item.status === 'active' ? 'success' : 'neutral'"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PlaceholderPanel>


    </div>
  </section>
</template>

<script setup lang="ts">
import EvaluationQualityPanel from '@/components/EvaluationQualityPanel.vue';
import JourneyCapabilitiesPanel from '@/components/JourneyCapabilitiesPanel.vue';
import ResourceFixturesPanel from '@/components/ResourceFixturesPanel.vue';
import ScenarioAssetsPanel from '@/components/ScenarioAssetsPanel.vue';
import CoverageLedgerPanel from '@/components/CoverageLedgerPanel.vue';
import { onMounted, ref } from 'vue';

import { managementApi } from '@/api';
import PlaceholderPanel from '@/components/common/PlaceholderPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import type { CaseSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

// 目录与上方资产编辑器读取同一持久化真源。
const cases = ref<CaseSummary[]>([]);
const loading = ref(false);
const errorMessage = ref('');

const caseStatusLabelMap = {
  active: '已启用',
  draft: '草稿',
} as const;

const loadCases = async () => {
  loading.value = true;
  errorMessage.value = '';

  try {
    cases.value = await managementApi.listCases();
  } catch (error) {
    errorMessage.value = resolveApiErrorMessage(error, '用例列表加载失败，请稍后重试。');
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  void loadCases();
});
</script>
