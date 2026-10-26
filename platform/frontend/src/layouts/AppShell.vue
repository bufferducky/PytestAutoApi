<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到页面内容</a>
    <SideNav />
    <div class="app-shell__body">
      <AppHeader />
      <main id="main-content" class="app-shell__main" tabindex="-1"><RouterView /></main>
      <footer class="app-shell__footer">TestFlow <span>·</span> 管理资产，执行测试，追溯证据</footer>
    </div>
  </div>
</template>
<script setup lang="ts">
import AppHeader from '@/components/layout/AppHeader.vue';
import SideNav from '@/components/layout/SideNav.vue';
</script>
<style scoped>
.app-shell { display: grid; grid-template-columns: 224px minmax(0, 1fr); min-height: 100dvh; }
.app-shell__body { min-width: 0; padding: 0 24px; }
.app-shell__main { position: relative; min-width: 0; max-width: 1600px; margin: 0 auto; }
.app-shell__footer { padding: 20px 0 16px; color: #929baa; font-size: 11px; display: flex; gap: 7px; }
.skip-link { position: fixed; top: -60px; left: 16px; padding: 10px 16px; background: white; z-index: 20; }
.skip-link:focus { top: 12px; }
@media (max-width: 1080px) { .app-shell { grid-template-columns: minmax(0, 1fr); } .app-shell__body { padding: 0 20px; } }
@media (max-width: 540px) { .app-shell__body { padding: 0 12px; } }
</style>
