<template>
  <span ref="anchor" class="help-hint" @mouseenter="show" @mouseleave="scheduleHide" @focusout="focusOut">
    <button ref="trigger" type="button" class="help-hint__trigger" :aria-label="`查看帮助：${content.title}`" :aria-describedby="visible ? descriptionId : undefined" :aria-controls="visible ? popupId : undefined" aria-haspopup="dialog" :aria-expanded="visible" @click.stop.prevent="toggle" @focus="focusTrigger" @keydown="triggerKeydown">
      <svg viewBox="0 0 20 20" width="15" height="15" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4" /><path d="M7.9 7.8a2.1 2.1 0 1 1 3.2 1.8c-.8.5-1.1.8-1.1 1.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" /><circle cx="10" cy="13.5" r=".8" fill="currentColor" /></svg>
    </button>
    <Teleport to="body">
      <div v-if="visible" :id="popupId" ref="tooltip" role="dialog" :aria-label="`帮助：${content.title}`" class="help-tooltip" :style="position" @mouseenter="cancelHide" @mouseleave="scheduleHide" @focusin="cancelHide" @focusout="focusOut">
        <div :id="descriptionId" role="tooltip"><strong>{{ content.title }}</strong><p>{{ content.text }}</p></div>
        <a ref="manualLink" class="help-tooltip__manual" :href="manualHref" target="_blank" rel="noopener" @click.stop @keydown.shift.tab.prevent="trigger?.focus()">查看完整手册 <span aria-hidden="true">↗</span><small>在新标签页打开</small></a>
      </div>
    </Teleport>
  </span>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue';
import { useRouter } from 'vue-router';
import { helpTopics, type HelpTopic } from '@/content/helpTopics';
import { manualTopicLinks } from '@/content/manual/topicLinks';
const props = defineProps<{ topic: HelpTopic }>();
const router = useRouter();
const content = computed(() => helpTopics[props.topic]);
const manualHref = computed(() => {
  const destination = manualTopicLinks[props.topic];
  return router.resolve({ name: 'manual', params: { articleId: destination.articleId }, hash: `#${destination.sectionId}` }).href;
});
const id = useId(), descriptionId = `help-description-${id}`, popupId = `help-popup-${id}`;
const anchor = ref<HTMLElement | null>(null), tooltip = ref<HTMLElement | null>(null), trigger = ref<HTMLButtonElement | null>(null), manualLink = ref<HTMLAnchorElement | null>(null);
const visible = ref(false), pinned = ref(false);
const position = ref({ left: '12px', top: '12px', width: '320px' });
let hideTimer: ReturnType<typeof setTimeout> | undefined, suppressFocus = false;
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
function inside(target: EventTarget | null) { return target instanceof Node && (anchor.value?.contains(target) || tooltip.value?.contains(target)); }
function outside(event: PointerEvent) { if (!inside(event.target)) hide(); }
function escape(event: KeyboardEvent) {
  if (event.key !== 'Escape') return;
  const restore = tooltip.value?.contains(document.activeElement);
  hide();
  if (restore) { suppressFocus = true; trigger.value?.focus(); suppressFocus = false; }
}
function focusTrigger() { if (!suppressFocus) void show(); }
function focusOut(event: FocusEvent) {
  // 浮层通过 Teleport 挂在 body：按钮失焦到手册链接时属于同一交互区域。
  if (!inside(event.relatedTarget)) { cancelHide(); hideTimer = setTimeout(hide, 0); }
}
function triggerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); hide(); }
  if (event.key === 'Tab' && !event.shiftKey && visible.value) { event.preventDefault(); manualLink.value?.focus(); }
}
function onScroll(event: Event) {
  if (event.target instanceof Node && tooltip.value?.contains(event.target)) return;
  const box = anchor.value?.getBoundingClientRect();
  if (!box || box.width === 0 || box.bottom < 0 || box.top > window.innerHeight) hide();
  else place();
}
function otherHelp(event: Event) { if ((event as CustomEvent<string>).detail !== popupId) hide(); }
async function show() {
  cancelHide();
  document.dispatchEvent(new CustomEvent('testflow:help-open', { detail: popupId }));
  position.value.width = `${Math.min(340, window.innerWidth - 24)}px`;
  if (!visible.value) {
    visible.value = true;
    document.addEventListener('testflow:help-open', otherHelp);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', hide);
  }
  await nextTick(); place();
}
function hide() {
  cancelHide(); visible.value = false; pinned.value = false;
  document.removeEventListener('testflow:help-open', otherHelp);
  document.removeEventListener('pointerdown', outside);
  document.removeEventListener('keydown', escape);
  window.removeEventListener('scroll', onScroll, true);
  window.removeEventListener('resize', hide);
}
function scheduleHide() {
  if (!pinned.value && !inside(document.activeElement)) hideTimer = setTimeout(hide, 160);
}
function toggle() { if (pinned.value) hide(); else { pinned.value = true; void show(); } }
onBeforeUnmount(hide);
</script>
<style scoped>
.help-hint { display: inline-flex; flex: 0 0 auto; vertical-align: middle; }
.help-hint__trigger { display: inline-flex; align-items: center; justify-content: center; min-height: 22px; width: 22px; height: 22px; padding: 2px; border: 0; border-radius: 50%; background: transparent; color: #8691a4; cursor: help; font-size: 12px; line-height: 1; }
.help-hint__trigger:hover, .help-hint__trigger[aria-expanded='true'] { color: var(--color-accent-strong); background: var(--color-accent-soft); border: 0; }
.help-tooltip { position: fixed; z-index: 1000; max-width: calc(100vw - 24px); max-height: min(480px, calc(100dvh - 24px)); overflow-y: auto; padding: 14px 16px; border: 1px solid #dce2ec; border-radius: 9px; background: #fff; box-shadow: 0 8px 32px rgb(16 24 40 / 15%); color: var(--color-ink-base); font: 13px/1.75 var(--font-sans); text-align: left; overflow-wrap: anywhere; }
.help-tooltip strong { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 650; }
.help-tooltip p { margin: 0; color: var(--color-ink-muted); white-space: pre-line; }
.help-tooltip__manual { display: flex; align-items: center; gap: 6px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e8edf5; color: var(--color-accent-strong); text-decoration: none; font-weight: 600; }
.help-tooltip__manual:hover { text-decoration: underline; }.help-tooltip__manual small { margin-left: auto; color: #8b96a8; font-size: 10px; font-weight: 400; }
</style>
