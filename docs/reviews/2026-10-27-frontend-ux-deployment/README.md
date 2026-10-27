# Element Plus 全量工作台服务器发布

2026-10-27，按用户“先提交再部署服务器，我看看效果”执行，已完成代码提交推送、独立发布包构建、服务器冷备份、切换及公网验收。

- 访问入口：[工作台](https://test.ysspace2099.com/dashboard)、[用例编辑](https://test.ysspace2099.com/cases)、[使用手册](https://test.ysspace2099.com/manual)。沿用原账号认证。
- 代码提交：`1a3e797ec06380d1debd9c9e8c746290bcbf01e8`，已推送 `master`。
- 新目录：`/home/ubuntu/pytestautoapi/releases/20261027-frontend-ux-1a3e797`，`current` 在公网验收通过后原子切换。
- 上一版本：`20261027-reception-f8ce7cb`，旧目录、镜像与现有数据卷继续保留。
- 备份：`/home/ubuntu/pytestautoapi/backups/20261027-frontend-ux-1a3e797`，停写停库后备份 MySQL 和附件卷，归档可读及 SHA-256 校验通过。

## 提交与本地检查

提交包含前端重构、Element Plus 2.14.7、使用手册、关联规范/回归及验收记录。原工作区的本地启动脚本、根 README 等其他改动保留未提交。发布包从该固定提交的干净隔离工作区生成，不从混合工作区复制运行代码。

标准发布脚本八项检查全部通过：Ruff、Python **354 passed / 14 skipped**、生产构建与类型检查、三组前端可靠性/变量/未保存保护检查、真实工作台浏览器 **1 passed in 52.30s**。跳过项包括需独立服务或显式开启的集成检查，未将其称为已通过的公司业务验收。

发布前发现两份旧环境回归和公网布局门槛仍基于原生控件、六导航及手机宽度，已适配真实组件库操作、七主导航和三个桌面宽度，业务断言保留。公网验证工具本地 Chromium 回归 **24 passed**。

## 服务器与数据保全

镜像隔离检查：非 root uid 10001，16 项契约、650 条研究观察及 Chromium 156.0.8078.4 通过；本地 HTTP worker 1 请求/1 断言成功，重建 app 后证据保留。后端构建全部命中现有缓存，运行内容与旧镜像一致，本轮实际更新前端静态资源。

启动后 backend/MySQL 健康，web 正常。切换前、停写后、启动后及 accept 前均核对平台 API 内容指纹。

| 资产 | 切换前 | 切换后 |
| --- | --- | --- |
| 环境 | 4 | 4 |
| 场景 | 20 | 20 |
| 套件 | 3 | 3 |
| 调度 | 3 | 3 |
| 运行 | 10 | 10 |
| 目标 / 身份 / 绑定 | 8 / 3 / 3 | 8 / 3 / 3 |

原 ID、草稿、版本、环境详情及运行内容指纹一致；worker 可用、queued=0、last_error=null；没有开启调度、重放旧任务或调用公司业务。

## 公网验收

- 未认证首页和 API 返回 401，原认证后健康正常。
- 17 个入口静态资源的集合与 SHA-256 匹配固定提交构建产物。
- 八路由 × 1280/1440/1920px，共 24 组页面默认/展开浏览器检查通过，无警告；应用脚本和请求错误检查通过。
- 首次验收出现浏览器网络请求失败，保留 [首次失败回执](./public-first-attempt.json)。独立首页复查零请求/脚本错误、七导航及布局正常，完整重跑全部通过；未修改应用或放宽门槛，也未篡改失败回执。
- 最终 [公网回执](./public.json) 绑定同一 commit/tag/manifest，上传服务器后 accept 成功。

机器记录：[deployment.json](./deployment.json)、[manifest.json](./manifest.json)。本次只使用 GET 进行公网验收，浏览器继续阻止写请求、跨源和重定向；认证秘密不进入日志、发布包或仓库。

## 回滚

需要退回应用时，复用此次上传的工具：

```sh
sh /home/ubuntu/pytestautoapi/incoming/20261027-frontend-ux-1a3e797/tools/server_release.sh rollback 20261027-frontend-ux-1a3e797 --apply
```

工具会先备份当前数据，再使用旧应用与当前卷，不恢复旧数据库、不使用 down -v。新写入数据继续保留；有活动运行、启用调度或其他发布接管时按 SOP 处理。
