<template>
  <header class="app-header">
    <el-breadcrumb class="app-header__breadcrumb" separator="/"><el-breadcrumb-item>工作空间</el-breadcrumb-item><el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item></el-breadcrumb>
    <div class="app-header__heading"><div><h1>{{ route.meta.title }}</h1><p>{{ route.meta.description }}</p></div></div>
  </header>
</template>
<script setup lang="ts">
import { useRoute } from 'vue-router';
const route = useRoute();
</script>
<style scoped>
.app-header { padding: 16px 0 18px; }
.app-header__breadcrumb { display: flex; gap: 10px; font-size: 11px; color: var(--color-ink-subtle); margin-bottom: 10px; }
.app-header__breadcrumb strong { font-weight: 500; color: var(--color-ink-muted); }
.app-header__heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.app-header__heading > div { min-width: 0; }
h1 { margin: 0; font-size: 24px; letter-spacing: -.6px; line-height: 1.3; font-weight: 650; }
p { margin: 7px 0 0; font-size: 13px; color: var(--color-ink-subtle); }
.app-header__badge { flex-shrink: 0; padding: 5px 9px; color: var(--color-ink-subtle); background: white; border: 1px solid var(--color-border); border-radius: 5px; font-size: 11px; }
@media (max-width: 540px) { .app-header { padding: 18px 0; } .app-header__breadcrumb { margin-bottom: 12px; } .app-header__badge { display: none; } h1 { font-size: 22px; } }
</style>

<style scoped>.app-header{padding:14px 0}.app-header h1{font-size:21px}.app-header p{margin-top:5px;font-size:12px}.app-header__breadcrumb{margin-bottom:8px;font-size:11px}</style>