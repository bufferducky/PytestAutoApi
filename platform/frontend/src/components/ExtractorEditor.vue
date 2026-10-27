<template>
  <section class="extractor-editor"><h4>变量提取 · {{ rows.length }} 条</h4>
    <p v-if="error" role="alert">{{ error }}</p>
    <fieldset v-for="(row, index) in rows" :key="index">
      <legend>提取 {{ index + 1 }}</legend>
      <label>名称 <UiInput :value="String(row.name ?? '')" @input="patch(index, 'name', value($event))"  /></label>
      <label>来源 <UiSelect :value="String(row.source || 'response_body')" @change="patch(index, 'source', value($event))"><option value="response_body">响应体</option><option value="response_headers">响应头</option></UiSelect></label>
      <label>字段路径 <UiInput :value="String(row.selector ?? '')" @input="patch(index, 'selector', value($event))"  /></label>
      <label>输出路径 <UiInput :value="String(row.target ?? '')" @input="patch(index, 'target', value($event))"  /></label>
      <label><input type="checkbox" :checked="row.required !== false" @change="patch(index, 'required', ($event.target as HTMLInputElement).checked)" /> 必须存在</label>
      <el-button native-type="button" @click="remove(index)">删除提取</el-button>
    </fieldset>
    <el-button native-type="button" @click="add">添加变量提取</el-button>
    <details><summary>高级提取 JSON</summary><UiInput type="textarea" :value="modelValue" aria-label="提取 JSON（写 outputs.本步骤ID.*）" rows="4" @input="$emit('update:modelValue', value($event))"  /></details>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
const props = defineProps<{ modelValue: string; stepId: string }>();
const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>();
const error = ref('');
function parseRows(): Record<string, unknown>[] {
  const data: unknown = JSON.parse(props.modelValue);
  if (!Array.isArray(data) || !data.every(row => row && typeof row === 'object' && !Array.isArray(row))) throw new Error('提取 JSON 必须为对象数组，请先修复，避免覆盖高级字段。');
  return data;
}
const rows = computed(() => { try { return parseRows(); } catch { return []; } });
const value = (event: Event) => (event.target as HTMLInputElement).value;
function change(edit: (rows: Record<string, unknown>[]) => void) {
  try { const data = parseRows(); edit(data); emit('update:modelValue', JSON.stringify(data, null, 2)); error.value = ''; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '提取 JSON 无效'; }
}
function patch(index: number, key: string, value: unknown) { change(rows => { rows[index] = { ...rows[index], [key]: value }; }); }
function remove(index: number) { change(rows => { rows.splice(index, 1); }); }
function add() { change(rows => rows.push({ name: '变量', source: 'response_body', selector: 'data.id', target: `outputs.${props.stepId}.id`, required: true })); }
</script>
<style scoped>
details, fieldset { min-width: 0; } fieldset { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; } label { display: grid; gap: 4px; min-width: 0; } textarea { width: 100%; } @media(max-width:540px) { fieldset { grid-template-columns: minmax(0, 1fr); } }
</style>
