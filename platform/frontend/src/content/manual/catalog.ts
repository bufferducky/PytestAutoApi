// 正文目录与检索元信息；稳定 ID 与文件名一致。
export const manualGroups: { id: string; title: string }[] = [
  {
    "id": "start",
    "title": "新手入门"
  },
  {
    "id": "basics",
    "title": "基础概念"
  },
  {
    "id": "context",
    "title": "环境与登录"
  },
  {
    "id": "authoring",
    "title": "用例与编排"
  },
  {
    "id": "regression",
    "title": "正式回归"
  },
  {
    "id": "results",
    "title": "结果与排障"
  },
  {
    "id": "advanced",
    "title": "高级能力"
  },
  {
    "id": "examples",
    "title": "案例与速查"
  }
];

export const manualArticles: { id: string; title: string; group: string; category: string; summary: string; keywords: string[] }[] = [
  {
    "id": "overview",
    "title": "先看懂平台，再开始配置",
    "group": "start",
    "category": "认识平台",
    "summary": "把平台理解为一份能反复执行、保存证据的业务检查清单。",
    "keywords": [
      "入门",
      "场景",
      "套件",
      "整体链路"
    ]
  },
  {
    "id": "prepare",
    "title": "开始前准备哪些资料",
    "group": "start",
    "category": "第一次使用",
    "summary": "先把真正依赖的资料准备齐，避免在页面里试填大量未知值。",
    "keywords": [
      "前置条件",
      "准备",
      "秘密引用",
      "账号"
    ]
  },
  {
    "id": "first-query",
    "title": "跟着做：第一条接口查询",
    "group": "start",
    "category": "第一次使用",
    "summary": "用一条已确认的只读查询，学会配置、调试、发布和查看结果。",
    "keywords": [
      "第一条",
      "教程",
      "查询",
      "GET",
      "发布"
    ]
  },
  {
    "id": "http",
    "title": "HTTP：请求与响应是什么",
    "group": "basics",
    "category": "接口与数据",
    "summary": "把调用接口看成向服务提出一个明确问题，并检查它给出的回答。",
    "keywords": [
      "HTTP",
      "接口",
      "请求",
      "响应",
      "状态码"
    ]
  },
  {
    "id": "json",
    "title": "JSON：怎么填写对象、数组和值",
    "group": "basics",
    "category": "接口与数据",
    "summary": "先学会区分数字、字符串和对象，再填写平台的 JSON 输入框。",
    "keywords": [
      "JSON",
      "字符串",
      "数字",
      "对象",
      "数组",
      "格式错误"
    ]
  },
  {
    "id": "field-paths",
    "title": "字段路径：从响应里找到一个值",
    "group": "basics",
    "category": "取值与引用",
    "summary": "字段路径是取值路线，不是要填写的真实业务值。",
    "keywords": [
      "字段路径",
      "selector",
      "null",
      "缺失",
      "引用"
    ]
  },
  {
    "id": "environment",
    "title": "环境与公开变量",
    "group": "context",
    "category": "配置执行环境",
    "summary": "环境用于组织测试配置；实际请求地址仍要核对目标系统。",
    "keywords": [
      "environment",
      "base_url",
      "环境变量",
      "地址"
    ]
  },
  {
    "id": "target",
    "title": "目标系统：到底测哪个服务",
    "group": "context",
    "category": "配置目标",
    "summary": "目标把服务地址、登录协议、环境和上下文要求组合起来。",
    "keywords": [
      "target",
      "目标系统",
      "配置类型",
      "上下文"
    ]
  },
  {
    "id": "login",
    "title": "登录协议与令牌解析",
    "group": "context",
    "category": "配置登录",
    "summary": "登录不是只填一个地址，还需要请求格式、字段、密码处理和响应解析一致。",
    "keywords": [
      "认证",
      "Token",
      "登录",
      "Bearer",
      "MD5"
    ]
  },
  {
    "id": "identity",
    "title": "测试身份与秘密引用",
    "group": "context",
    "category": "配置身份",
    "summary": "身份说明“以谁的账号测试”，网页保存的是秘密名称，而不是密码。",
    "keywords": [
      "身份",
      "秘密",
      "secret_ref",
      "账号",
      "密码"
    ]
  },
  {
    "id": "binding",
    "title": "租户、项目与归属回读",
    "group": "context",
    "category": "配置业务空间",
    "summary": "同一个账号可能在多个空间有不同数据和权限，绑定防止测试跑错范围。",
    "keywords": [
      "绑定",
      "租户",
      "项目",
      "上下文",
      "归属"
    ]
  },
  {
    "id": "preflight",
    "title": "预检：哪些检查真的发请求",
    "group": "context",
    "category": "验证配置",
    "summary": "读懂配置、认证、归属、服务四栏，才知道目前验证到了哪一步。",
    "keywords": [
      "预检",
      "configuration",
      "authentication",
      "context",
      "service",
      "not_verified"
    ]
  },
  {
    "id": "scenario",
    "title": "场景与步骤：把业务检查拆清楚",
    "group": "authoring",
    "category": "建立场景",
    "summary": "先确定业务检查目标，再为每次请求命名和安排阶段。",
    "keywords": [
      "场景",
      "步骤",
      "稳定ID",
      "修订号"
    ]
  },
  {
    "id": "request",
    "title": "请求字段：地址、参数、请求体",
    "group": "authoring",
    "category": "配置请求",
    "summary": "按真实接口契约拆开填写，每部分只承担自己的职责。",
    "keywords": [
      "请求",
      "URL",
      "headers",
      "query",
      "body",
      "重放"
    ]
  },
  {
    "id": "parameters",
    "title": "公开参数：默认值与本次覆盖",
    "group": "authoring",
    "category": "传递数据",
    "summary": "把会变化的公开业务值从请求里提出来，复用同一场景。",
    "keywords": [
      "参数",
      "params",
      "schema",
      "默认",
      "覆盖"
    ]
  },
  {
    "id": "dependencies",
    "title": "依赖：为什么前一步失败后不能继续",
    "group": "authoring",
    "category": "传递数据",
    "summary": "后一步需要前一步的输出，必须把依赖写清楚。",
    "keywords": [
      "依赖",
      "depends_on",
      "blocked"
    ]
  },
  {
    "id": "extractors",
    "title": "变量提取：把响应交给后一步",
    "group": "authoring",
    "category": "传递数据",
    "summary": "提取是把本次响应中的某个值保存给当前场景的后续步骤。",
    "keywords": [
      "提取",
      "extractors",
      "outputs",
      "输出路径"
    ]
  },
  {
    "id": "assertions",
    "title": "断言：写清楚怎样才算正确",
    "group": "authoring",
    "category": "验证业务结果",
    "summary": "断言是可执行的验收条件，不能只检查接口有没有返回。",
    "keywords": [
      "断言",
      "equals",
      "期望",
      "业务码"
    ]
  },
  {
    "id": "advanced-assertions",
    "title": "高级断言：动态值、集合与业务关系",
    "group": "authoring",
    "category": "验证业务结果",
    "summary": "需要精确核对关联对象时，使用动态引用、明确类型和受控业务规则。",
    "keywords": [
      "expected_ref",
      "decimal",
      "datetime",
      "集合",
      "不变量"
    ]
  },
  {
    "id": "async-wait",
    "title": "异步任务：等待状态终态",
    "group": "authoring",
    "category": "异步流程",
    "summary": "任务提交一次，之后有界查询状态，避免反复创建同一业务。",
    "keywords": [
      "轮询",
      "wait_until",
      "异步",
      "状态",
      "预算"
    ]
  },
  {
    "id": "debugging",
    "title": "调试当前草稿与单步",
    "group": "authoring",
    "category": "调试与修订",
    "summary": "调试执行眼前编辑，不自动保存或发布，也不是离线模拟。",
    "keywords": [
      "调试",
      "未保存",
      "单步",
      "outputs"
    ]
  },
  {
    "id": "import-export",
    "title": "导入、导出与迁移",
    "group": "authoring",
    "category": "导入与复用",
    "summary": "旧定义转成草稿后仍需核对真实契约，导入成功不是测试通过。",
    "keywords": [
      "YAML",
      "导入",
      "导出",
      "迁移"
    ]
  },
  {
    "id": "publishing",
    "title": "保存、预检、发布是三个动作",
    "group": "regression",
    "category": "固定版本",
    "summary": "先保存编辑，再检查定义，最后冻结供正式回归引用。",
    "keywords": [
      "发布",
      "草稿",
      "版本",
      "预检",
      "归档"
    ]
  },
  {
    "id": "suites",
    "title": "套件：组合固定版本场景",
    "group": "regression",
    "category": "组织回归",
    "summary": "套件把一批已发布场景组合为同一次回归，固定顺序和预算。",
    "keywords": [
      "套件",
      "场景引用",
      "版本",
      "预算"
    ]
  },
  {
    "id": "running",
    "title": "计划预览与真实运行",
    "group": "regression",
    "category": "执行固定版本",
    "summary": "先确认本次会测谁、用哪版、做什么，再实际执行。",
    "keywords": [
      "运行",
      "计划",
      "live",
      "构建"
    ]
  },
  {
    "id": "scheduling",
    "title": "调度：按时间重复执行回归",
    "group": "regression",
    "category": "定时执行",
    "summary": "固定套件和环境，预览时间，再启用自动真实运行。",
    "keywords": [
      "Cron",
      "调度",
      "时区",
      "暂停",
      "排队"
    ]
  },
  {
    "id": "release-report",
    "title": "发布回归摘要与证据范围",
    "group": "regression",
    "category": "审阅证据",
    "summary": "汇总某个构建的选定运行，不自动批准部署。",
    "keywords": [
      "报告",
      "report_only",
      "strict",
      "发布门槛"
    ]
  },
  {
    "id": "dashboard",
    "title": "工作台统计：每个数字算了什么",
    "group": "results",
    "category": "查看概况",
    "summary": "卡片数字有各自统计范围，不一定等于你眼前列表长度。",
    "keywords": [
      "仪表盘",
      "统计",
      "成功率",
      "运行数"
    ]
  },
  {
    "id": "diagnostics",
    "title": "执行结果：状态、首错与复跑",
    "group": "results",
    "category": "定位失败",
    "summary": "先看首个失败步骤，再看预期实际和脱敏请求响应，避免被后续阻塞淹没。",
    "keywords": [
      "结果",
      "失败",
      "诊断",
      "复跑",
      "取消"
    ]
  },
  {
    "id": "run-filters",
    "title": "筛选与同口径趋势",
    "group": "results",
    "category": "检索结果",
    "summary": "筛选只改变你查看哪些历史记录，不会改运行、切换目标或执行测试。",
    "keywords": [
      "筛选",
      "趋势",
      "ISO",
      "环境ID",
      "构建"
    ]
  },
  {
    "id": "evidence",
    "title": "附件与证据保留",
    "group": "results",
    "category": "管理证据",
    "summary": "证据用于复盘，不因添加一份附件就自动证明业务通过。",
    "keywords": [
      "附件",
      "保留",
      "回收",
      "证据"
    ]
  },
  {
    "id": "cleanup",
    "title": "取消、超时后怎么处理资源",
    "group": "results",
    "category": "恢复测试环境",
    "summary": "主流程结束不代表数据已清理，必须查看本运行的资源账本。",
    "keywords": [
      "清理",
      "取消",
      "超时",
      "资源账本",
      "预检令牌"
    ]
  },
  {
    "id": "business-datasource",
    "title": "业务数据源：独立核对接口结果",
    "group": "advanced",
    "category": "数据库核验",
    "summary": "平台自己的状态库与被测业务库是两回事；业务数据源为断言提供独立期望。",
    "keywords": [
      "数据库",
      "datasource",
      "独立期望",
      "服务端配置"
    ]
  },
  {
    "id": "reception",
    "title": "言迹查询包与接诊筛选回归",
    "group": "advanced",
    "category": "数据库核验",
    "summary": "用实际API结果对照独立测试库事实，发现漏查、多查、错误总数与分页问题。",
    "keywords": [
      "言迹",
      "接诊",
      "筛选",
      "分页",
      "独立期望"
    ]
  },
  {
    "id": "fixtures",
    "title": "测试资源fixture：准备与退出清理",
    "group": "advanced",
    "category": "测试资源",
    "summary": "fixture把获取、使用和清理绑定起来，避免重复测试污染环境。",
    "keywords": [
      "fixture",
      "资源定义",
      "create",
      "lease",
      "read_only"
    ]
  },
  {
    "id": "resource-pools",
    "title": "专属资源池与租约",
    "group": "advanced",
    "category": "测试资源",
    "summary": "资源池登记明确可测试的对象，租约说明当前谁能用它。",
    "keywords": [
      "池",
      "租约",
      "owner",
      "generation",
      "expires_at"
    ]
  },
  {
    "id": "media",
    "title": "测试媒体manifest与校验",
    "group": "advanced",
    "category": "测试资源",
    "summary": "manifest是受控测试文件的资料卡，不是上传客户录音入口。",
    "keywords": [
      "manifest",
      "媒体",
      "WAV",
      "MP3",
      "hash"
    ]
  },
  {
    "id": "coverage",
    "title": "覆盖账本：风险、契约与真实证据",
    "group": "advanced",
    "category": "覆盖与评估",
    "summary": "代码里出现一条接口调用，只是观察线索，不等于该风险已真实验证。",
    "keywords": [
      "覆盖",
      "风险",
      "契约",
      "S01",
      "发布必需"
    ]
  },
  {
    "id": "journeys",
    "title": "Web与Android界面旅程",
    "group": "advanced",
    "category": "界面自动化",
    "summary": "界面旅程执行真实页面或设备动作，不能用HTTP请求成功替代。",
    "keywords": [
      "web",
      "android",
      "旅程",
      "runner",
      "语义定位",
      "Appium"
    ]
  },
  {
    "id": "quarantine",
    "title": "隔离与解除：保留不稳定历史",
    "group": "advanced",
    "category": "界面自动化",
    "summary": "隔离记录说明为什么暂不采纳某旅程，解除也不自动产生成功证据。",
    "keywords": [
      "隔离",
      "quarantine",
      "解除",
      "历史"
    ]
  },
  {
    "id": "evaluation",
    "title": "历史AI与语音评估：能看什么",
    "group": "advanced",
    "category": "覆盖与评估",
    "summary": "目前只提供历史查询与同口径对比，新评估执行已禁用。",
    "keywords": [
      "AI",
      "语音",
      "评估",
      "历史",
      "禁用"
    ]
  },
  {
    "id": "multi-step",
    "title": "完整案例：登录后从列表查到详情",
    "group": "examples",
    "category": "跟着业务做",
    "summary": "用同一组客户数据串起登录、项目、参数、提取、断言与固定版本回归。",
    "keywords": [
      "完整案例",
      "列表",
      "详情",
      "参数传递",
      "登录",
      "发布"
    ]
  },
  {
    "id": "glossary",
    "title": "术语速查：看到陌生词从这里找",
    "group": "examples",
    "category": "查词与查错",
    "summary": "先用一句话建立概念，再进入对应的字段和操作说明。",
    "keywords": [
      "术语",
      "名词",
      "字典",
      "速查"
    ]
  },
  {
    "id": "troubleshooting",
    "title": "常见问题：从报错找到下一步",
    "group": "examples",
    "category": "查词与查错",
    "summary": "按出现的具体提示排查，不通过删保护字段或修改期望值来强行变绿。",
    "keywords": [
      "错误",
      "报错",
      "常见问题",
      "排查",
      "配置不来"
    ]
  }
];
