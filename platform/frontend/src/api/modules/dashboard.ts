import { apiClient } from '@/api/client';
import { extractRunCollection, normalizeRunSummary } from '@/api/adapters/runs';
import type {
  ApiResolvedData,
  DashboardMetric,
  DashboardOverview,
  FocusItem,
} from '@/types/platform';

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readString = (value: unknown) => (typeof value === 'string' ? value : '');

const normalizeMetric = (payload: unknown, index: number): DashboardMetric | null => {
  if (!isRecord(payload)) {
    return null;
  }

  const label = readString(payload.label) || readString(payload.title);
  const value = payload.value ?? payload.count ?? payload.total;

  if (!label || value === undefined || value === null) {
    return null;
  }

  return {
    key: readString(payload.key) || `metric-${index}`,
    label,
    value: String(value),
    description: readString(payload.description) || '来自后端接口的统计摘要',
    trend: readString(payload.trend) || readString(payload.subtitle) || '已接入真实接口',
  };
};

const normalizeFocusItem = (payload: unknown, index: number): FocusItem | null => {
  if (!isRecord(payload)) {
    return null;
  }

  const status = readString(payload.status);
  const normalizedStatus: FocusItem['status'] =
    status === 'stable' || status === 'attention' || status === 'planned' ? status : 'planned';

  const title = readString(payload.title) || readString(payload.name);

  if (!title) {
    return null;
  }

  return {
    id: readString(payload.id) || `focus-${index}`,
    title,
    owner: readString(payload.owner) || '平台后端',
    status: normalizedStatus,
    summary: readString(payload.summary) || readString(payload.description) || '暂无补充说明',
  };
};

const normalizeDashboardOverview = (payload: unknown): DashboardOverview | null => {
  const root = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;

  if (!isRecord(root)) {
    return null;
  }

  const metrics = (Array.isArray(root.metrics) ? root.metrics : [])
    .map(normalizeMetric)
    .filter((item): item is DashboardMetric => item !== null);
  const focusItems = (
    Array.isArray(root.focusItems)
      ? root.focusItems
      : Array.isArray(root.focus_items)
        ? root.focus_items
        : []
  )
    .map(normalizeFocusItem)
    .filter((item): item is FocusItem => item !== null);
  const recentRuns = extractRunCollection(root.recentRuns ?? root.recent_runs)
    .map((item, index) => normalizeRunSummary(item, index));

  return {
    metrics,
    focusItems,
    recentRuns,
  };
};

export const dashboardApi = {
  async getOverview(): Promise<ApiResolvedData<DashboardOverview>> {
    const payload = await apiClient.get<unknown>('/dashboard/overview');
    const overview = normalizeDashboardOverview(payload);
    if (!overview) throw new Error('仪表盘接口返回结构不符合页面要求。');
    return { data: overview, source: 'api' };
  },
};
