<template>
  <section class="assertions">
    <p v-if="error" class="state-banner state-banner--error">{{ error }}</p>
    <fieldset v-for="(row,index) in rows" :key="index">
      <legend>断言 {{ index + 1 }}</legend>
      <label>断言名称 <input :value="row.name" @input="patch(index,{name:text($event)})" /></label>
      <label>来源 <select :value="row.source || 'response_body'" @change="patch(index,{source:text($event)})">
        <option value="response_body">响应体</option><option value="response_headers">响应头</option><option value="status_code">HTTP 状态</option><option value="context">运行上下文</option>
      </select></label>
      <label>字段路径 <input :value="row.selector || ''" @input="patch(index,{selector:text($event)})" /></label>
      <label>比较规则 <select :value="row.operator || 'equals'" @change="patch(index,{operator:text($event)})">
        <option v-for="operator in operators" :key="operator" :value="operator">{{ operator }}</option>
      </select></label>
      <label>期望 JSON <input :value="JSON.stringify(row.expected ?? null)" @change="expected(index,text($event))" /></label>
      <label>或期望引用（params/fixtures/outputs）<input :value="row.expected_ref || ''" @input="patch(index,{expected_ref:text($event) || null})" /></label>
      <label>显式值类型 <select :value="row.value_type || 'native'" @change="patch(index,{value_type:text($event)})"><option>native</option><option>decimal</option><option>datetime</option></select></label>
      <label>容差（时间为秒）<input type="number" min="0" step="any" :value="row.tolerance || 0" @input="patch(index,{tolerance:Number(text($event))})" /></label>
      <label>业务不变量 <select :value="row.rule_ref || ''" @change="patch(index,{rule_ref:text($event) || null})">
        <option value="">普通比较</option><option>count_delta@1</option><option>unchanged@1</option><option>relation@1</option>
      </select></label>
      <label>前置快照引用 <input :value="row.baseline_ref || ''" @input="patch(index,{baseline_ref:text($event) || null})" /></label>
      <p>精确对象选择和时区/单位可在下面 JSON 中设置 select_by、normalization；集合按 key 比较用 extras.key。</p>
      <button type="button" @click="remove(index)">删除断言</button>
    </fieldset>
    <button type="button" @click="add">添加断言</button>
    <label>完整结构化断言 JSON（保留高级字段）<textarea :value="modelValue" @input="$emit('update:modelValue',text($event))" rows="5" /></label>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
interface Rule { name: string; selector?: string; source?: string; operator?: string; expected?: unknown;
  expected_ref?: string | null; value_type?: string; tolerance?: number; rule_ref?: string | null; baseline_ref?: string | null;
  [key: string]: unknown; }
const props = defineProps<{modelValue: string}>();
const emit = defineEmits<{(event: 'update:modelValue', value: string): void}>();
const error = ref('');
const operators = ['equals','not_equals','contains','not_contains','exists','is_null','is_missing','type_is','schema','set_equals','keyed_equals','unique','greater_than','greater_or_equal','less_than','less_or_equal'];
const rows = computed<Rule[]>(() => { try { const data: unknown = JSON.parse(props.modelValue); return Array.isArray(data) ? data.filter((row): row is Rule => typeof row === 'object' && row !== null && 'name' in row) : []; } catch { return []; } });
const text = (event: Event) => (event.target as HTMLInputElement).value;
function validRows(): Rule[] | null { try { const data: unknown = JSON.parse(props.modelValue); if (!Array.isArray(data) || !data.every(row => typeof row === 'object' && row !== null && typeof row.name === 'string')) throw new Error(); error.value = ''; return [...rows.value]; } catch { error.value = '请先修复断言 JSON，避免覆盖未保存内容。'; return null; } }
function patch(index: number, changes: Partial<Rule>) { const value = validRows(); if (!value) return; const current = value[index]; if (!current) return; value[index] = Object.assign({}, current, changes); emit('update:modelValue', JSON.stringify(value, null, 2)); }
function expected(index: number, value: string) { try { patch(index, {expected:JSON.parse(value)}); } catch { error.value = '期望值必须是有效 JSON。'; } }
function add() { const value = validRows(); if (!value) return; value.push({name:'业务验证',selector:'code',operator:'equals',expected:200}); emit('update:modelValue',JSON.stringify(value,null,2)); }
function remove(index: number) { const value = validRows(); if (!value) return; value.splice(index,1); emit('update:modelValue',JSON.stringify(value,null,2)); }
</script>
<style scoped>
fieldset { display:grid; gap:.4rem; margin-block:.6rem; } label { display:grid; gap:.25rem; }
input,select,textarea { max-width:100%; padding:.4rem; }
</style>
