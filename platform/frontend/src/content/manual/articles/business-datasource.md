# 业务数据源：独立核对接口结果

> 当前界面入口：进入用例工作区“接入与高级”，打开业务查询包和接诊筛选回归，选择业务数据源并按需验证；目标、身份和项目先在“场景设置”中指定。

平台自己的状态库与被测业务库是两回事；业务数据源为断言提供独立期望。

## 网页选择前先注册 {#setup}

服务运行人员在API和worker进程中配置同一份公开来源及秘密引用；网页只选择已注册来源，不输入数据库口令或任意SQL。普通HTTP场景不依赖此能力。

公开配置的形状如下，示例地址/库名/ID全部替换为已确认测试资源：

```json
[{
  "id":"customer-test-db",
  "name":"测试只读业务核验",
  "host":"<测试库地址>",
  "port":3306,
  "schema":"<业务库名>",
  "username_secret_ref":"env:PYTA_SECRET_TEST_DB_USER",
  "password_secret_ref":"env:PYTA_SECRET_TEST_DB_PASSWORD",
  "allowed_target_origin":"https://api.example.test",
  "tenant_id":"<测试租户ID>",
  "project_id":"<专用项目ID>",
  "max_rows":5000,
  "connect_timeout_seconds":5,
  "query_timeout_seconds":10
}]
```

配置由服务端的PYTA_BUSINESS_DATASOURCES_JSON读取；host/port/schema定位数据库，allowed_target_origin限制匹配API来源，tenant/project限制已确认范围，max_rows和timeout限制读取预算。真实秘密另由PYTA_SECRET环境变量提供。只配API没配worker，会出现页面可选但运行缺配置。

## 两种检查别混淆 {#checks}

“检查数据源配置”只看引用与绑定，不连接数据库；“验证数据库连接与权限”会立即连测试库做只读核对。切换目标、用户、项目或来源后旧预检不再代表当前组合。

该能力目前是受控的言迹接诊核验，不是全系统通用SQL客户端；不能给任意库名就期望自动生成断言。

## 业务数据源 {#business-datasource}

从服务端已注册来源选取，与平台MySQL独立，页面不保存口令。

**在哪里使用：** 用例 → 接诊筛选回归 → 业务数据源。

**填写或阅读示例：** 来源注册完成后刷新列表，选对应言迹测试库，核对目标/身份/项目。

**应该看到什么：** 可做配置检查；尚不等于连通。

**常见错误：** 把平台状态库当业务库，或只在API进程配来源。

## 数据库连接与权限预检 {#business-datasource-probe}

立即真实只读连接并核对专用用户、项目及要求的权限，运行还会再核验。

**在哪里使用：** 接诊筛选回归 → 验证数据库连接与权限。

**填写或阅读示例：** 选正确来源、预期用户ID和绑定后点击验证。

**应该看到什么：** 分别看到configuration、connection、permission结果。

**常见错误：** 以为不连库，或以一次通过永久证明权限。
