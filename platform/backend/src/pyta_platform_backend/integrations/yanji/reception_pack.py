"""接诊筛选回归草稿，发布和执行沿用正式资产工作流。"""

from fastapi import HTTPException

from pyta_platform_backend.integrations.yanji.query_pack import query_drafts
from pyta_platform_backend.integrations.yanji.reception_oracle import CONTRACT, EMPTY_DIFF
from pyta_platform_backend.repositories.asset_repository import asset_hash
from pyta_platform_backend.services.business_datasources import resolve_source


def reception_drafts(target_ref, identity_ref, binding_ref, expected_user_id, datasource_ref):
    definitions = [
        ("default", "页面默认录音筛选"),
        ("status", "状态单条件"),
        ("customer_type", "客户类型"),
        ("date", "接待日期"),
        ("reception_user", "接待人"),
        ("combined", "日期人员状态类型组合"),
        ("keyword_existing", "关键词精确接诊ID"),
        ("keyword_empty", "不存在关键词"),
        ("no_record", "无录音分支"),
        ("short_record", "短录音分支"),
        ("sweep", "全部分页集合"),
    ]
    for preset, label in definitions:
        identity = next(query_drafts(target_ref, identity_ref, binding_ref, expected_user_id))[1]
        identity_step = identity["steps"][0]
        identity_step["metadata"] = {"yanji_identity": True}
        yield (
            preset,
            {
                "name": "言迹接诊 · " + label,
                "module": "言迹/接诊筛选回归",
                "target_ref": target_ref,
                "identity_ref": identity_ref,
                "identity_binding_ref": binding_ref,
                "priority": "P0",
                "tags": ["yanji", "reception", "readonly-db", "query-only"],
                "source": {
                    "kind": "yanji-reception-pack",
                    "version": 1,
                    "contract_ref": CONTRACT,
                    "coverage_gaps": [
                        "非空无录音/短录音/其他状态/恰好120秒样本尚未确认",
                        "首版仅支持项目超管且角色purpose为空",
                    ],
                },
                "steps": [
                    identity_step,
                    {
                        "step_id": "receptions",
                        "name": label,
                        "depends_on": ["identity"],
                        "contract_confirmed": True,
                        "operation_kind": "query",
                        "safe_to_replay": True,
                        "request": {
                            "method": "GET",
                            "url": "{{host}}/api/v1/reception_form/page",
                            "query": {"pageNum": 1, "pageSize": 12, "recordDurationStatus": 2},
                        },
                        "database_check": {
                            "datasource_ref": datasource_ref,
                            "contract_ref": CONTRACT,
                            "expected_user_id": expected_user_id,
                            "filter_preset": preset,
                            "sweep": preset == "sweep",
                        },
                        "assertions": [
                            {"name": "http-status", "source": "status_code", "expected": 200},
                            {"name": "business-code", "selector": "code", "expected": 200},
                            {
                                "name": "数据库接诊集合与分页",
                                "source": "context",
                                "selector": "runtime.database_diff",
                                "expected": EMPTY_DIFF,
                            },
                        ],
                    },
                ],
            },
        )


def import_reception_pack(assets, payload):
    required = ["target_ref", "identity_ref", "binding_ref", "expected_user_id", "datasource_ref"]
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
        raise HTTPException(400, "请选择目标/身份/绑定/数据源并填写预期用户ID")
    snapshot = assets.context.snapshot(*(payload[key] for key in required[:3]))
    try:
        resolve_source(payload["datasource_ref"], snapshot)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    target = snapshot["target"]
    if target["auth"]["mode"] != "password" or not target["requires_context"]:
        raise HTTPException(400, "言迹接诊回归需要密码登录和已确认项目绑定")
    created = []
    for key, draft in reception_drafts(*(payload[key] for key in required)):
        identifier = (
            "yanji-reception-"
            + asset_hash([payload["binding_ref"], payload["datasource_ref"], key])[:24]
        )
        try:
            existing = assets.repository.get("scenarios", identifier)
        except KeyError:
            existing = assets.create("scenarios", draft, identifier=identifier)
        created.append(existing)
    return {
        "assets": created,
        "network_executed": False,
        "scope": "reception_filter_regression",
        "note": "只创建草稿；预检/发布后运行。动态样本由只读DB选择；覆盖缺口保留。",
    }
