<template>
  <aside class="side-nav">
    <RouterLink to="/dashboard" class="side-nav__brand" aria-label="TestFlow 工作台首页">
      <span class="side-nav__mark"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true"><path d="M5 5h14M12 5v14M5 12h5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" /></svg></span>
      <span><strong class="side-nav__title">TestFlow<span class="side-nav__edition">工作台</span></strong><span class="side-nav__caption">个人 API 测试</span></span>
    </RouterLink>
    <div class="side-nav__navigation">
      <p class="side-nav__group">测试工作空间</p>
      <nav class="side-nav__menu" aria-label="平台主导航">
        <RouterLink v-for="item in appStore.navigation" :key="item.name" :to="{ name: item.name }" class="side-nav__item" :class="{ 'side-nav__item--active': route.name === item.name }" :aria-current="route.name === item.name ? 'page' : undefined">
          <NavIcon :name="item.name" /><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <RouterLink to="/extensions" class="side-nav__extension" :aria-current="route.name === 'extensions' ? 'page' : undefined">扩展工具 <span aria-hidden="true">↗</span></RouterLink>
    </div>
    <div class="side-nav__footer"><span class="side-nav__avatar">YS</span><div><strong>个人工作空间</strong><small>测试资产与执行记录</small></div></div>
  </aside>
</template>
<script setup lang="ts">
import { useRoute } from 'vue-router';
import NavIcon from '@/components/common/NavIcon.vue';
import { useAppStore } from '@/stores/app';
const route = useRoute();
const appStore = useAppStore();
</script>
<style scoped>
.side-nav { position: sticky; top: 0; display: grid; grid-template-rows: auto auto 1fr; gap: 32px; height: 100dvh; padding: 26px 16px 18px; background: #fff; border-right: 1px solid var(--color-border); }
.side-nav__brand { display: flex; gap: 10px; align-items: center; color: var(--color-ink-base); text-decoration: none; padding: 0 8px; }
.side-nav__mark { display: grid; place-items: center; width: 34px; height: 34px; flex-shrink: 0; background: var(--color-accent-strong); color: white; border-radius: 9px; }
.side-nav__title { display: flex; align-items: center; gap: 8px; font-size: 18px; letter-spacing: -.6px; }
.side-nav__edition { font-size: 10px; font-weight: 500; letter-spacing: 0; padding: 0 5px; color: var(--color-ink-subtle); border: 1px solid var(--color-border); border-radius: 4px; }
.side-nav__caption { display: block; color: var(--color-ink-subtle); font-size: 10px; margin-top: 2px; }
.side-nav__group { margin: 0 12px 12px; color: #8a94a5; font-size: 11px; letter-spacing: 1px; }
.side-nav__menu { display: grid; gap: 6px; }
.side-nav__item { display: flex; align-items: center; gap: 12px; padding: 11px 13px; color: #586476; text-decoration: none; border-radius: 7px; font-size: 13px; font-weight: 500; }
.side-nav__item:hover { background: #f5f7fc; }
.side-nav__item--active { background: var(--color-accent-soft); color: var(--color-accent-strong); }
.side-nav__item--active::after { content: ''; width: 5px; height: 5px; margin-left: auto; border-radius: 50%; background: currentColor; }
.side-nav__extension { display: flex; justify-content: space-between; margin: 18px 0 0; padding: 10px 13px; border-top: 1px solid var(--color-border); color: var(--color-ink-muted); font-size: 12px; text-decoration: none; }
.side-nav__extension[aria-current="page"] { color: var(--color-accent-strong); background: var(--color-accent-soft); }
.side-nav__footer { align-self: end; display: flex; align-items: center; gap: 10px; border-top: 1px solid var(--color-border); padding: 18px 8px 0; }
.side-nav__avatar { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; color: #6377a3; background: #edf0f7; font-size: 11px; font-weight: 600; }
.side-nav__footer strong { display: block; font-size: 12px; font-weight: 500; }
.side-nav__footer small { display: block; color: var(--color-ink-subtle); font-size: 10px; }
@media (max-width: 1080px) {
  .side-nav { position: static; grid-template-rows: auto auto; height: auto; padding: 14px 20px 10px; gap: 16px; border-right: 0; border-bottom: 1px solid var(--color-border); }
  .side-nav__extension { margin: 6px 0 0; padding: 6px 10px; justify-content: flex-end; gap: 8px; }
  .side-nav__group, .side-nav__footer { align-self: end; display: none; }
  .side-nav__menu { grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 4px; }
  .side-nav__item { justify-content: center; padding: 9px 4px; gap: 6px; font-size: 12px; }
  .side-nav__item--active::after { display: none; }
}
@media (max-width: 540px) {
  .side-nav { padding: 12px; gap: 12px; }
  .side-nav__menu { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .side-nav__item svg { width: 16px; height: 16px; }
}
</style>
