# 断言：写清楚怎样才算正确

> 当前界面入口：在用例工作区选择左侧步骤，再打开“断言”标签页编辑规则；完整 JSON 和高级断言字段仍可展开。保存会校验所有步骤，隐藏步骤中的格式错误也会自动定位。

断言是可执行的验收条件，不能只检查接口有没有返回。

## 先验证业务码，再验证对象 {#design}

详情响应 `{"code":200,"data":{"id":"customer-001"}}` 可检查HTTP码、业务码和对象ID三个不同层次。

| 目标 | 来源 | 字段 | 规则 | 期望 |
| --- | --- | --- | --- | --- |
| 通信正常 | status_code | 空 | equals | 200 |
| 业务正常 | response_body | code | equals | 200 |
| 对象正确 | response_body | data.id | equals | expected_ref=outputs.list_customers.id |

第三条在高级选项填期望引用，不将路径文本填到期望JSON。

## 规则速查 {#rules}

| 规则 | 含义 | 适用例子 |
| --- | --- | --- |
| equals / not_equals | 相等/不等 | code为数字200 |
| contains / not_contains | 包含/不包含 | 名称包含测试 |
| exists | 字段存在 | data.records出现 |
| is_null / is_missing | 空值/缺失 | 可选字段明确为空或不返回 |
| greater_than / greater_or_equal | 大于/不小于 | total不小于1 |
| less_than / less_or_equal | 小于/不大于 | 数量不超上限 |
| type_is / schema | 类型/受支持结构 | records是array |
| unique | 集合无重复 | ID集合不重复 |
| set_equals / keyed_equals | 集合或按唯一key的对象相等 | 对齐ID和字段 |

缺字段不自动等于null，集合与精确类型见[高级断言](/manual/advanced-assertions#collections)。

## 断言来源 {#assert-source}

response_body是响应体，response_headers是响应头，status_code是HTTP码，context是运行上下文。

**在哪里使用：** 步骤 → 响应断言 → 来源。

**填写或阅读示例：** 业务码选response_body路径code，HTTP选status_code期望200。

**应该看到什么：** 诊断source_ref说明究竟验证什么。

**常见错误：** 把业务code当HTTP状态，或选上下文仍填响应body路径。

## 比较规则 {#operator}

取值后如何判断，必须匹配数据类型和意图。

**在哪里使用：** 步骤 → 响应断言 → 比较规则。

**填写或阅读示例：** code用equals，缺字段用is_missing，数组去重用unique。

**应该看到什么：** 展示预期、实际和规则结果。

**常见错误：** 用contains粗略检查应精确相等的对象ID。

## 期望 JSON {#expected}

填合法JSON值，保留数字、字符串、对象和布尔类型。

**在哪里使用：** 步骤 → 响应断言 → 期望JSON。

**填写或阅读示例：** 数字 `200`；字符串 `"测试客户"`；开关 `true`。

**应该看到什么：** 按规则比较，类型差异不会被无条件抹平。

**常见错误：** 字符串不加引号，或将200写为"200"。

## 完整断言 JSON {#assert-json}

与表单同步的同一份规则数组，可保留高级字段。

**在哪里使用：** 步骤 → 编辑完整断言JSON。

**填写或阅读示例：** `[{"name":"业务码","source":"response_body","selector":"code","operator":"equals","expected":200}]`。

**应该看到什么：** 表单与数组同步，格式错明确提示。

**常见错误：** 把一个对象填进数组框，或以为JSON是第二套独立规则。
