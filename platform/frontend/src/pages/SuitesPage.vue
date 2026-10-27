<template><section class="page-grid"><ScenarioAssetsPanel kind="suites" @saved="onSaved" @selected="appStore.rememberAsset" /></section></template>
<script setup lang="ts">
import ScenarioAssetsPanel from '@/components/ScenarioAssetsPanel.vue';
import { useAppStore } from '@/stores/app';
const appStore=useAppStore();
function onSaved(asset: {id:string}) { appStore.rememberAsset(asset.id); }
</script>
