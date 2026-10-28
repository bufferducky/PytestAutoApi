// 只转换展示文案；API 枚举与复制的原始证据保持不变。
const labels: Record<string, string> = {
  live: '真实执行', mock: '历史模拟', debug: '草稿调试', live_partial: '真实局部复跑',
  historical_unknown: '历史未记录', historical_demo: '迁入演示历史',
  simulated: '模拟证据', simulated_partial: '模拟局部证据',
  succeeded: '成功', failed: '失败', not_started: '未开始', not_recorded: '未记录',
  running: '执行中', skipped: '已跳过', error: '执行错误', needs_reconciliation: '待核对',
  recorded: '已记录', complete: '完整', partial: '不完整', pruned: '已回收', missing: '缺失',
  'platform-asset': '发布资产', manual: '手动', scheduler: '定时调度', rerun: '关联复跑',
  assertion: '断言失败', setup: '准备', action: '执行', verify: '验证', cleanup: '清理',
  total: '结果数', errors: '错误', passed: '通过', blocked: '阻塞', planned: '计划步骤',
  executed: '已执行', requests: '请求数', assertions: '断言数', authentication_requests: '认证请求',
  cleanup_requests: '清理请求', cancelled: '已取消', timed_out: '已超时', interrupted: '已中断',
};
export const evidenceLabel = (value: string) => labels[value] || value;
