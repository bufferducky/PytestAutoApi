// 在浏览器读取真实布局后校验，不能用构建通过或匹配 CSS 字符串代替。
// measureLayout 可传给 Playwright page.evaluate；按用户确认范围只验收桌面。
import assert from 'node:assert/strict';

const widths = [1280, 1440, 1920];
const routes = ['/dashboard', '/cases', '/suites', '/environments', '/runs', '/schedules', '/extensions', '/manual'];

function measureLayout() {
  const rect = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return { width: box.width, height: box.height };
  };
  return {
    viewport: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    body: rect('.app-shell__body'),
    brand: rect('.side-nav__brand'),
    navItem: rect('.side-nav__item'),
    title: rect('.hero-banner__title'),
    links: document.querySelectorAll('.side-nav__menu a').length,
  };
}

function assertLayout(metrics, label) {
  assert.ok(metrics.scroll <= metrics.viewport + 1, `${label}: 页面横向溢出 ${JSON.stringify(metrics)}`);
  assert.equal(metrics.links, 7, `${label}: 六个业务入口和使用手册必须可达`);
  assert.ok(metrics.brand.height < 100, `${label}: 品牌区被页面高度拉伸`);
  assert.ok(metrics.navItem.height < 120, `${label}: 导航行被页面高度拉伸`);
  if (metrics.title) {
    assert.ok(metrics.title.width >= Math.min(240, metrics.body.width - 80),
      `${label}: 标题被元信息挤窄 ${JSON.stringify(metrics)}`);
    assert.ok(metrics.title.height < 250, `${label}: 标题出现逐字换行`);
  }
}

export { widths, routes, measureLayout, assertLayout };
