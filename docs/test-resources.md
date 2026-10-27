# 测试数据与清理

Cases页的资源面板维护fixture不可变定义、专属池和媒体；Runs页提供该运行的资源账本、只读清理预检和本次预检清理动作。

## 声明fixture

定义选择create、lease或read_only，确认测试接口/恢复契约后保存。create提供创建/删除请求及ID路径；lease可声明原值查询/恢复；read_only必须精确指向已确认专属池对象，不取第一条数据。

场景高级元数据中的fixtures示例：

```json
{
  "fixtures": [{"name":"item","definition_id":"已保存定义ID","version":1,"depends_on":[]}]
}
```

请求用`{{fixtures.item.id}}`；创建名字可用`{{runtime.test_prefix}}`。框架前缀区分run、场景scope和fixture，连续或并发执行不复用历史对象。借用原值可引用`fixtures.item.original`，结构由已确认查询决定。

发布与计划预览不会创建资源；预览列资源策略/版本和副作用。主流程退出仍按获取反序清理，失败不掩盖主断言。租约过期不代表业务对象已恢复，不会自动发给下一个run。

## 处理中断或清理失败

先打开该run的资源/清理预检，核对所属target/项目和对象，提交返回的preflight_token再清理。资源状态改变后令牌失效。自动/手动清理都不能拿任意对象ID作为删除目标。

创建请求结果不明或缺ID时为ownership_unknown，系统不会按名字搜索后批量删。人工确认必须先核查并提供依据；原关联或秘密不足时保留待办，不把脱敏值当真实参数发送。

启动对账在取得单实例worker锁后进行。中断run及资源保留，绝不自动重新创建或删对象；需要按账本对账与恢复。SQLite版本4迁移前创建resources-backup，不清空工作库。

## 测试媒体

将合成/授权且脱敏的音频放在Files/test-media，用manifest登记sha256、byte_size、duration_seconds、format、language、noise、source、authorized/redacted和applicable_scenarios。

WAV校验真实时长；MP3当前做文件头、hash和体积检查，不能据此声称语音内容/解码质量通过。超过16MiB、路径越界、hash/大小不匹配在上传前拒绝。

上传能力供worker/provider调用，必须已确认上传契约，且URL源属于target本身或明确allowed_upload_origins。不跟重定向，结果不保存签名URL。只有manifest预检时会明确显示“尚未确认上传契约”，不伪造上传成功。

## 历史人设样例

旧demo已移除“首条人设/首个评估包”提取。真实过渡入口必须显式给出专属persona_id/evaluate_pkg_id；未提供直接拒绝。正式日常场景应使用fixture/专属池，由R07补公司契约和恢复断言；旧脚本与业务 YAML 示例已移除；前端 YAML 内容导入保留，不代表已经完成相同改造。

本轮证据来自本地HTTP服务、临时SQLite、合成WAV和子进程中断测试；没有修改公司数据或使用真实客户录音。

资源准备阶段也遵守取消与超时。创建多个资源时，每次分配前都会检查停止信号；首个对象已创建后取消，只清理首个，不再尝试创建第二个，也不继续主业务。API场景和UI旅程共享这一规则。超时显示timed_out，UI尚未执行的动作显示blocked；清理仍使用自己的预算。
