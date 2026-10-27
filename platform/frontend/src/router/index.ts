import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';

const ExtensionsPage = () => import('@/pages/ExtensionsPage.vue');
import DashboardPage from '@/pages/DashboardPage.vue';
const CasesPage = () => import('@/pages/CasesPage.vue');
const SuitesPage = () => import('@/pages/SuitesPage.vue');
const EnvironmentsPage = () => import('@/pages/EnvironmentsPage.vue');
const RunsPage = () => import('@/pages/RunsPage.vue');
const SchedulesPage = () => import('@/pages/SchedulesPage.vue');
import { useAppStore } from '@/stores/app';

const routes: RouteRecordRaw[] = [
  { path: '/manual/:articleId?', name: 'manual', component: () => import('@/pages/ManualPage.vue'), meta: { title: '使用手册', description: '从基础概念到完整测试链路，按步骤配置，随时查阅字段说明。', navLabel: '使用手册', shortLabel: 'MA', section: 'manual' } },
  { path: '/extensions', name: 'extensions', component: ExtensionsPage, meta: { title: '扩展工具', description: '覆盖账本、测试资源、旅程能力与历史评估。', navLabel: '扩展工具', shortLabel: 'EX', section: 'cases' } },
  {
    path: '/',
    redirect: { name: 'dashboard' },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: DashboardPage,
    meta: {
      title: '工作台',
      description: '继续编辑资产，执行回归，处理失败。',
      navLabel: '仪表盘',
      shortLabel: 'DB',
      section: 'dashboard',
    },
  },
  {
    path: '/cases',
    name: 'cases',
    component: CasesPage,
    meta: {
      title: '用例管理',
      description: '组织业务场景，编排请求步骤，管理断言与发布版本。',
      navLabel: '用例管理',
      shortLabel: 'CA',
      section: 'cases',
    },
  },
  {
    path: '/suites',
    name: 'suites',
    component: SuitesPage,
    meta: {
      title: '套件管理',
      description: '组合已发布场景，固定版本与执行顺序。',
      navLabel: '套件管理',
      shortLabel: 'SU',
      section: 'suites',
    },
  },
  {
    path: '/environments',
    name: 'environments',
    component: EnvironmentsPage,
    meta: {
      title: '环境管理',
      description: '管理执行环境、目标系统与测试身份。',
      navLabel: '环境管理',
      shortLabel: 'EN',
      section: 'environments',
    },
  },
  {
    path: '/runs',
    name: 'runs',
    component: RunsPage,
    meta: {
      title: '执行结果',
      description: '追踪每次运行的状态、失败原因与执行证据。',
      navLabel: '执行结果',
      shortLabel: 'RU',
      section: 'runs',
    },
  },
  {
    path: '/schedules',
    name: 'schedules',
    component: SchedulesPage,
    meta: {
      title: '调度任务',
      description: '配置定时回归，预览触发时间，查看执行记录。',
      navLabel: '调度任务',
      shortLabel: 'SC',
      section: 'schedules',
    },
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  // 手册正文延迟加载，小节位置由阅读器在内容就绪后处理。
  scrollBehavior: to => to.name === 'manual' ? false : ({ top: 0 }),
});

router.afterEach((to) => {
  // 路由 meta 是页面信息的单一入口：
  // 标题、描述、导航高亮都优先从这里取，避免每个组件自己维护一套副本。
  const appStore = useAppStore();
  appStore.setCurrentSection(to.meta.section);
  if ((to.name === 'cases' || to.name === 'suites') && typeof to.query.assetId === 'string') appStore.rememberAsset(to.query.assetId);
  document.title = `测试平台 · ${to.meta.title}`;
});

export default router;

