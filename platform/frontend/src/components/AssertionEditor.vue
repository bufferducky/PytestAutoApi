<template>
  <section class="assertions">
    <h4>响应断言 <span>{{ rows.length }} 条规则</span></h4>
    <p v-if="error || jsonError" class="state-banner state-banner--error" role="alert">{{ error || jsonError }}</p>
    <fieldset v-for="(row,index) in rows" :key="index">
      <legend>断言 {{ index + 1 }}</legend>
      <label>断言名称 <input :value="row.name" @input="patch(index,{name:text($event)})" /></label>
      <label><span class="field-caption"><span>来源</span><HelpHint topic="assertSource" /></span><select :value="row.source || 'response_body'" @change="patch(index,{source:text($event)})" aria-label="来源">
        <option value="response_body">响应体</option><option value="response_headers">响应头</option><option value="status_code">HTTP 状态</option><option value="context">运行上下文</option>
      </select></label>
      <label><span class="field-caption"><span>字段路径</span><HelpHint topic="selector" /></span><input :value="row.selector || ''" @input="patch(index,{selector:text($event)})" aria-label="字段路径" /></label>
      <label><span class="field-caption"><span>比较规则</span><HelpHint topic="operator" /></span><select :value="row.operator || 'equals'" @change="patch(index,{operator:text($event)})" aria-label="比较规则">
        <option v-for="operator in operators" :key="operator" :value="operator">{{ operator }}</option>
      </select></label>
      <label><span class="field-caption"><span>期望 JSON</span><HelpHint topic="expected" /></span><input :value="JSON.stringify(row.expected ?? null)" @change="expected(index,text($event))" aria-label="期望 JSON" /></label>
      <details class="assertion-advanced"><summary aria-label="高级断言选项">高级断言选项<HelpHint topic="invariant" /></summary><div class="assertion-fields">
      <label><span class="field-caption"><span>或期望引用（params/fixtures/outputs）</span><HelpHint topic="expectedRef" /></span><input :value="row.expected_ref || ''" @input="patch(index,{expected_ref:text($event) || null})" aria-label="或期望引用（params/fixtures/outputs）" /></label>
      <label><span class="field-caption"><span>显式值类型</span><HelpHint topic="valueType" /></span><select :value="row.value_type || 'native'" @change="patch(index,{value_type:text($event)})" aria-label="显式值类型"><option>native</option><option>decimal</option><option>datetime</option></select></label>
      <label><span class="field-caption"><span>容差（时间为秒）</span><HelpHint topic="tolerance" /></span><input type="number" min="0" step="any" :value="row.tolerance || 0" @input="patch(index,{tolerance:Number(text($event))})" aria-label="容差（时间为秒）" /></label>
      <label><span class="field-caption"><span>业务不变量</span><HelpHint topic="invariant" /></span><select :value="row.rule_ref || ''" @change="patch(index,{rule_ref:text($event) || null})" aria-label="业务不变量">
        <option value="">普通比较</option><option>count_delta@1</option><option>unchanged@1</option><option>relation@1</option>
      </select></label>
      <label><span class="field-caption"><span>前置快照引用</span><HelpHint topic="baseline" /></span><input :value="row.baseline_ref || ''" @input="patch(index,{baseline_ref:text($event) || null})" aria-label="前置快照引用" /></label>
      </div></details>
      <p class="assertion-tip">精确对象选择和时区/单位可在下面 JSON 中设置 select_by、normalization；集合按 key 比较用 extras.key。</p>
      <button type="button" @click="remove(index)">删除断言</button>
    </fieldset>
    <button type="button" @click="add">添加断言</button>
    <details><summary aria-label="编辑完整断言 JSON">编辑完整断言 JSON<HelpHint topic="assertJson" /></summary><label><span class="field-caption"><span>完整结构化断言 JSON（保留高级字段）</span><HelpHint topic="assertJson" /></span><textarea :value="modelValue" @input="$emit('update:modelValue',text($event))" rows="5" aria-label="完整结构化断言 JSON（保留高级字段）" /></label></details>
  </section>
</template>
<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { computed, ref } from 'vue';
interface Rule { name: string; selector?: string; source?: string; operator?: string; expected?: unknown;
  expected_ref?: string | null; value_type?: string; tolerance?: number; rule_ref?: string | null; baseline_ref?: string | null;
  [key: string]: unknown; }
const props = defineProps<{modelValue: string}>();
const emit = defineEmits<{(event: 'update:modelValue', value: string): void}>();
const error = ref('');
const jsonError = computed(() => { try { const data: unknown = JSON.parse(props.modelValue); return Array.isArray(data) && data.every(row => row && typeof row === 'object' && typeof row.name === 'string') ? '' : '断言 JSON 必须为包含名称的对象数组。'; } catch { return '断言 JSON 格式错误，请展开完整 JSON 修复。'; } });
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
.assertions { display: grid; gap: 12px; min-width: 0; }
h4 { display: flex; flex-wrap: wrap; gap: 10px; margin: 0; font-size: 13px; }
h4 span { font-size: 11px; font-weight: 400; color: var(--color-ink-subtle); }
fieldset, .assertion-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
label { display: grid; gap: 6px; }
fieldset > :is(details, p, button) { grid-column: 1 / -1; }
fieldset > button { justify-self: end; }
.assertion-fields { padding: 0 12px 12px; }
.assertion-tip { margin: 0; font-size: 11px; color: var(--color-ink-subtle); }
details { min-width: 0; border: 1px solid var(--color-border); border-radius: 6px; }
@media (max-width:540px) { fieldset, .assertion-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
