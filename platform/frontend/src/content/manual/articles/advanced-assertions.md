# 高级断言：动态值、集合与业务关系

需要精确核对关联对象时，使用动态引用、明确类型和受控业务规则。

## 集合与精确对象 {#collections}

set_equals的设计含义是忽略顺序并保留重复数量，但当前实现对字符串、布尔和对象数组存在已知比较限制，相同内容换序也可能失败，暂不要将它用作这些集合的可靠判断。纯数值集合与对象按key比较应分别核对；对象数组优先用keyed_equals，按extras.key指定唯一字段对齐，重复key明确报错。

```json
[{"name":"集合一致","selector":"data.records","operator":"keyed_equals","expected_ref":"outputs.before.records","extras":{"key":"id"}}]
```

需要已有前置输出并依赖before。只检查某个对象时，完整JSON可用select_by指定key和value/value_ref，不盲用数组第一条。

## 类型与时间 {#normalization}

金额协议单位一致后可选decimal；datetime用带时区ISO文本。数字时间戳必须在normalization声明unit为seconds或milliseconds，不按位数猜。缺时区日期还要明确timezone。

## 业务规则 {#business-rules}

count_delta@1验证前后数量差；unchanged@1验证与基线一致；relation@1结合动态期望验证业务关联。规则是已注册版本，不接受任意Python或SQL。普通比较足够时不要额外增加规则。

## 动态期望引用 {#expected-ref}

从params、fixtures或前置outputs读取本次期望值，引用必须存在。

**在哪里使用：** 高级断言 → 或期望引用。

**填写或阅读示例：** `outputs.list_customers.id`，不用双花括号，同时依赖list_customers。

**应该看到什么：** 详情ID与本次列表提取ID比较。

**常见错误：** 将路径文本填进期望字符串，或前置输出未声明。

## 显式值类型 {#value-type}

native按JSON类型，decimal用于精确小数，datetime用于明确时区/单位的时间。

**在哪里使用：** 高级断言 → 显式值类型。

**填写或阅读示例：** 时间 `2026-10-27T09:00:00+08:00` 配datetime；金额单位一致后decimal。

**应该看到什么：** 双方按明确规则规范化。

**常见错误：** 元与分直接比较，或自动猜时间单位。

## 比较容差 {#tolerance}

有限非负偏差；datetime单位秒，decimal按数值差，0为严格偏差。

**在哪里使用：** 高级断言 → 容差。

**填写或阅读示例：** 时间允许1秒设1，精确金额设0。

**应该看到什么：** 超出约定差异仍失败。

**常见错误：** 填负值或巨大容差掩盖问题。

## 业务不变量 {#invariant}

选择受控版本化关系规则，提供所需基线和期望。

**在哪里使用：** 高级断言 → 业务不变量。

**填写或阅读示例：** 数量增加1：count_delta@1、baseline_ref为操作前计数、expected为1。

**应该看到什么：** 比较实际增量与1，不只比较当前数量。

**常见错误：** 只选规则不提供真实基线。

## 前置快照引用 {#baseline}

操作前的真实值，与当前实际值对应两个时点。

**在哪里使用：** 高级断言 → 前置快照引用。

**填写或阅读示例：** 先提取 `outputs.before.count`，后步显式依赖before并填该引用。

**应该看到什么：** 缺引用会报错，不以当前值冒充基线。

**常见错误：** 用当前响应同时当基线和实际值。

### 类型、结构与唯一性的具体写法 {#type-schema-unique}

检查数组类型时operator选type_is，期望JSON填字符串 `"array"`，不能裸填array。结构规则只支持type、required、properties、items、enum；不是完整JSON Schema实现，其他关键字会被拒绝。

```json
[{"name":"详情结构","selector":"data","operator":"schema","expected":{"type":"object","required":["id"],"properties":{"id":{"type":"string"}}}}]
```

unique比较整个数组元素，不是默认按id去重：两个对象id相同但其他字段不同，不会因此被unique视为重复。若要验证业务ID唯一，应先取得明确ID数组或使用已确认的受控规则；不要误以为勾unique就完成关联唯一性核验。

当前set_equals对非数值集合的实现限制是既存问题，不能靠特殊转义期望来绕过。只有响应和期望本身就是具有唯一业务键的对象数组时，才可使用keyed_equals；平台目前没有把字符串数组自动转换为对象数组的入口。字符串数组忽略顺序比较暂没有等价替代，请待规则修复，或仅在真实需求本来要求顺序时使用equals（有序比较，语义不同）。不要把这一实现限制误报为被测业务一定有问题。
