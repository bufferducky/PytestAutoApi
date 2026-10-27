<template>
  <figure class="manual-diagram" :class="{ 'manual-diagram--expanded': expanded }" aria-label="流程图">
    <div class="manual-diagram__toolbar"><span>流程图</span><button v-if="svg" type="button" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起大图' : '展开大图' }}</button></div>
    <p v-if="loading" role="status">正在绘制流程图…</p>
    <div v-else-if="svg" class="manual-diagram__canvas" v-html="svg" />
    <p v-if="error" role="alert">流程图暂时无法绘制，请先阅读相邻的文字说明。</p>
    <details v-if="error"><summary>查看流程图源码</summary><pre>{{ source }}</pre></details>
  </figure>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from 'vue';
const props = defineProps<{ source: string }>();
const emit = defineEmits<{ (event: 'rendered'): void }>();
const svg = ref(''), loading = ref(true), error = ref(false), expanded = ref(false);
const instanceId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
let generation = 0;
onBeforeUnmount(() => { ++generation; });
watch(() => props.source, async source => {
  const current = ++generation;
  loading.value = true; error.value = false; svg.value = ''; expanded.value = false;
  try {
    // 图形依赖只在阅读手册时加载，业务页面的问号不加载 Mermaid。
    const { default: mermaid } = await import('mermaid');
    mermaid.initialize({ startOnLoad: false, suppressErrorRendering: true, securityLevel: 'strict', theme: 'base', fontFamily: 'system-ui, sans-serif', themeVariables: { primaryColor: '#eef2ff', primaryTextColor: '#26344d', primaryBorderColor: '#a8b7df', lineColor: '#7082aa', secondaryColor: '#f1f7f4', tertiaryColor: '#faf7ef' }, flowchart: { useMaxWidth: false, htmlLabels: false } });
    const rendered = await mermaid.render(`manual-diagram-${instanceId}-${current}`, source);
    if (current === generation) svg.value = rendered.svg;
  } catch {
    if (current === generation) error.value = true;
  } finally { if (current === generation) { loading.value = false; emit('rendered'); } }
}, { immediate: true });
</script>
<style scoped>
.manual-diagram { min-width: 0; margin: 24px 0; border: 1px solid #dfe5ef; border-radius: 10px; background: #fbfcff; overflow: hidden; }
.manual-diagram__toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 14px; color: #73809a; border-bottom: 1px solid #e8edf5; font-size: 12px; }
.manual-diagram__toolbar button { min-height: 26px; padding: 3px 10px; font-size: 12px; }
.manual-diagram__canvas { overflow: auto; padding: 20px; max-height: 580px; }
.manual-diagram__canvas :deep(svg) { display: block; margin: 0 auto; min-width: min(100%, 480px); max-width: none; height: auto; }
.manual-diagram--expanded .manual-diagram__canvas { max-height: none; }
.manual-diagram--expanded .manual-diagram__canvas :deep(svg) { min-width: 900px; }
.manual-diagram p, .manual-diagram details { margin: 14px; }
.manual-diagram pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
