import { computed, ref } from 'vue';
import { defineStore } from 'pinia';

import type { NavigationItem, RouteName } from '@/types/platform';

const defaultNavigation: NavigationItem[] = [
  { name: 'dashboard', label: '工作台', shortLabel: 'DB', description: '查看运行统计与最近执行。' },
  { name: 'cases', label: '用例管理', shortLabel: 'CA', description: '维护 HTTP 用例、断言与变量提取。' },
  { name: 'suites', label: '套件管理', shortLabel: 'SU', description: '组织用例顺序、分组与依赖。' },
  { name: 'environments', label: '环境管理', shortLabel: 'EN', description: '维护 base_url、鉴权和环境变量。' },
  { name: 'runs', label: '执行结果', shortLabel: 'RU', description: '查看运行记录、失败明细与定位信息。' },
  { name: 'schedules', label: '调度任务', shortLabel: 'SC', description: '配置轻量 cron 任务与执行入口。' },
];

export const useAppStore = defineStore('app', () => {
  // 这个 store 只放“壳层状态”：
  // 品牌信息、导航配置、当前所在模块等都属于页面外壳，不属于具体业务页。
  // 只记忆资产标识，不将草稿、请求参数或凭证写入浏览器存储。
  const recentAssetIds = ref<string[]>([]);
  try {
    const stored: unknown = JSON.parse(localStorage.getItem('testflow.recent-assets') ?? '[]');
    if (Array.isArray(stored)) recentAssetIds.value = stored.filter((id): id is string => typeof id === 'string').slice(0, 12);
  } catch { /* 禁用存储时仍可正常使用工作台。 */ }
  const rememberAsset = (id: string) => {
    recentAssetIds.value = [id, ...recentAssetIds.value.filter((item) => item !== id)].slice(0, 12);
    try { localStorage.setItem('testflow.recent-assets', JSON.stringify(recentAssetIds.value)); } catch { /* 内存记录仍然有效。 */ }
  };
  const platformName = ref('TestFlow');
  const platformSlogan = ref('个人 API 测试');
  const phaseLabel = ref('个人测试工作台');
  const navigation = ref(defaultNavigation);
  const currentSection = ref<RouteName>('dashboard');

  const currentNavigation = computed(() =>
    navigation.value.find((item) => item.name === currentSection.value),
  );

  const setCurrentSection = (section: RouteName) => {
    currentSection.value = section;
  };

  return {
    recentAssetIds,
    rememberAsset,
    platformName,
    platformSlogan,
    phaseLabel,
    navigation,
    currentSection,
    currentNavigation,
    setCurrentSection,
  };
});

