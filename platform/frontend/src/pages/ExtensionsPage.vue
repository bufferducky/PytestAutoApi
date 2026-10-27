<template><section class="page-grid"><el-tabs v-model="tool" aria-label="扩展工具目录"><el-tab-pane v-for="item in tools" :key="item.key" :name="item.key" :label="item.label" /></el-tabs><el-alert :title="tools.find(item=>item.key===tool)?.description || ''" type="info" :closable="false" /><section v-show="tool==='coverage'"><CoverageLedgerPanel /></section><section v-show="tool==='resources'"><ResourceFixturesPanel /></section><section v-show="tool==='journeys'"><JourneyCapabilitiesPanel /></section><section v-show="tool==='evaluation'"><EvaluationQualityPanel /></section></section></template>
<script setup lang="ts">
import {ref} from 'vue';
import CoverageLedgerPanel from '@/components/CoverageLedgerPanel.vue';
import ResourceFixturesPanel from '@/components/ResourceFixturesPanel.vue';
import JourneyCapabilitiesPanel from '@/components/JourneyCapabilitiesPanel.vue';
import EvaluationQualityPanel from '@/components/EvaluationQualityPanel.vue';
const tool=ref('coverage');
const tools=[{key:'coverage',label:'覆盖与研究账本',description:'查看场景覆盖与待确认契约。'},{key:'resources',label:'测试资源与清理配置',description:'管理测试数据、资源预算与清理规则。'},{key:'journeys',label:'Web / App 旅程与能力',description:'维护旅程版本，检查执行器能力与依赖。'},{key:'evaluation',label:'历史评估报告',description:'查阅历史报告和复核记录，新评估执行保持禁用。'}];
</script>
