<template>
  <section class="page-grid">
    <p class="state-banner state-banner--info">按需打开辅助工具；场景编写、调试和回归仍在主工作区完成。</p>
    <div class="auxiliary-panels">    <details><summary aria-label="覆盖与研究账本">覆盖与研究账本<HelpHint topic="coverage" /></summary><CoverageLedgerPanel /></details>
    <details><summary aria-label="测试资源与清理配置">测试资源与清理配置<HelpHint topic="fixture" /></summary><ResourceFixturesPanel /></details>
    <details><summary aria-label="Web / App 旅程与能力">Web / App 旅程与能力<HelpHint topic="runner" /></summary><JourneyCapabilitiesPanel /></details>
    <details><summary aria-label="历史评估报告（新执行禁用）">历史评估报告（新执行禁用）<HelpHint topic="evaluation" /></summary><EvaluationQualityPanel /></details>
    </div>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import CoverageLedgerPanel from '@/components/CoverageLedgerPanel.vue';
import ResourceFixturesPanel from '@/components/ResourceFixturesPanel.vue';
import JourneyCapabilitiesPanel from '@/components/JourneyCapabilitiesPanel.vue';
import EvaluationQualityPanel from '@/components/EvaluationQualityPanel.vue';
</script>
