// 通过 Vite 读取真实手册运行时，检查主题、小节、站内链接和检索的数据契约。
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const frontend = path.join(root, 'platform/frontend');
const require = createRequire(path.join(frontend, 'package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const server = await createServer({
  root: frontend,
  configFile: path.join(frontend, 'vite.config.ts'),
  logLevel: 'error',
  server: { middlewareMode: true, watch: null },
});

try {
  const runtime = await server.ssrLoadModule('/src/content/manual/index.ts');
  const { manualTopicLinks } = await server.ssrLoadModule('/src/content/manual/topicLinks.ts');
  const { helpTopics } = await server.ssrLoadModule('/src/content/helpTopics.ts');
  const articles = runtime.manualArticles;
  const groups = runtime.manualGroups;
  assert.ok(groups.length >= 8, '入门、概念、各模块及高级专题都需有入口');
  assert.equal(new Set(articles.map(article => article.id)).size, articles.length, '文章 ID 必须唯一');
  assert.equal(new Set(groups.map(group => group.id)).size, groups.length, '一级目录 ID 必须唯一');
  const documents = new Map();
  const manifest = [];
  let diagramCount = 0;
  for (const article of articles) {
    assert.ok(groups.some(group => group.id === article.group), `${article.id}: 分组不存在`);
    assert.ok(article.category && article.summary && article.keywords.length, `${article.id}: 三级导航/查找信息不完整`);
    const document = await runtime.loadManualArticle(article.id);
    assert.ok(document.headings.length, `${article.id}: 必须有可定位的小节`);
    assert.equal(new Set(document.headings.map(heading => heading.id)).size, document.headings.length, `${article.id}: 小节 ID 重复`);
    for (const heading of document.headings) {
      assert.match(heading.id, /^[a-z][a-z0-9-]*$/, `${article.id}: 小节 ID 应稳定且可作为 URL`);
      assert.ok(document.blocks.some(block => block.kind === 'html' && block.html.includes(`id="${heading.id}"`)), `${article.id}#${heading.id}: 目录与实际渲染不一致`);
    }
    const diagrams = document.blocks.filter(block => block.kind === 'diagram').length;
    diagramCount += diagrams;
    documents.set(article.id, document);
    manifest.push({ ...article, headings: document.headings, diagrams });
  }
  assert.ok(diagramCount >= 10, `关键链路图不足，目前 ${diagramCount} 张`);
  assert.deepEqual(Object.keys(manualTopicLinks).sort(), Object.keys(helpTopics).sort(), '全部既有和新增帮助主题均需映射');
  assert.ok(Object.keys(helpTopics).length >= 161, '157 个基线主题和 4 个调试帮助不能缺失');
  for (const [topic, link] of Object.entries(manualTopicLinks)) {
    const document = documents.get(link.articleId);
    assert.ok(document, `${topic}: 目标文章不存在`);
    const section = document.sections.find(item => item.sectionId === link.sectionId);
    assert.ok(section, `${topic}: 目标小节不存在 ${link.articleId}#${link.sectionId}`);
    assert.ok(section.text.length > 40, `${topic}: 小节只有标题，没有实质解释`);
  }
  for (const article of articles) {
    const source = await readFile(path.join(frontend, 'src/content/manual/articles', `${article.id}.md`), 'utf8');
    for (const match of source.matchAll(/\]\((\/manual(?:\/[^)\s#]+)?)(#[^)\s]+)?\)/g)) {
      const target = match[1].slice('/manual/'.length) || articles[0].id;
      assert.ok(documents.has(target), `${article.id}: 无效站内链接 ${match[0]}`);
      if (match[2]) assert.ok(documents.get(target).headings.some(item => item.id === match[2].slice(1)), `${article.id}: 无效站内小节 ${match[0]}`);
    }
  }
  assert.deepEqual(await runtime.searchManual('   '), []);
  for (const query of ['JSON', 'Token', 'params', '秘密引用']) {
    const results = await runtime.searchManual(query);
    assert.ok(results.length, `检索无法找到关键概念：${query}`);
    for (const result of results) {
      assert.ok(documents.has(result.articleId));
      assert.ok(result.text && result.excerpt);
      if (result.sectionId) assert.ok(documents.get(result.articleId).headings.some(item => item.id === result.sectionId));
    }
  }
  const result = { articles: manifest, groups, topicLinks: manualTopicLinks, topicCount: Object.keys(helpTopics).length, diagramCount };
  console.log(process.argv.includes('--json') ? JSON.stringify(result) : `Manual content passed: ${articles.length} articles, ${result.topicCount} topics, ${diagramCount} diagrams; anchors, internal links and real search verified.`);
} finally {
  await server.close();
}
