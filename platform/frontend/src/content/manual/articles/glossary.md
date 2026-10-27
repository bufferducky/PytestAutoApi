# 术语速查：看到陌生词从这里找

先用一句话建立概念，再进入对应的字段和操作说明。

## 术语索引 {#terms}

| 界面词 | 用人话解释 | 深入阅读 |
| --- | --- | --- |
| environment 环境 | 配置与记录所属的执行空间 | [环境](/manual/environment#environment) |
| target 目标 | 实际服务地址和协议 | [目标](/manual/target#target) |
| identity 身份 | 测试时使用哪个账号配置 | [身份](/manual/identity#identity) |
| binding 绑定 | 此身份在哪个租户项目执行 | [绑定](/manual/binding#binding) |
| secret_ref 秘密引用 | 服务端秘密的名称，不是秘密值 | [引用](/manual/identity#secret-ref) |
| schema | 参数名、类型和必填规则 | [参数规则](/manual/parameters#schema) |
| selector 字段路径 | 逐层取值的路线 | [字段路径](/manual/field-paths#selector) |
| params | 本次公开输入 | [公开参数](/manual/parameters#parameters) |
| extractors | 从本步响应保存输出的规则 | [提取](/manual/extractors#extractors) |
| outputs | 前面步骤本次产生的输出 | [依赖](/manual/dependencies#dependencies) |
| assertion 断言 | 什么结果才算正确 | [断言](/manual/assertions#design) |
| expected_ref | 从本次上下文取期望值 | [动态期望](/manual/advanced-assertions#expected-ref) |
| revision/r | 可编辑草稿或配置的修订号 | [修订](/manual/scenario#configuration-revision) |
| version/v | 已发布的固定快照号 | [版本](/manual/publishing#version) |
| run | 一次实际执行记录 | [运行](/manual/running#run) |
| fixture | 测前获取、测后清理的资源协议 | [资源](/manual/fixtures#fixture) |
| lease 租约 | 谁暂时持有哪个专属资源 | [资源池](/manual/resource-pools#lease-state) |
| manifest | 受控媒体的元信息清单 | [媒体](/manual/media#media) |
| runner | 执行Web/Android旅程的能力 | [旅程](/manual/journeys#runner) |
| report_only | 汇总证据，不批准部署 | [报告](/manual/release-report#report-mode) |

## 三种“通过”不要混用 {#passed}

配置可解析 ≠ 已真实登录；HTTP200 ≠ 业务断言通过；单次断言通过 ≠ 所有发布条件满足。先确认你在哪个入口、查看哪一栏、验证哪个范围，再报告结果。
