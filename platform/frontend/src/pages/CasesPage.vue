<template>
  <section class="page-grid">
    <ScenarioAssetsPanel kind="scenarios" @saved="onSaved" @selected="appStore.rememberAsset" />
    <details><summary>用例目录概览</summary>
    <div>
      <ContentPanel
        title="用例目录"
        description="查看已保存场景的模块、请求方法与状态。"
      >
        <p v-if="errorMessage" role="alert" class="state-banner state-banner--error">{{ errorMessage }}</p>
        <div v-if="loading && !cases.length" class="empty-copy">正在加载用例列表...</div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>用例</th>
                <th>模块</th>
                <th aria-label="方法">方法<HelpHint topic="method" /></th>
                <th aria-label="优先级">优先级<HelpHint topic="priority" /></th>
                <th aria-label="状态">状态<HelpHint topic="assetStatus" /></th>
              </tr>
            </thead>
            <tbody><tr v-if="!cases.length"><td colspan="5" class="empty-copy">暂无用例，创建并保存场景后可在此查看。</td></tr>
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
      </ContentPanel>


    </div></details>

  </section>
</template>

<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { useAppStore } from '@/stores/app';
import ScenarioAssetsPanel from '@/components/ScenarioAssetsPanel.vue';
import { onMounted, ref } from 'vue';

import { managementApi } from '@/api';
import ContentPanel from '@/components/common/ContentPanel.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import type { CaseSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

// 目录与上方资产编辑器读取同一持久化真源。
const appStore = useAppStore();
const onSaved = (asset?: unknown) => {
  if (asset && typeof asset === 'object' && 'id' in asset && typeof asset.id === 'string') appStore.rememberAsset(asset.id);
  void loadCases();
};
const cases = ref<CaseSummary[]>([]);
const loading = ref(false);
const errorMessage = ref('');

const caseStatusLabelMap = {
  active: '已启用',
  draft: '草稿',
} as const;

let requestSequence = 0;
const loadCases = async () => {
  const sequence = ++requestSequence;
  loading.value = true;
  errorMessage.value = '';

  try {
    const result = await managementApi.listCases();
    if (sequence === requestSequence) cases.value = result;
  } catch (error) {
    if (sequence === requestSequence) errorMessage.value = resolveApiErrorMessage(error, '用例列表加载失败，请稍后重试。');
  } finally {
    if (sequence === requestSequence) loading.value = false;
  }
};

onMounted(() => {
  void loadCases();
});
</script>
