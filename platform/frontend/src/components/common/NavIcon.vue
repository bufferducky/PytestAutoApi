<template>
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path :d="paths[name]" />
  </svg>
</template>
<script setup lang="ts">
import type { RouteName } from '@/types/platform';
defineProps<{ name: RouteName }>();
const paths: Record<RouteName, string> = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  cases: 'M8 3h8l4 4v14H4V3h4 M15 3v5h5 M8 12h8 M8 16h5',
  suites: 'M3 5h7l2 3h9v12H3z M3 8h9 M7 12h10 M7 16h7',
  environments: 'M4 4h16v6H4z M4 14h16v6H4z M8 7h.01 M8 17h.01 M12 7h5 M12 17h5',
  runs: 'M9 5l10 7-10 7z M4 4v16',
  manual: 'M12 5C8 2 4 3 2 4v15c3-2 7-2 10 0 3-2 7-2 10 0V4c-2-1-6-2-10 1 M12 5v14 M5 7h3 M5 11h3 M16 7h3 M16 11h3',
  schedules: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
};
</script>
