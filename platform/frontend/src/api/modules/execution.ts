import { normalizeRunDetail } from '@/api/adapters/runs';
import { apiClient } from '@/api/client';
import type { RunDetail } from '@/types/platform';

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readString = (value: unknown) => (typeof value === 'string' ? value : '');

const readRunId = (payload: unknown) => {
  if (!isRecord(payload)) {
    return '';
  }

  return readString(payload.run_id) || readString(payload.runId) || readString(payload.id);
};

export const executionApi = {
  getRunDetail,
  executeRunNow,
  rerun,
  cancelRun,
};

async function getRunDetail(runId: string): Promise<RunDetail> {
  const payload = await apiClient.get<unknown>(`/runs/${runId}`);
  return normalizeRunDetail(payload, 0);
}

async function executeRunNow(runId: string): Promise<RunDetail> {
  const payload = await apiClient.post<unknown>(`/worker/runs/${runId}/execute`);
  return normalizeRunDetail(payload, 0);
}

async function rerun(runId: string): Promise<RunDetail> {
  const created = await apiClient.post<unknown>(`/runs/${runId}/rerun`, { transport_mode: 'live' });
  return executeRunNow(readRunId(created));
}

async function cancelRun(runId: string): Promise<RunDetail> {
  return normalizeRunDetail(await apiClient.post<unknown>(`/runs/${runId}/cancel`), 0);
}
