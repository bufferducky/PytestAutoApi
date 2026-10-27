<template>
  <section class="manual-page" aria-label="使用手册">
    <div class="manual-search">
      <label for="manual-search-input">想了解哪个配置？</label>
      <div class="manual-search__field"><svg viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.6" /><path d="m13 13 4 4" stroke="currentColor" stroke-width="1.6" /></svg><UiInput id="manual-search-input" v-model="query" type="search" aria-label="搜索使用手册" placeholder="搜索术语、字段或问题，例如 JSON、令牌、前置 outputs…"  /><el-button v-if="query" native-type="button" @click="query = ''">清空</el-button></div>
      <p>第一次使用可从“新手入门”顺序阅读，也可以从页面上的问号直接查到具体配置。</p>
      <div v-if="query.trim()" class="manual-search__results" aria-label="手册搜索结果">
        <p v-if="searching" role="status">正在查找…</p><p v-else-if="searchError" role="alert">{{ searchError }}</p><p v-else role="status">{{ results.length ? `找到 ${results.length} 条相关说明` : '没有找到相关说明，试试更短的关键词或界面中的英文名称。' }}</p>
        <ol v-if="results.length"><li v-for="result in results" :key="`${result.articleId}:${result.sectionId}`"><RouterLink :to="articleLocation(result.articleId, result.sectionId)" @click="selectSearch"><small>{{ groupTitle(result.article.group) }} / {{ result.article.category }} / {{ result.article.title }}</small><strong>{{ result.title || result.article.title }}</strong><span>{{ result.excerpt }}</span></RouterLink></li></ol>
      </div>
    </div>
    <div class="manual-layout">
      <aside class="manual-navigation">
        <div class="manual-navigation__heading"><strong>使用手册</strong><span>{{ manualArticles.length }} 篇说明</span></div>
        <nav aria-label="使用手册目录">
          <details v-for="group in manualGroups" :key="group.id" open class="manual-group">
            <summary>{{ group.title }}</summary>
            <div v-for="category in categories(group.id)" :key="category" class="manual-category"><p>{{ category }}</p><RouterLink v-for="article in categoryArticles(group.id, category)" :key="article.id" :to="articleLocation(article.id)" :aria-current="article.id === selectedId ? 'page' : undefined" @click="query = ''">{{ article.title }}</RouterLink></div>
          </details>
        </nav>
      </aside>
      <div class="manual-reading">
        <div v-if="loading" class="manual-state" role="status">正在打开手册…</div>
        <div v-else-if="error" class="manual-state" role="alert"><h2>暂时无法打开这篇说明</h2><p>{{ error }}</p><RouterLink :to="articleLocation(homeId)">返回新手入门</RouterLink><el-button v-if="currentArticle" native-type="button" @click="openArticle">重试</el-button></div>
        <template v-else-if="currentArticle && document">
          <article class="manual-article" aria-label="手册正文">
            <nav class="manual-breadcrumbs" aria-label="当前位置"><RouterLink :to="articleLocation(homeId)">使用手册</RouterLink><span>/</span><span>{{ groupTitle(currentArticle.group) }}</span><span>/</span><span>{{ currentArticle.category }}</span></nav>
            <header class="manual-article__header"><h1>{{ currentArticle.title }}</h1><p>{{ currentArticle.summary }}</p></header>
            <p v-if="fragmentError" class="state-banner state-banner--info" role="alert">{{ fragmentError }} 请从本篇目录重新选择。</p>
            <nav v-if="articleHeadings.length" class="manual-toc" aria-label="本篇目录"><strong>本篇目录</strong><div><RouterLink v-for="heading in articleHeadings" :key="heading.id" :to="articleLocation(selectedId, heading.id)" :class="{ 'manual-toc__sub': heading.depth > 2 }" :aria-current="fragment === heading.id ? 'location' : undefined">{{ heading.title }}</RouterLink></div></nav>
            <div class="manual-body" @click="followContentLink"><template v-for="(block, index) in document.blocks" :key="`${selectedId}:${index}`"><div v-if="block.kind === 'html'" v-html="block.html" /><MermaidDiagram v-else :source="block.source" @rendered="diagramRendered" /></template></div>
            <footer class="manual-related" aria-label="继续阅读"><RouterLink v-if="previousArticle" :to="articleLocation(previousArticle.id)"><small>上一篇</small><strong>← {{ previousArticle.title }}</strong></RouterLink><RouterLink v-if="nextArticle" :to="articleLocation(nextArticle.id)"><small>继续阅读</small><strong>{{ nextArticle.title }} →</strong></RouterLink></footer>
          </article>
        </template>
      </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import MermaidDiagram from '@/components/manual/MermaidDiagram.vue';
import { manualArticles, manualGroups, loadManualArticle, searchManual, type ManualDocument, type ManualSearchResult } from '@/content/manual';
const route = useRoute(), router = useRouter();
const homeId = manualArticles.find(article => article.id === 'overview')?.id ?? manualArticles[0]?.id ?? '';
const selectedId = computed(() => typeof route.params.articleId === 'string' && route.params.articleId ? route.params.articleId : homeId);
const currentArticle = computed(() => manualArticles.find(article => article.id === selectedId.value));
const currentIndex = computed(() => manualArticles.findIndex(article => article.id === selectedId.value));
const previousArticle = computed(() => manualArticles[currentIndex.value - 1]);
const nextArticle = computed(() => currentIndex.value >= 0 ? manualArticles[currentIndex.value + 1] : undefined);
const document = ref<ManualDocument | null>(null), loading = ref(false), error = ref(''), fragmentError = ref('');
const query = ref(''), results = ref<ManualSearchResult[]>([]), searching = ref(false), searchError = ref('');
const articleHeadings = computed(() => document.value?.headings.filter(heading => heading.depth >= 2) ?? []);
const fragment = computed(() => { try { return decodeURIComponent(route.hash.slice(1)); } catch { return route.hash.slice(1); } });
const categories = (group: string) => [...new Set(manualArticles.filter(article => article.group === group).map(article => article.category))];
const categoryArticles = (group: string, category: string) => manualArticles.filter(article => article.group === group && article.category === category);
const groupTitle = (group: string) => manualGroups.find(item => item.id === group)?.title ?? group;
const articleLocation = (articleId: string, sectionId = '') => ({ name: 'manual', params: { articleId }, hash: sectionId ? `#${sectionId}` : '' });
let generation = 0, searchGeneration = 0, searchTimer: ReturnType<typeof setTimeout> | undefined, pendingDiagrams = 0;
function positionFragment(focus = true) {
  fragmentError.value = '';
  if (!fragment.value) { window.scrollTo({ top: 0 }); return; }
  if (!document.value?.headings.some(heading => heading.id === fragment.value)) { fragmentError.value = `未找到“${fragment.value}”小节。`; window.scrollTo({ top: 0 }); return; }
  const target = window.document.getElementById(fragment.value);
  if (target) { target.scrollIntoView({ block: 'start' }); if (focus) target.focus({ preventScroll: true }); }
}
async function openArticle() {
  const sequence = ++generation;
  loading.value = true; error.value = ''; fragmentError.value = ''; document.value = null;
  if (!currentArticle.value) { error.value = '文章地址可能已变更，请从左侧目录选择一篇说明。'; loading.value = false; window.scrollTo({ top: 0 }); return; }
  try {
    const loaded = await loadManualArticle(selectedId.value);
    if (sequence !== generation) return;
    document.value = loaded;
    pendingDiagrams = loaded.blocks.filter(block => block.kind === 'diagram').length;
    window.document.title = `使用手册 · ${currentArticle.value?.title ?? ''} · 测试平台`;
  } catch (cause) { if (sequence === generation) error.value = cause instanceof Error ? cause.message : '加载失败，请重试。'; }
  finally { if (sequence === generation) { loading.value = false; await nextTick(); positionFragment(); } }
}
function diagramRendered() {
  if (pendingDiagrams > 0) --pendingDiagrams;
  // 图形完成后会改变正文高度，重新对准深链接，避免落在上一个小节。
  if (pendingDiagrams === 0 && fragment.value) void nextTick(() => positionFragment(false));
}
async function selectSearch() { query.value = ''; await nextTick(); positionFragment(); }
function followContentLink(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || !(event.target instanceof Element)) return;
  const link = event.target.closest('a');
  if (!(link instanceof HTMLAnchorElement) || link.target || link.hasAttribute('download')) return;
  const url = new URL(link.href, window.location.href);
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  if (url.origin !== window.location.origin || !url.pathname.startsWith(`${base}/manual`)) return;
  event.preventDefault();
  void router.push(`${url.pathname.slice(base.length)}${url.search}${url.hash}`);
}
watch(selectedId, () => { void openArticle(); }, { immediate: true });
watch(() => route.hash, async () => { await nextTick(); if (!loading.value) positionFragment(); });
watch(query, value => {
  clearTimeout(searchTimer);
  const sequence = ++searchGeneration;
  results.value = []; searchError.value = ''; searching.value = !!value.trim();
  if (!value.trim()) return;
  searchTimer = setTimeout(async () => {
    try { const found = await searchManual(value); if (sequence === searchGeneration) results.value = found; }
    catch { if (sequence === searchGeneration) searchError.value = '手册搜索暂时不可用，请通过左侧目录查阅或稍后重试。'; }
    finally { if (sequence === searchGeneration) searching.value = false; }
  }, 160);
});
onBeforeUnmount(() => { ++generation; ++searchGeneration; clearTimeout(searchTimer); });
</script>
<style scoped>
.manual-page { min-width: 0; padding-bottom: 32px; }
.manual-search { padding: 20px 24px; margin-bottom: 22px; border: 1px solid var(--color-border); border-radius: 10px; background: white; }
.manual-search > label { display: block; font-size: 14px; font-weight: 650; margin-bottom: 10px; }
.manual-search__field { display: flex; align-items: center; gap: 10px; max-width: 780px; border: 1px solid #d5ddea; border-radius: 7px; padding: 0 12px; background: #fbfcff; color: #8794ad; }
.manual-search__field input { min-width: 0; flex: 1; border: 0; background: transparent; box-shadow: none; padding: 11px 0; }
.manual-search__field input:focus { outline: none; }
.manual-search__field:focus-within { outline: 2px solid var(--color-accent-strong); outline-offset: 2px; }
.manual-search__field button { min-height: 26px; border: 0; padding: 4px 8px; font-size: 12px; }
.manual-search > p { color: var(--color-ink-muted); margin: 10px 0 0; font-size: 12px; }
.manual-search__results { margin-top: 18px; border-top: 1px solid var(--color-border); padding-top: 12px; }
.manual-search__results > p { color: var(--color-ink-muted); font-size: 12px; }
.manual-search__results ol { display: grid; gap: 6px; max-height: 460px; overflow: auto; list-style: none; margin: 0; padding: 0; }
.manual-search__results a { display: grid; gap: 5px; padding: 12px; border-radius: 7px; color: var(--color-ink-base); text-decoration: none; }
.manual-search__results a:hover { background: #f4f6fc; }
.manual-search__results small, .manual-search__results span { color: var(--color-ink-muted); line-height: 1.7; font-size: 12px; }
.manual-search__results strong { color: var(--color-accent-strong); font-size: 14px; }
.manual-layout { display: grid; grid-template-columns: 228px minmax(0, 1fr); gap: 22px; align-items: start; }
.manual-navigation { position: sticky; top: 20px; max-height: calc(100dvh - 40px); overflow-y: auto; border: 1px solid var(--color-border); border-radius: 10px; background: white; padding: 18px 12px; scrollbar-width: thin; }
.manual-navigation__heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 0 6px 14px; border-bottom: 1px solid #edf0f5; }
.manual-navigation__heading strong { font-size: 14px; }.manual-navigation__heading span { color: var(--color-ink-muted); font-size: 11px; }
.manual-group { border: 0; background: transparent; padding: 0; margin: 10px 0 0; }
.manual-group > summary { padding: 8px 5px; color: #3c4b65; font-size: 13px; font-weight: 650; cursor: pointer; }
.manual-category { margin: 2px 0 10px 9px; padding-left: 10px; border-left: 1px solid #e8edf5; }
.manual-category > p { margin: 8px 6px 4px; color: #8b96a8; font-size: 11px; }
.manual-category a { display: block; margin: 2px 0; padding: 7px 8px; color: #68758d; text-decoration: none; font-size: 12px; line-height: 1.65; border-radius: 5px; }
.manual-category a:hover { background: #f6f8fc; }.manual-category a[aria-current='page'] { color: var(--color-accent-strong); background: var(--color-accent-soft); font-weight: 600; }
.manual-reading { min-width: 0; }.manual-state { padding: 32px; border: 1px solid var(--color-border); background: white; border-radius: 10px; line-height: 1.8; }.manual-state button { margin-left: 18px; }
.manual-article { min-width: 0; padding: 30px 36px; border: 1px solid var(--color-border); border-radius: 10px; background: white; }
.manual-breadcrumbs { display: flex; flex-wrap: wrap; gap: 8px; color: #8591a5; font-size: 11px; line-height: 1.8; }.manual-breadcrumbs a { color: var(--color-accent-strong); text-decoration: none; }
.manual-article__header { margin: 16px 0 24px; }.manual-article__header h1 { margin: 0 0 12px; color: #23324c; font-size: 27px; line-height: 1.5; letter-spacing: -.5px; }.manual-article__header p { margin: 0; color: #7a879c; line-height: 1.9; font-size: 14px; }
.manual-toc { padding: 16px 20px; margin-bottom: 28px; border: 1px solid #e3e9f3; border-radius: 8px; background: #f8faff; }.manual-toc > strong { font-size: 12px; color: #526282; }.manual-toc > div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 18px; margin-top: 10px; }.manual-toc a { color: #63779e; text-decoration: none; font-size: 12px; line-height: 1.8; }.manual-toc a:hover, .manual-toc a[aria-current='location'] { color: var(--color-accent-strong); text-decoration: underline; }.manual-toc .manual-toc__sub { padding-left: 12px; }
.manual-body { color: #40506a; font-size: 14px; line-height: 1.95; overflow-wrap: anywhere; }
.manual-body :deep(h1), .manual-body :deep(h2), .manual-body :deep(h3), .manual-body :deep(h4), .manual-body :deep(.manual-document-anchor) { scroll-margin-top: 24px; outline-offset: 5px; }
.manual-body :deep(h1) { font-size: 25px; }.manual-body :deep(h2) { margin: 34px 0 14px; padding-top: 5px; font-size: 21px; line-height: 1.6; color: #263851; }.manual-body :deep(h3) { margin: 26px 0 10px; font-size: 16px; color: #354865; }.manual-body :deep(h4) { font-size: 14px; margin: 22px 0 10px; }
.manual-body :deep(p) { margin: 12px 0; }.manual-body :deep(ul), .manual-body :deep(ol) { padding-left: 24px; }.manual-body :deep(li) { margin: 7px 0; }.manual-body :deep(a) { color: var(--color-accent-strong); text-underline-offset: 3px; }
.manual-body :deep(code) { padding: 2px 5px; border-radius: 4px; color: #4a5f8b; background: #eff3fa; font-size: 12px; }.manual-body :deep(pre) { overflow: auto; max-height: 620px; padding: 18px; border: 1px solid #e3e9f3; border-radius: 8px; background: #f6f8fc; white-space: pre; line-height: 1.8; }.manual-body :deep(pre code) { padding: 0; background: transparent; color: #425573; font-size: 12px; }
.manual-body :deep(blockquote) { margin: 20px 0; padding: 8px 18px; border-left: 3px solid #8fa6d4; background: #f3f6fc; color: #617492; }
.manual-body :deep(table) { display: block; width: max-content; max-width: 100%; overflow-x: auto; margin: 20px 0; border-collapse: collapse; font-size: 12px; line-height: 1.85; }.manual-body :deep(th), .manual-body :deep(td) { min-width: 100px; max-width: 460px; padding: 11px 13px; border: 1px solid #e1e7f0; text-align: left; vertical-align: top; }.manual-body :deep(th) { background: #f4f7fc; color: #485c7d; font-weight: 600; }.manual-body :deep(hr) { border: 0; border-top: 1px solid #e8edf5; margin: 28px 0; }
.manual-related { display: flex; justify-content: space-between; gap: 24px; padding-top: 24px; margin-top: 38px; border-top: 1px solid #e4eaf3; }.manual-related a { display: grid; gap: 6px; max-width: 48%; color: var(--color-accent-strong); text-decoration: none; }.manual-related a:last-child { margin-left: auto; text-align: right; }.manual-related small { color: #8a97ad; font-size: 11px; }.manual-related strong { font-size: 13px; }
@media (max-width: 1400px) { .manual-layout { grid-template-columns: 210px minmax(0, 1fr); gap: 18px; }.manual-article { padding: 26px; }.manual-toc > div { grid-template-columns: minmax(0, 1fr); } }
</style>

<style scoped>.manual-reading{max-width:1040px}.manual-body{max-width:920px;margin-inline:auto}</style>
