import { apiClient } from '@/api/client';
import {
  extractManagementCollection,
  normalizeCaseSummary,
  normalizeEnvironmentDetail,
  normalizeEnvironmentSummary,
  normalizeScheduleSummary,
  normalizeSuiteSummary,
} from '@/api/adapters/management';
import { extractRunCollection, normalizeRunSummary } from '@/api/adapters/runs';
import type {
  ApiResolvedData,
  CaseSummary,
  CreateEnvironmentPayload,
  EnvironmentDetail,
  EnvironmentSummary,
  RunSummary,
  ScheduleSummary,
  SuiteSummary,
  UpdateEnvironmentPayload,
} from '@/types/platform';

export const managementApi = {
  async listCases() {
    try {
      const payload = await apiClient.get<unknown>('/cases');
      return extractManagementCollection(payload).map((item, index) => normalizeCaseSummary(item, index));
    } catch (error) {
      throw error;
    }
  },

  async listSuites() {
    try {
      const payload = await apiClient.get<unknown>('/suites');
      return extractManagementCollection(payload).map((item, index) => normalizeSuiteSummary(item, index));
    } catch (error) {
      throw error;
    }
  },

  async listEnvironments() {
    try {
      const payload = await apiClient.get<unknown>('/environments');
      return extractManagementCollection(payload).map((item, index) =>
        normalizeEnvironmentSummary(item, index),
      );
    } catch (error) {
      throw error;
    }
  },

  async getEnvironmentDetail(environmentId: string): Promise<EnvironmentDetail> {
    try {
      const response = await apiClient.get<unknown>(`/environments/${environmentId}`);
      return normalizeEnvironmentDetail(response, 0);
    } catch (error) {
      throw error;
    }
  },

  async createEnvironment(payload: CreateEnvironmentPayload): Promise<EnvironmentDetail> {
    const response = await apiClient.post<unknown>('/environments', {
      name: payload.name,
      base_url: payload.baseUrl,
      auth_mode: payload.authMode,
      status: payload.status,
    });
    return normalizeEnvironmentDetail(response, 0);
  },

  async updateEnvironment(
    environmentId: string,
    payload: UpdateEnvironmentPayload,
  ): Promise<EnvironmentDetail> {
    const response = await apiClient.patch<unknown>(`/environments/${environmentId}`, {
      expected_revision: payload.expectedRevision,
      name: payload.name,
      base_url: payload.baseUrl,
      auth_mode: payload.authMode,
      status: payload.status,
    });
    return normalizeEnvironmentDetail(response, 0);
  },

  async deleteEnvironment(environmentId: string): Promise<EnvironmentSummary> {
    const response = await apiClient.delete<unknown>(`/environments/${environmentId}`);
    return normalizeEnvironmentSummary(response, 0);
  },

  async listRuns(_options?: { query?: Record<string, string | number> }): Promise<ApiResolvedData<RunSummary[]>> {

    try {
      const payload = await apiClient.get<unknown>('/runs', _options?.query);
      const runs = extractRunCollection(payload).map((item, index) => normalizeRunSummary(item, index));

      return {
        data: runs,
        total: typeof payload === 'object' && payload !== null && 'total' in payload && typeof payload.total === 'number' ? payload.total : runs.length,
        source: 'api',
      };
    } catch (error) {
      throw error;
    }
  },

  async listSchedules() {
    try {
      const payload = await apiClient.get<unknown>('/schedules');
      return extractManagementCollection(payload).map((item, index) =>
        normalizeScheduleSummary(item, index),
      );
    } catch (error) {
      throw error;
    }
  },
};
