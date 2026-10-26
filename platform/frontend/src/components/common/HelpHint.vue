<template>
  <span ref="anchor" class="help-hint" @mouseenter="show" @mouseleave="scheduleHide">
    <button type="button" class="help-hint__trigger" :aria-label="`查看帮助：${content.title}`" :aria-describedby="visible ? tooltipId : undefined" :aria-expanded="visible" @click.stop.prevent="toggle" @focus="show" @blur="hide" @keydown.esc.stop.prevent="hide">
      <svg viewBox="0 0 20 20" width="15" height="15" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4" /><path d="M7.9 7.8a2.1 2.1 0 1 1 3.2 1.8c-.8.5-1.1.8-1.1 1.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" /><circle cx="10" cy="13.5" r=".8" fill="currentColor" /></svg>
    </button>
    <Teleport to="body">
      <div v-if="visible" :id="tooltipId" ref="tooltip" role="tooltip" class="help-tooltip" :style="position" @mouseenter="cancelHide" @mouseleave="scheduleHide">
        <strong>{{ content.title }}</strong><p>{{ content.text }}</p>
      </div>
    </Teleport>
  </span>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue';
import { helpTopics, type HelpTopic } from '@/content/helpTopics';
const props = defineProps<{ topic: HelpTopic }>();
const content = computed(() => helpTopics[props.topic]);
const tooltipId = `help-${useId()}`;
const anchor = ref<HTMLElement | null>(null), tooltip = ref<HTMLElement | null>(null);
const visible = ref(false), pinned = ref(false);
const position = ref({ left: '12px', top: '12px', width: '320px' });
let hideTimer: ReturnType<typeof setTimeout> | undefined;
function cancelHide() { clearTimeout(hideTimer); }
function place() {
  if (!anchor.value || !tooltip.value) return;
  const box = anchor.value.getBoundingClientRect();
  const width = Math.min(340, window.innerWidth - 24);
  const height = tooltip.value.getBoundingClientRect().height;
  const left = Math.max(12, Math.min(box.left + box.width / 2 - width / 2, window.innerWidth - width - 12));
  const below = box.bottom + 8;
  const top = below + height <= window.innerHeight - 12 ? below : Math.max(12, box.top - height - 8);
  position.value = { left: `${left}px`, top: `${top}px`, width: `${width}px` };
}
function outside(event: PointerEvent) {
  const target = event.target;
  if (target instanceof Node && !anchor.value?.contains(target) && !tooltip.value?.contains(target)) hide();
}
function escape(event: KeyboardEvent) { if (event.key === 'Escape') hide(); }
function onScroll(event: Event) {
  if (event.target instanceof Node && tooltip.value?.contains(event.target)) return;
  const box = anchor.value?.getBoundingClientRect();
  if (!box || box.width === 0 || box.bottom < 0 || box.top > window.innerHeight) hide();
  else place();
}
async function show() {
  cancelHide();
  position.value.width = `${Math.min(340, window.innerWidth - 24)}px`;
  if (!visible.value) {
    visible.value = true;
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    // Teleport 避免被表格/details 裁切；滚动时跟随可见锚点，离开视口后关闭。
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', hide);
  }
  await nextTick();
  place();
}
function hide() {
  cancelHide(); visible.value = false; pinned.value = false;
  document.removeEventListener('pointerdown', outside);
  document.removeEventListener('keydown', escape);
  window.removeEventListener('scroll', onScroll, true);
  window.removeEventListener('resize', hide);
}
function scheduleHide() { if (!pinned.value) hideTimer = setTimeout(hide, 140); }
function toggle() { if (pinned.value) hide(); else { pinned.value = true; void show(); } }
onBeforeUnmount(hide);
</script>
<style scoped>
.help-hint { display: inline-flex; flex: 0 0 auto; vertical-align: middle; }
.help-hint__trigger { display: inline-flex; align-items: center; justify-content: center; min-height: 22px; width: 22px; height: 22px; padding: 2px; border: 0; border-radius: 50%; background: transparent; color: #8691a4; cursor: help; font-size: 12px; line-height: 1; }
.help-hint__trigger:hover, .help-hint__trigger[aria-expanded='true'] { color: var(--color-accent-strong); background: var(--color-accent-soft); border: 0; }
.help-tooltip { position: fixed; z-index: 1000; max-width: calc(100vw - 24px); max-height: min(420px, calc(100dvh - 24px)); overflow-y: auto; padding: 14px 16px; border: 1px solid #dce2ec; border-radius: 9px; background: #fff; box-shadow: 0 8px 32px rgb(16 24 40 / 15%); color: var(--color-ink-base); font: 13px/1.75 var(--font-sans); text-align: left; overflow-wrap: anywhere; }
.help-tooltip strong { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 650; }
.help-tooltip p { margin: 0; color: var(--color-ink-muted); white-space: pre-line; }
</style>
