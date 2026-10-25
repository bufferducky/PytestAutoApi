import type { RunStatus, StatusTone } from '@/types/platform';

interface RunStatusPresentation {
  label: string;
  tone: StatusTone;
  summary: string;
  description: string;
  nextSteps: string[];
}

/**
 * 运行状态会同时来自两类来源：
 * 1. 历史模拟运行状态
 * 2. 后端真实接口里的 queued / succeeded / failed 等原始枚举
 *
 * 这里统一做“后端状态 -> 前端展示状态”的映射，避免 Dashboard 和 Runs 两页各写一套。
 */
const runStatusMetaMap: Record<RunStatus, RunStatusPresentation> = {
  queued: {
    label: '排队中',
    tone: 'neutral',
    summary: '任务已经进入队列，但还没真正开始执行。',
    description: '排队态通常代表调度器已受理请求，接下来要确认 worker 是否空闲、队列是否积压。',
    nextSteps: ['先确认调度队列长度是否异常。', '再检查是否有空闲 worker 可以拉起本次运行。'],
  },
  running: {
    label: '运行中',
    tone: 'running',
    summary: '任务正在执行中，排障重点是判断有没有卡在慢步骤或外部依赖。',
    description: '运行中不代表系统健康，仍要结合耗时、步骤日志和依赖服务状态判断是否存在阻塞。',
    nextSteps: ['优先对照当前耗时与历史平均值。', '再确认外部依赖、数据库或鉴权链路是否变慢。'],
  },
  success: {
    label: '成功',
    tone: 'success',
    summary: '任务已经成功结束，当前更适合作为结果核对和追溯入口。',
    description: '成功态说明主流程通过了当前断言，但如果业务仍异常，还需要继续查看日志、响应片段和下游结果。',
    nextSteps: ['若用户仍反馈异常，继续抽查关键日志和响应片段。', '确认成功结果是否对应了正确环境和正确目标。'],
  },
  failed: {
    label: '失败',
    tone: 'attention',
    summary: '任务已经失败，应优先定位失败步骤和最近变更。',
    description: '失败态是最直接的排障入口，通常要先看错误摘要，再沿着目标、触发人和时间回溯上下文。',
    nextSteps: ['先阅读错误摘要，确认是断言失败、依赖失败还是环境问题。', '结合目标和触发时间回看最近代码、配置或环境变更。'],
  },
  warning: {
    label: '告警',
    tone: 'warning',
    summary: '结果范围或状态需要确认，不能据此判定真实业务通过。',
    description: '检查执行模式、未知状态和证据完整性，勿把告警当作已通过。',
    nextSteps: ['确认哪些步骤被标记成非阻塞告警。', '评估是否需要把当前告警升级成阻塞失败。'],
  },
  error: { label: '执行错误', tone: 'attention', summary: '执行器、配置或外部调用异常，需要检查错误明细。', description: '执行器、配置或外部调用异常，需要检查错误明细。', nextSteps: ['查看步骤证据和清理状态。'] },
  skipped: { label: '已跳过', tone: 'attention', summary: '本次没有完成有效业务验证，不计真实通过。', description: '本次没有完成有效业务验证，不计真实通过。', nextSteps: ['查看步骤证据和清理状态。'] },
  blocked: { label: '被阻塞', tone: 'attention', summary: '缺少前置条件或有效断言，业务尚未验证。', description: '缺少前置条件或有效断言，业务尚未验证。', nextSteps: ['查看步骤证据和清理状态。'] },
  cancelled: { label: '已取消', tone: 'attention', summary: '已停止新步骤；已到达服务端的写请求需要检查。', description: '已停止新步骤；已到达服务端的写请求需要检查。', nextSteps: ['查看步骤证据和清理状态。'] },
  timed_out: { label: '已超时', tone: 'attention', summary: '运行预算耗尽，需检查已发请求与清理结果。', description: '运行预算耗尽，需检查已发请求与清理结果。', nextSteps: ['查看步骤证据和清理状态。'] },
  interrupted: { label: '执行中断', tone: 'attention', summary: 'worker 中断，未盲目重放，需核查资源。', description: 'worker 中断，未盲目重放，需核查资源。', nextSteps: ['查看步骤证据和清理状态。'] },
};

export const normalizeRunStatus = (rawStatus?: string | null): RunStatus => {
  const normalizedStatus = rawStatus?.trim().toLowerCase();

  switch (normalizedStatus) {
    case 'queued':
    case 'pending':
      return 'queued';
    case 'running':
    case 'in_progress':
      return 'running';
    case 'succeeded':
    case 'success':
    case 'passed':
      return 'success';
    case 'failed':
      return 'failed';
    case 'error':
    case 'skipped':
    case 'blocked':
    case 'cancelled':
    case 'timed_out':
    case 'interrupted':
      return normalizedStatus;
    case 'warning':
    case 'partial_success':
      return 'warning';
    default:
      return 'warning';
  }
};

export const getRunStatusMeta = (status: RunStatus) => {
  const { label, tone } = runStatusMetaMap[status];
  return { label, tone };
};

/**
 * 页面层不再自己拼接状态说明文案，而是统一从这里拿：
 * - 文案口径一致
 * - 新页面要复用时不必复制 switch 逻辑
 */
export const getRunStatusInsight = (status: RunStatus) => {
  const { summary, description, nextSteps } = runStatusMetaMap[status];
  return { summary, description, nextSteps };
};
