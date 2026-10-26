<template>
  <fieldset><legend>环境变量</legend>
    <p>保留字符串、数字、布尔值及嵌套 JSON 类型；凭证请使用秘密引用。</p>
    <label>编辑方式<select :value="mode" aria-label="编辑方式" @change="changeMode"><option value="rows">结构化</option><option value="json">高级 JSON</option></select></label>
    <label v-if="mode === 'json'">变量 JSON<textarea :value="modelValue" rows="10" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" /></label>
    <template v-else>
      <div v-for="(row, index) in rows" :key="index" class="variable-row">
        <label>变量名<input v-model="row.key" @input="publish" /></label>
        <label>类型<select v-model="row.type" aria-label="类型" @change="changeType(row)"><option v-for="type in types" :key="type" :value="type">{{ type }}</option></select></label>
        <label>值<textarea v-model="row.text" rows="2" @input="publish" /></label>
        <button type="button" @click="rows.splice(index, 1); publish()">移除</button>
      </div>
      <button type="button" @click="rows.push({ key: '', type: 'string', text: '' }); publish()">添加变量</button>
    </template>
    <p v-if="error" role="alert">{{ error }}</p>
  </fieldset>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue';
const props = defineProps<{ modelValue: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string]; validity: [valid: boolean] }>();
const mode = ref('rows'), error = ref('');
function changeMode(event: Event) {
  const select = event.target as HTMLSelectElement;
  if (error.value) {
    select.value = mode.value;
    error.value = '请先修复当前编辑内容后再切换方式。' + error.value.replace('请先修复当前编辑内容后再切换方式。', '');
    return;
  }
  mode.value = select.value;
}
const types = ['string', 'number', 'boolean', 'null', 'object', 'array'];
interface Row { key: string; type: string; text: string }
const rows = ref<Row[]>([]);
let lastPublished = '';
function parseObject(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('环境变量必须为 JSON 对象');
  return value as Record<string, unknown>;
}
watch(() => props.modelValue, (text) => {
  if (text === lastPublished) return;
  try {
    rows.value = Object.entries(parseObject(text)).map(([key, value]) => ({ key, type: value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value, text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }));
    error.value = ''; emit('validity', true);
  } catch (cause) { error.value = String(cause); emit('validity', false); }
}, { immediate: true });
function changeType(row: Row) {
  row.text = ({ string: '', number: '0', boolean: 'false', null: 'null', object: '{}', array: '[]' } as Record<string, string>)[row.type] ?? '';
  publish();
}
function publish() {
  try {
    const entries: [string, unknown][] = [];
    for (const row of rows.value) {
      if (!row.key.trim()) throw new Error('变量名不能为空');
      if (entries.some(([key]) => key === row.key)) throw new Error(`变量名重复：${row.key}`);
      const value: unknown = row.type === 'string' ? row.text : JSON.parse(row.text);
      const actual = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
      if (actual !== row.type || (typeof value === 'number' && !Number.isFinite(value))) throw new Error(`${row.key} 的值不符合 ${row.type} 类型`);
      entries.push([row.key, value]);
    }
    lastPublished = JSON.stringify(Object.fromEntries(entries), null, 2);
    emit('update:modelValue', lastPublished); error.value = ''; emit('validity', true);
  } catch (cause) { error.value = String(cause); emit('validity', false); }
}
</script>
<style scoped>
fieldset { min-width:0; display:grid;gap:.75rem; } label {display:grid;gap:.3rem;min-width:0;} .variable-row {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.7fr) minmax(0,2fr) auto;gap:.5rem;align-items:end;} textarea,select,input {width:100%;min-width:0;} p {overflow-wrap:anywhere;} @media(max-width:720px){.variable-row{grid-template-columns:minmax(0,1fr);}}
</style>
