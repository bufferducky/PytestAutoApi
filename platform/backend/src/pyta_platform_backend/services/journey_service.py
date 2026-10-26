"""版本化UI旅程及能力闸门；缺公司资源不编造W/A业务步骤。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException

from pyta_platform_backend.runners.ui import capability, device_preflight
from pyta_platform_backend.schemas.journeys import DeviceProfile, JourneyDefinition
from pyta_platform_backend.schemas.run import CreateRunRequest
from pyta_platform_backend.services.redaction import Redactor

RISK_IDS = ["W01", "W02", "W03", "W04", "A01", "A02", "A03", "A04"]


class JourneyService:
    def __init__(self, repository, runs, context, resources, diagnostics):
        self.repository, self.runs, self.context, self.resources, self.diagnostics = (
            repository,
            runs,
            context,
            resources,
            diagnostics,
        )

    def device(self, data):
        data = dict(data)
        identifier = data.pop("id", None)
        try:
            model = DeviceProfile(**data)
            public = model.model_dump() if hasattr(model, "model_dump") else model.dict()
            import re

            if not re.fullmatch(r"env:PYTA_SECRET_[A-Z0-9_]+", public["device_secret_ref"]):
                raise ValueError("设备序列号只保存env:PYTA_SECRET_*引用")
            if not re.fullmatch(r"[0-9a-f]{64}", public["app_build_sha256"]):
                raise ValueError("必须指定真实App构建SHA256")
            server = urlsplit(public["appium_url"])
            if (
                server.scheme != "http"
                or server.hostname not in {"127.0.0.1", "localhost"}
                or server.query
                or server.username
            ):
                raise ValueError("首期Appium仅本机服务")
            return self.repository.define(
                "device-profile", {**public, **({"id": identifier} if identifier else {})}
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def define(self, data):
        data = dict(data)
        identifier = data.pop("id", None)
        try:
            model = JourneyDefinition(**data)
            public = model.model_dump() if hasattr(model, "model_dump") else model.dict()
            if model.risk_id and (
                model.risk_id not in RISK_IDS
                or model.risk_id.startswith("W") != (model.runner_type == "web")
            ):
                raise ValueError("risk_id须与Web的W01—W04或Android的A01—A04匹配")
            if model.runner_version != "ui-runner@1":
                raise ValueError("未知runner版本")
            if not model.actions:
                raise ValueError("旅程不能为空")
            ids = [a.step_id for a in model.actions]
            if len(ids) != len(set(ids)):
                raise ValueError("step_id必须唯一")
            if not any(
                a.action.startswith("assert_") or a.action == "api_assert" for a in model.actions
            ):
                raise ValueError("旅程必须有可观察断言")
            for action in model.actions:
                if action.action == "api_assert":
                    if (
                        action.request is None
                        or not action.assertions
                        or action.operation_kind != "query"
                    ):
                        raise ValueError(
                            "api_assert必须是已确认查询并有请求/业务断言，不能用于写入"
                        )
                elif action.action not in {"navigate", "background", "permission"}:
                    if action.selector is None:
                        raise ValueError("动作缺语义selector")
                    allowed = (
                        {"role", "label", "testid", "placeholder"}
                        if model.runner_type == "web"
                        else {"accessibility_id", "resource_id"}
                    )
                    if action.selector.strategy not in allowed:
                        raise ValueError("不允许坐标/CSS/XPath及不适用定位")
                if action.action == "permission" and action.restore_permission_granted is None:
                    raise ValueError("权限测试必须声明恢复状态")
            if Redactor(public).clean(public) != public:
                raise ValueError("旅程不能含秘密/客户明文，使用value_ref")
            snapshot = self.context.snapshot(
                model.target_ref, model.identity_ref, model.identity_binding_ref
            )
            if model.capture_trace or model.capture_video:
                if (
                    model.runner_type != "web"
                    or not model.synthetic_test_data
                    or snapshot.get("identity")
                ):
                    raise ValueError("原生trace/录屏仅允许明确合成且无凭证身份的Web旅程")
            self.fixture_plan(public)
            return self.repository.define(
                "journeys", {**public, **({"id": identifier} if identifier else {})}
            )
        except ValueError as exc:
            raise HTTPException(400, Redactor(data).clean(str(exc))) from exc

    def fixture_plan(self, data):
        plan = []
        names = set()
        for requirement in data.get("fixtures", []):
            if requirement["name"] in names or any(
                dep not in names for dep in requirement["depends_on"]
            ):
                raise ValueError("旅程fixture名称须唯一，依赖只能向前")
            definition = self.resources.fixture(
                requirement["definition_id"], requirement["version"]
            )
            if not definition["data"]["contract_confirmed"]:
                raise ValueError("旅程fixture契约尚未确认")
            if definition["data"]["strategy"] == "read_only":
                for action in data["actions"]:
                    if action["operation_kind"] == "write":
                        raise ValueError("含只读fixture的旅程不能声明写入动作")
            names.add(requirement["name"])
            plan.append({**requirement, "definition": definition})
        return plan

    def get(self, kind, identifier, version):
        try:
            return self.repository.version(kind, identifier, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def preflight(self, identifier, version, probe=False):
        published = self.get("journeys", identifier, version)
        journey = published["data"]
        profile = None
        if journey["runner_type"] == "android" and journey.get("device_profile_id"):
            profile = self.get(
                "device-profile", journey["device_profile_id"], journey["device_profile_version"]
            )["data"]
        result = capability(journey, profile)
        if probe and result["available"] and profile:
            result["device_probe"] = device_preflight(profile)
        return result

    def run(self, identifier, version, *, build="unspecified"):
        published = self.get("journeys", identifier, version)
        data = published["data"]
        snapshot = self.context.snapshot(
            data["target_ref"], data["identity_ref"], data["identity_binding_ref"]
        )
        if not isinstance(build, str) or not build.strip():
            raise HTTPException(400, "build必须为非空标识")
        payload = {
            "business_scope": "yanji_web"
            if data["target_ref"]
            and snapshot["target"]["base_url"] == "https://web-test.yanjiai.com"
            else "unclassified",
            "build": build,
            "execution_mode": "ui_journey",
            "transport_mode": "live",
            "journey_definition": published,
            "journey_fixture_plan": self.fixture_plan(data),
            "context_snapshots": {"default": snapshot},
            "timeout_seconds": data["timeout_seconds"],
        }
        if data.get("device_profile_id"):
            payload["device_profile"] = self.get(
                "device-profile", data["device_profile_id"], data["device_profile_version"]
            )
        return self.runs._create_prepared(
            CreateRunRequest(
                suite_id=identifier,
                environment_id=snapshot["target"]["environment_id"],
                trigger_source="ui-journey",
                payload=payload,
            ),
            self.context.management.get_environment_by_id(
                snapshot["target"]["environment_id"]
            ).name,
        )

    def quarantine(self, identifier, version, reason, expires_at):
        self.get("journeys", identifier, version)
        try:
            expiry = datetime.fromisoformat(expires_at)
            if (
                expiry.tzinfo is None
                or expiry <= datetime.now(timezone.utc)
                or len(reason.strip()) < 5
            ):
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(400, "隔离须说明原因与未来到期时间") from exc
        return self.repository.define(
            "quarantine",
            {
                "journey_id": identifier,
                "version": version,
                "reason": Redactor().clean(reason),
                "expires_at": expires_at,
            },
        )

    def resolve_quarantine(self, quarantine_id, reason):
        record = next(
            (
                item
                for item in self.repository.definitions("quarantine")
                if item["id"] == quarantine_id
            ),
            None,
        )
        if record is None:
            raise HTTPException(404, "隔离记录不存在")
        if not isinstance(reason, str) or len(reason.strip()) < 5:
            raise HTTPException(400, "解除隔离须给出修复/验证依据")
        return self.repository.define(
            "quarantine-resolution",
            {
                "quarantine_id": quarantine_id,
                "quarantine_hash": record["hash"],
                "reason": Redactor().clean(reason),
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def readiness(self, *, freshness_days=7, environment_id=None, build=None, run_ids=None):
        if not isinstance(freshness_days, int) or not 1 <= freshness_days <= 365:
            raise HTTPException(400, "freshness_days须1—365")
        defined = self.repository.definitions("journeys")
        latest = {}
        for published in defined:
            if (
                published["id"] not in latest
                or published["version"] > latest[published["id"]]["version"]
            ):
                latest[published["id"]] = published
        quarantines = self.repository.definitions("quarantine")
        resolved = {
            (r["data"]["quarantine_id"], r["data"]["quarantine_hash"])
            for r in self.repository.definitions("quarantine-resolution")
        }
        records = []
        now = datetime.now(timezone.utc)
        all_runs = self.runs.repository.list_runs(limit=100000, offset=0).items
        for risk_id in RISK_IDS:
            candidates = [p for p in latest.values() if p["data"].get("risk_id") == risk_id]
            evidence = []
            blocked = []
            for published in candidates:
                if not published["data"]["contract_confirmed"]:
                    blocked.append(
                        {"journey_id": published["id"], "reason": "journey_contract_missing"}
                    )
                    continue
                unresolved = [
                    q
                    for q in quarantines
                    if q["data"]["journey_id"] == published["id"]
                    and q["data"]["version"] == published["version"]
                    and (q["id"], q["hash"]) not in resolved
                ]
                if unresolved:
                    blocked.append(
                        {
                            "journey_id": published["id"],
                            "reason": "quarantine_requires_resolution",
                            "quarantine_ids": [q["id"] for q in unresolved],
                        }
                    )
                    continue
                for row in all_runs:
                    if (
                        row.execution_mode != "ui_journey"
                        or row.transport_mode != "live"
                        or row.status.value != "succeeded"
                        or row.cleanup_status != "succeeded"
                    ):
                        continue
                    if not row.finished_at or row.finished_at < now - timedelta(
                        days=freshness_days
                    ):
                        continue
                    if (
                        not row.counts.get("assertions")
                        or row.counts.get("blocked")
                        or row.counts.get("skipped")
                    ):
                        continue
                    if environment_id is not None and row.environment_id != environment_id:
                        continue
                    if run_ids is not None and row.run_id not in run_ids:
                        continue
                    detail = self.runs.get_run_detail(row.run_id)
                    if detail.evidence_pruned_at or detail.payload.get("rerun_selection", {}).get(
                        "partial"
                    ):
                        continue
                    if build is not None and detail.payload.get("build") != build:
                        continue
                    actual = detail.payload.get("journey_definition", {})
                    if (actual.get("id"), actual.get("version"), actual.get("hash")) != (
                        published["id"],
                        published["version"],
                        published["hash"],
                    ):
                        continue
                    evidence.append(
                        {
                            "run_id": row.run_id,
                            "journey_id": published["id"],
                            "version": published["version"],
                            "hash": published["hash"],
                            "finished_at": row.finished_at.isoformat(),
                            "environment_id": row.environment_id,
                            "build": detail.payload.get("build"),
                        }
                    )
            evidence.sort(key=lambda item: item["finished_at"], reverse=True)
            records.append(
                {
                    "risk_id": risk_id,
                    "defined": bool(candidates),
                    "validation": "verified" if evidence else "unverified",
                    "reason": None if evidence else "缺少同范围新鲜live成功证据，或仍在隔离中",
                    "latest_evidence": evidence[0] if evidence else None,
                    "blocking_conditions": blocked,
                }
            )
        return {
            "risks": records,
            "quarantines": quarantines,
            "quarantine_resolutions": self.repository.definitions("quarantine-resolution"),
            "freshness_days": freshness_days,
            "scope": {"environment_id": environment_id, "build": build},
            "note": "风险关联由操作者按契约明确声明；不从未关联本地样例推断公司业务通过",
        }
