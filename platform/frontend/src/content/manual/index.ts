import { Marked, type Token, type Tokens } from 'marked';
import { manualArticles, manualGroups } from './catalog';

export { manualArticles, manualGroups };
export type ManualArticleMeta = (typeof manualArticles)[number];
export interface ManualHeading { id: string; title: string; depth: number }
export type ManualBlock = { kind: 'html'; html: string } | { kind: 'diagram'; source: string };
export interface ManualDocument { blocks: ManualBlock[]; headings: ManualHeading[]; sections: ManualSearchSection[] }
export interface ManualSearchSection { articleId: string; sectionId: string; title: string; text: string }
export interface ManualSearchResult extends ManualSearchSection { article: ManualArticleMeta; excerpt: string }

const articleFiles = import.meta.glob<string>('./articles/*.md', { query: '?raw', import: 'default' });
const documents = new Map<string, Promise<ManualDocument>>();
const anchorPattern = /\s*\{#([a-z][a-z0-9-]*)\}\s*$/;
function headingInfo(token: Tokens.Heading): ManualHeading {
  const match = token.text.match(anchorPattern);
  return { id: match?.[1] ?? '', title: token.text.replace(anchorPattern, '').replace(/[`*_]/g, ''), depth: token.depth };
}
function escapeHtml(value: string) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}
function plainText(value: string) {
  return value.replace(/```[^\n]*\n/g, ' ').replace(/\{#[a-z][a-z0-9-]*\}/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[#*`>|]/g, ' ').replace(/\s+/g, ' ').trim();
}

// 渲染和目录都读同一份 heading token，避免标题重命名导致问号锚点悄悄变化。
export function parseManualMarkdown(source: string, articleId = ''): ManualDocument {
  const markdown = new Marked({ gfm: true });
  const renderer = {
    heading(this: { parser: { parseInline(tokens: Token[]): string } }, token: Tokens.Heading) {
      const heading = headingInfo(token);
      const html = this.parser.parseInline(token.tokens).replace(anchorPattern, '');
      const id = heading.id ? ` id="${heading.id}" tabindex="-1"` : '';
      if (token.depth === 1) return `<div${id} class="manual-document-anchor"></div>\n`;
      return `<h${token.depth}${id}>${html}</h${token.depth}>\n`;
    },
    link(this: { parser: { parseInline(tokens: Token[]): string } }, token: Tokens.Link) {
      const href = token.href.startsWith('/manual') ? `${import.meta.env.BASE_URL.replace(/\/$/, '')}${token.href}` : token.href;
      return `<a href="${escapeHtml(href)}"${token.title ? ` title="${escapeHtml(token.title)}"` : ''}>${this.parser.parseInline(token.tokens)}</a>`;
    },
  };
  markdown.use({ renderer });
  const tokens = markdown.lexer(source);
  const blocks: ManualBlock[] = [], headings: ManualHeading[] = [], sections: ManualSearchSection[] = [];
  let pending: Token[] = [];
  let section: ManualSearchSection = { articleId, sectionId: '', title: '', text: '' };
  const flush = () => {
    if (pending.length) blocks.push({ kind: 'html', html: markdown.parser(pending) });
    pending = [];
  };
  for (const token of tokens) {
    if (token.type === 'heading') {
      const heading = headingInfo(token as Tokens.Heading);
      if (heading.id) headings.push(heading);
      if (section.text.trim()) sections.push({ ...section, text: plainText(section.text) });
      section = { articleId, sectionId: heading.id, title: heading.title, text: token.raw };
    } else section.text += token.raw;
    if (token.type === 'code' && token.lang?.trim() === 'mermaid') {
      flush(); blocks.push({ kind: 'diagram', source: token.text });
    } else pending.push(token);
  }
  flush();
  if (section.text.trim()) sections.push({ ...section, text: plainText(section.text) });
  return { blocks, headings, sections };
}

export function loadManualArticle(articleId: string): Promise<ManualDocument> {
  const existing = documents.get(articleId);
  if (existing) return existing;
  const load = articleFiles[`./articles/${articleId}.md`];
  if (!load) return Promise.reject(new Error('这篇手册暂时无法找到，请从目录选择其他文章。'));
  const promise = load().then(source => parseManualMarkdown(source, articleId));
  documents.set(articleId, promise);
  promise.catch(() => documents.delete(articleId));
  return promise;
}

let searchIndex: Promise<ManualSearchSection[]> | undefined;
export async function searchManual(query: string): Promise<ManualSearchResult[]> {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  searchIndex ??= Promise.all(manualArticles.map(article => loadManualArticle(article.id))).then(items => items.flatMap(item => item.sections)).catch(error => { searchIndex = undefined; throw error; });
  const results: (ManualSearchResult & { score: number })[] = [];
  for (const section of await searchIndex) {
    const article = manualArticles.find(item => item.id === section.articleId);
    if (!article) continue;
    const metadata = [article.title, article.summary, ...article.keywords, section.title].join(' ').toLocaleLowerCase();
    const text = section.text.toLocaleLowerCase();
    if (!terms.every(term => metadata.includes(term) || text.includes(term))) continue;
    const first = terms.map(term => text.indexOf(term)).filter(index => index >= 0).sort((a, b) => a - b)[0] ?? 0;
    const start = Math.max(0, first - 35);
    results.push({ ...section, article, excerpt: `${start ? '…' : ''}${section.text.slice(start, start + 145)}${section.text.length > start + 145 ? '…' : ''}`, score: terms.reduce((score, term) => score + (section.title.toLocaleLowerCase().includes(term) ? 5 : 0) + (article.title.toLocaleLowerCase().includes(term) ? 2 : 0) + (text.includes(term) ? 1 : 0), 0) });
  }
  return results.sort((a, b) => b.score - a.score).slice(0, 60);
}
