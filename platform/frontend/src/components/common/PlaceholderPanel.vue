<template>
  <section class="panel">
    <header class="panel__header">
      <div>
        <h2 class="panel__title">{{ title }}</h2>
        <p v-if="description" class="panel__description">{{ description }}</p>
      </div>
      <slot name="actions" />
    </header>

    <div class="panel__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<style scoped>
.panel {
  padding: 22px;
  border-radius: var(--radius-large);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-soft);
}

.panel__header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.panel__title {
  margin: 0;
  font-size: 15px;
}

.panel__description {
  margin: 0.45rem 0 0;
  color: var(--color-ink-muted);
  line-height: 1.7;
  font-size: 12px;
}

.panel__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem;
}
@media (max-width:540px) { .panel { padding: 16px; } }
</style>

