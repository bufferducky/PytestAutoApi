"""言迹测试环境的只读接入包；场景进入既有版本真源，不另建执行引擎。"""

from urllib.parse import urlsplit

from fastapi import HTTPException


def query_drafts(target_ref, identity_ref, binding_ref, expected_user_id):
    """期望来自明确测试身份/绑定；不从业务列表首行抽取待测对象。"""
    scope = [
        {"name": "tenant", "selector": "data.tenantId", "expected_ref": "identity.tenant_id"},
        {"name": "project", "selector": "data.deptId", "expected_ref": "identity.project_id"},
        {"name": "user", "selector": "data.userId", "expected": expected_user_id},
    ]
    definitions = [
        ("identity", "身份与当前项目", "/api/v1/user/role_info", {}, scope),
        (
            "menus",
            "角色可见菜单",
            "/api/v1/permission/manager_permission_menu/APP_GP",
            {},
            [{"name": "menu-list", "selector": "data", "operator": "type_is", "expected": "array"}],
        ),
        (
            "receptions",
            "接诊列表结构",
            "/api/v1/reception_form/page",
            {"pageNum": 1, "pageSize": 10},
            [
                {
                    "name": "total",
                    "selector": "data.total",
                    "operator": "greater_or_equal",
                    "expected": 0,
                },
                {
                    "name": "rows",
                    "selector": "data.rows",
                    "operator": "type_is",
                    "expected": "array",
                },
            ],
        ),
        (
            "personas",
            "人设分页结构",
            "/api/v1/practice/person/page",
            {"pageNum": 1, "pageSize": 10},
            [
                {
                    "name": "total",
                    "selector": "data.total",
                    "operator": "greater_or_equal",
                    "expected": 0,
                },
                {
                    "name": "records",
                    "selector": "data.records",
                    "operator": "type_is",
                    "expected": "array",
                },
            ],
        ),
    ]
    for key, name, path, query, assertions in definitions:
        yield (
            key,
            {
                "name": "言迹查询 · " + name,
                "module": "言迹/查询smoke",
                "target_ref": target_ref,
                "identity_ref": identity_ref,
                "identity_binding_ref": binding_ref,
                "priority": "P0",
                "tags": ["yanji", "auth-smoke", "query-only"],
                # 查询 smoke 只验证部分风险，不自动解除 S01—S16 整项覆盖。
                "source": {"kind": "yanji-query-pack", "version": 1, "scope": "query_smoke"},
                "steps": [
                    {
                        "step_id": key,
                        "name": name,
                        "contract_confirmed": True,
                        "operation_kind": "query",
                        "safe_to_replay": True,
                        "request": {"method": "GET", "url": "{{host}}" + path, "query": query},
                        "assertions": [
                            {"name": "business-code", "selector": "code", "expected": 200},
                            *assertions,
                        ],
                    }
                ],
            },
        )


def import_query_pack(assets, payload):
    """导入仅写草稿，不登录、不发业务请求、不覆盖操作者已有编辑。"""
    required = ["target_ref", "identity_ref", "binding_ref", "expected_user_id"]
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
        raise HTTPException(400, "请选择目标/身份/项目绑定并填写明确的预期用户 ID")
    snapshot = assets.context.snapshot(
        payload["target_ref"], payload["identity_ref"], payload["binding_ref"]
    )
    target = snapshot["target"]
    parsed = urlsplit(target["base_url"])
    if parsed.scheme != "https" or parsed.hostname != "api-test.yanjiai.com":
        raise HTTPException(400, "yanji_test_only: 言迹接入包仅允许 API 测试环境")
    if not target["requires_context"] or target["auth"]["mode"] != "password":
        raise HTTPException(400, "言迹查询包需要已确认密码登录与项目绑定")
    created = []
    for key, draft in query_drafts(*(payload[key] for key in required)):
        # 每个绑定有独立包，重复导入不制造副本或覆盖本地编辑。
        from pyta_platform_backend.repositories.asset_repository import asset_hash

        identifier = "yanji-query-" + asset_hash([payload["binding_ref"], key])[:24]
        try:
            existing = assets.repository.get("scenarios", identifier)
        except KeyError:
            existing = assets.create("scenarios", draft, identifier=identifier)
        created.append(existing)
    return {
        "assets": created,
        "network_executed": False,
        "scope": "query_smoke_only",
        "note": (
            "只创建查询草稿；需预检/发布/真实执行。"
            "未解除项目切换、权限拒绝、业务写入及 Web 未验证项。"
        ),
    }


def import_web_query(journeys, payload):
    """登录和可见查询的 Web smoke；不冒充 W01—W04 完整验收。"""
    keys = ["target_ref", "identity_ref", "binding_ref", "chromium_version", "expected_user_id"]
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in keys):
        raise HTTPException(400, "请选择 Web 测试目标/身份/绑定、浏览器版本和预期用户 ID")
    snapshot = journeys.context.snapshot(
        payload["target_ref"], payload["identity_ref"], payload["binding_ref"]
    )
    target = snapshot["target"]
    if target["base_url"] != "https://web-test.yanjiai.com":
        raise HTTPException(400, "yanji_test_only: 旅程仅允许指定 Web 测试站点")
    if target["auth"]["password_transform"] != "md5" or not target.get("request_headers", {}).get(
        "User-Agent"
    ):
        raise HTTPException(400, "Web 使用原始密码引用；API 登录需 MD5 和独立终端请求头")
    if target["auth"]["mode"] != "password":
        raise HTTPException(400, "API 回读需要已确认密码登录")
    actions = [
        {"step_id": "open", "name": "打开测试登录页", "action": "navigate", "path": "/login"},
        {
            "step_id": "username",
            "name": "填写账号引用",
            "action": "fill",
            "value_ref": "identity.username",
            "selector": {"strategy": "placeholder", "value": "请输入用户名"},
        },
        {
            "step_id": "password",
            "name": "填写密码引用",
            "action": "fill",
            "value_ref": "identity.password",
            "selector": {"strategy": "placeholder", "value": "请输入密码"},
        },
        {
            "step_id": "login",
            "name": "登录",
            "action": "click",
            "selector": {"strategy": "role", "value": "button", "name": "登录"},
        },
        {
            "step_id": "menu",
            "name": "登录后可见客户中心",
            "action": "assert_visible",
            "selector": {"strategy": "role", "value": "menuitem", "name": "客户中心"},
        },
        {
            "step_id": "requested_receptions",
            "name": "打开用户指定的测试接诊入口",
            "action": "navigate",
            "path": "/visitor-register?roleId=&routerId=0",
        },
        {
            "step_id": "query",
            "name": "接诊查询入口可见",
            "action": "assert_visible",
            "selector": {"strategy": "role", "value": "button", "name": "查询"},
        },
    ]
    first = next(
        query_drafts(
            payload["target_ref"],
            payload["identity_ref"],
            payload["binding_ref"],
            payload["expected_user_id"],
        )
    )[1]["steps"][0]
    actions.append(
        {
            "step_id": "api_context",
            "name": "API 精确回读当前身份/项目",
            "action": "api_assert",
            "request": first["request"],
            "assertions": first["assertions"],
        }
    )
    return journeys.define(
        {
            "name": "言迹测试 Web 登录与查询 smoke（非完整 W 风险）",
            "runner_type": "web",
            "target_ref": payload["target_ref"],
            "identity_ref": payload["identity_ref"],
            "identity_binding_ref": payload["binding_ref"],
            "chromium_version": payload["chromium_version"],
            "contract_confirmed": True,
            "synthetic_test_data": False,
            "actions": actions,
            "timeout_seconds": 120,
        }
    )
