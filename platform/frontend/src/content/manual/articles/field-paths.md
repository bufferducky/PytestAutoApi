# 字段路径：从响应里找到一个值

字段路径是取值路线，不是要填写的真实业务值。

## 从一份响应走到一个值 {#path}

```json
{"code":200,"data":{"records":[{"id":"customer-001","name":"测试客户"}],"total":1}}
```

| 路径 | 取到的值 | 逐步理解 |
| --- | --- | --- |
| code | 200 | 根对象的 code |
| data.total | 1 | data 里面的 total |
| data.records.0.id | "customer-001" | data → records → 第 0 项 → id |

本平台普通字段路径用点分隔，数组序号也写成点路径。不要把示例值 `customer-001` 填到“字段路径”；字段路径应该填 `data.records.0.id`。

## 字段缺失与 null 不一样 {#missing-null}

`{"data":{"name":null}}` 中 name 存在但为空；`{"data":{}}` 中 name 没有出现。普通 equals 比较缺字段会报错。需要区别时使用 `exists`、`is_null`、`is_missing`，不要用期望 null 一口气代表所有情况。

## 三种地方的写法不要混用 {#three-forms}

| 使用处 | 写法 | 含义 |
| --- | --- | --- |
| 断言/提取的字段路径 | data.records.0.id | 从当前选定来源取值 |
| 请求中的模板 | {{outputs.list_customers.id}} | 把前置输出放进请求 |
| 断言的期望引用 | outputs.list_customers.id | 直接取上下文，不加双花括号 |

先用[变量提取](/manual/extractors#extractors)把响应值写入 outputs，后续才有值可引用；仅写路径不会自动生成数据。

## 字段路径 {#selector}

它指定当前断言从哪里取值。先选来源，再写对应来源内部的路径；响应头、响应体和上下文的根不同。

**在哪里使用：** 步骤 → 响应断言 → 字段路径。

**填写或阅读示例：** 响应体填 `data.records.0.id`；HTTP 状态来源通常不需要响应体字段路径。

**应该看到什么：** 示例响应会取到字符串 `customer-001`，再交给比较规则判断。

**常见错误：** 把实际 ID 填进路径，或把 `$.data.records[0].id` 粘到普通 field_path 配置。普通路径优先使用点语法。
