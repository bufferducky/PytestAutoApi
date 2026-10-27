import { defineComponent, h, ref, onMounted, computed, Fragment, type VNode, type PropType } from 'vue';
import { ElInput, ElSelect, ElOption } from 'element-plus';

// 保留现有编辑器的 Event 边界，库控件只负责交互，不重写业务序列化。
function valueEvent(value: unknown): Event {
  const event=new Event('change');
  Object.defineProperties(event,{target:{value:{value}},currentTarget:{value:{value}}});
  return event;
}
function labelFor(element: HTMLElement | undefined): string {
  const label = element?.closest('label');
  if (!label) return '';
  return [...label.childNodes].filter(node => node.nodeType === Node.TEXT_NODE || (node instanceof HTMLElement && node.classList.contains('field-caption')))
    .map(node => node.textContent?.replace(/查看帮助：[^？]+/g, '') || '').join(' ').replace(/\s+/g, ' ').trim();
}
export const UiInput = defineComponent({
  name: 'UiInput', inheritAttrs: false,
  props: { modelValue: [String, Number], value: [String, Number], modelModifiers: Object, type: { type: String, default: 'text' } },
  emits: ['update:modelValue', 'input', 'change'],
  setup(props, { attrs, emit }) {
    const control = ref<InstanceType<typeof ElInput>>();
    const label = ref('');
    onMounted(() => { label.value = labelFor(control.value?.$el); });
    const normalize = (value: string) => props.modelModifiers?.number && value.trim() && Number.isFinite(Number(value)) ? Number(value) : value;
    return () => h(ElInput, { ...attrs, ref: control, type: props.type,
      'aria-label': attrs['aria-label'] || label.value || undefined,
      modelValue: props.modelValue ?? props.value ?? '',
      'onUpdate:modelValue': (value: string) => emit('update:modelValue', normalize(value)),
      onInput: (value: string) => emit('input', valueEvent(value)),
      onChange: (value: string) => emit('change', valueEvent(value)),
    });
  },
});
function flatten(nodes: VNode[]): VNode[] {
  return nodes.flatMap(node => node.type === Fragment && Array.isArray(node.children) ? flatten(node.children as VNode[]) : [node]);
}
function textContent(node: VNode): string {
  return typeof node.children === 'string' ? node.children : Array.isArray(node.children) ? (node.children as VNode[]).map(textContent).join('') : '';
}
export const UiSelect = defineComponent({
  name: 'UiSelect', inheritAttrs: false,
  props: { modelValue: [String, Number, Array] as PropType<string | number | unknown[]>, value: [String, Number, Array] as PropType<string | number | unknown[]>, multiple: Boolean, required: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { attrs, slots, emit }) {
    const control = ref<InstanceType<typeof ElSelect>>();
    const root = ref<HTMLElement>();
    const label = ref('');
    onMounted(() => { label.value = labelFor(root.value); });
    const current = computed(() => props.modelValue ?? props.value ?? (props.multiple ? [] : ''));
    return () => h('span', { class: ['ui-select', attrs.class], style: attrs.style, ref: root }, [
      h(ElSelect, { ...attrs, class: undefined, style: undefined, ref: control, filterable: true, multiple: props.multiple,
        'aria-label': attrs['aria-label'] || label.value || undefined, modelValue: current.value,
        placeholder: String(attrs.placeholder || textContent(flatten(slots.default?.() || []).find(node => node.type === 'option' && node.props?.value === '') || { children: '请选择' } as VNode)),
        'onUpdate:modelValue': (value: unknown) => { if (!root.value?.closest('fieldset:disabled')) emit('update:modelValue', value); },
        onChange: (value: unknown) => emit('change', valueEvent(value)),
      }, { default: () => flatten(slots.default?.() || []).filter(node => node.type === 'option').map(node => {
        const label = textContent(node);
        return h(ElOption, { key: node.key ?? node.props?.value ?? label, value: node.props?.value ?? label, label, 'data-value': String(node.props?.value ?? label), disabled: node.props?.disabled !== undefined && node.props.disabled !== false });
      }) }),
      // ElSelect 的输入用于搜索；独立校验代理维护表单 required 契约，错误时焦点回库控件。
      props.required ? h('input', { class: 'select-validity', tabindex: -1, 'aria-hidden': 'true', required: true,
        value: Array.isArray(current.value) ? current.value.join(',') : current.value || '',
        onInvalid: (event: Event) => { event.preventDefault(); control.value?.focus(); },
      }) : null,
    ]);
  },
});
