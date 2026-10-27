<template>
  <section class="json-result" :aria-label="title"><div class="section-heading"><h3>{{ title }}</h3><el-button native-type="button" @click="copy">{{ copied ? '已复制' : '复制记录' }}</el-button></div>
    <el-alert v-if="summary" :title="summary" :type="failed ? 'error' : 'info'" :closable="false" show-icon />
    <el-descriptions v-if="facts.length" :column="2" border><el-descriptions-item v-for="fact in facts" :key="fact.key" :label="fact.key">{{ fact.value }}</el-descriptions-item></el-descriptions>
    <ul v-if="issues.length" class="result-issues"><li v-for="(issue,index) in issues" :key="index">{{ typeof issue === 'string' ? issue : JSON.stringify(issue) }}</li></ul>
    <details><summary>原始记录</summary><pre>{{ text }}</pre></details><p v-if="copyError" role="alert">{{ copyError }}</p>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
const props = withDefaults(defineProps<{ value: unknown; title?: string }>(), { title: '操作结果' });
const copied=ref(false), copyError=ref('');
const data=computed<Record<string, unknown>>(() => { try { const value=typeof props.value==='string'?JSON.parse(props.value):props.value; return value && typeof value==='object'&&!Array.isArray(value) ? value : {}; } catch { return {}; } });
const text=computed(() => typeof props.value==='string'?props.value:JSON.stringify(props.value,null,2));
const issues=computed<unknown[]>(() => [data.value.errors,data.value.blockers,data.value.warnings].flatMap(value => Array.isArray(value)?value:[]));
const failed=computed(() => data.value.valid===false || data.value.passed===false || (Array.isArray(data.value.errors)&&data.value.errors.length>0));
const summary=computed(() => String(data.value.message || data.value.note || (data.value.valid===true?'预检通过':data.value.valid===false?'预检未通过，请修复以下问题':'操作结果已更新，可查看摘要与原始记录')));
const names:Record<string,string>={valid:'校验通过',status:'状态',run_id:'运行 ID',environment_id:'环境',version:'版本',configuration:'配置',connection:'连接',permission:'权限',eligible_for_release:'可作为发布证据'};
const facts=computed(() => Object.entries(data.value).filter(([,v]) => ['string','number','boolean'].includes(typeof v)).slice(0,12).map(([key,value]) => ({key:names[key]||key,value:typeof value==='boolean'?(value?'是':'否'):String(value)})));
async function copy(){try{await navigator.clipboard.writeText(text.value);copied.value=true;copyError.value='';}catch{copyError.value='复制失败，请展开原始记录后手动复制。';}}
</script>
<style scoped>.json-result {display:grid;gap:12px;padding:16px;background:white;border:1px solid var(--color-border);border-radius:8px;min-width:0}.json-result h3{margin:0;font-size:14px}.result-issues{margin:0;padding-left:20px;overflow-wrap:anywhere}pre{max-height:380px;white-space:pre-wrap;overflow-wrap:anywhere}</style>
