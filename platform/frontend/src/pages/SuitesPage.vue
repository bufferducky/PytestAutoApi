<template>
  <section class="page-grid">
    <ScenarioAssetsPanel kind="suites" @saved="onSaved" @selected="appStore.rememberAsset" />
    <details><summary>套件目录概览</summary><div>
      <ContentPanel
        title="套件目录"
        description="查看已保存套件的场景数量与最近运行。"
      >
        <p v-if="errorMessage" class="state-banner state-banner--error">{{ errorMessage }}</p>
        <div v-if="loading && !suites.length" class="empty-copy">正在加载套件列表...</div>

        <div v-else class="table-shell">
          <table>
            <thead>
              <tr>
                <th>套件</th>
                <th>用例数</th>
                <th>最近运行</th>
                <th aria-label="调度计划">调度计划<HelpHint topic="scheduleToggle" /></th>
              </tr>
            </thead>
            <tbody><tr v-if="!suites.length"><td colspan="4" class="empty-copy">暂无套件，请先创建套件并添加已发布的场景版本。</td></tr>
              <tr v-for="item in suites" :key="item.id">
                <td>{{ item.name }}</td>
                <td>{{ item.caseCount }}</td>
                <td>{{ item.lastRun }}</td>
                <td>{{ item.schedule }}</td>
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
import type { SuiteSummary } from '@/types/platform';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

// 套件页骨架强调“执行组织能力”，
// 让后续的排序、分组、依赖关系有明确落点。
const appStore = useAppStore();
const onSaved = (asset?: unknown) => {
  if (asset && typeof asset === 'object' && 'id' in asset && typeof asset.id === 'string') appStore.rememberAsset(asset.id);
  void loadSuites();
};
const suites = ref<SuiteSummary[]>([]);
const loading = ref(false);
const errorMessage = ref('');

let requestSequence = 0;
const loadSuites = async () => {
  const sequence = ++requestSequence;
  loading.value = true;
  errorMessage.value = '';

  try {
    const result = await managementApi.listSuites();
    if (sequence === requestSequence) suites.value = result;
  } catch (error) {
    if (sequence === requestSequence) errorMessage.value = resolveApiErrorMessage(error, '套件列表加载失败，请稍后重试。');
  } finally {
    if (sequence === requestSequence) loading.value = false;
  }
};

onMounted(() => {
  void loadSuites();
});
</script>

<style scoped>
.action-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-accent-strong);
  cursor: pointer;
}

.action-link:disabled {
  opacity: 0.6;
  cursor: wait;
}
</style>
