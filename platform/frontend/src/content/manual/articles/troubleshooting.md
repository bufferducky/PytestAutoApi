# 常见问题：从报错找到下一步

按出现的具体提示排查，不通过删保护字段或修改期望值来强行变绿。

## 配置与发布 {#configuration}

| 现象 | 先核对 | 下一步 |
| --- | --- | --- |
| JSON格式错误 | 双引号/尾逗号/对象与数组 | [JSON](/manual/json#mistakes) |
| 秘密引用不可用 | 名称、API与worker加载环境 | [秘密](/manual/identity#secret-ref) |
| 未声明/不可覆盖参数 | 参数schema是否声明键 | [覆盖规则](/manual/parameters#precedence) |
| 输出尚未声明/必须依赖 | 提取target与depends_on | [依赖](/manual/dependencies#dependencies) |
| 409修订冲突 | 当前服务端revision | 刷新核对，保留修改意图，不盲覆盖 |
| 预检按钮禁用 | 当前是否未保存 | 保存后再做发布预检 |
| 版本不存在 | 场景/套件是否发布该v | [版本](/manual/publishing#version) |

## 运行与证据 {#execution}

| 现象 | 先核对 | 下一步 |
| --- | --- | --- |
| 登录200但认证失败 | 业务码/Token路径/前缀 | [登录](/manual/login#errors) |
| context未验证 | 归属接口、路径与真实ID | [预检](/manual/preflight#states) |
| 一直queued | 执行器心跳/排队预算 | [调度状态](/manual/scheduling#scheduler) |
| 必需提取缺失 | 实际响应是否空列表/null | 核实样本，不用历史输出兜底 |
| 字段缺失/类型不符 | 路径及数字/字符串 | [字段](/manual/field-paths#missing-null) |
| 轮询超时 | 真实状态映射/次数/总预算 | [等待](/manual/async-wait#example) |
| 数据源权限/连接错误 | 服务端来源和专用身份 | [数据源](/manual/business-datasource#checks) |
| 数据变化/覆盖缺口 | 共享库前后事实/非空样本 | [回归限制](/manual/reception#limits) |
| 取消后仍有资源 | 已发送请求不可撤回、清理结果 | [清理](/manual/cleanup#flow) |
| 旅程blocked | 驱动/设备/构建/契约 | [能力](/manual/journeys#journey-preflight) |
| 新建评估禁用 | 当前未接真实评估服务 | [历史评估](/manual/evaluation#steps) |

## 给研发一份有效摘要 {#summary}

保留run ID、构建、环境、目标、资产发布版本、首错步骤、预期/实际和脱敏请求响应；不要复制密码/Token或原始客户记录。复跑能增加证据，但不会抹去原失败，附上两次run ID比只说“重跑好了”更容易判断。
