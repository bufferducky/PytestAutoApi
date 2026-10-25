"""平台资产真源：版本化场景/套件、覆盖账本与只读迁移。"""

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from pyta_platform_backend.repositories.asset_repository import asset_hash
from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.schemas.assets import ScenarioDraft, SuiteDraft
from pyta_platform_backend.schemas.run import CreateRunRequest
from pyta_platform_backend.services.redaction import Redactor
from pyta_platform_backend.services.scenario_compiler import compile_scenario, dump, preflight
from pyta_platform_backend.workers.context_transport import ContextError
from testflow_engine import LegacyYamlCompatLoader, TestRunDefinition


class AssetService:
    def __init__(self, repository, run_service, context_service, demo_service):
        self.repository, self.runs = repository, run_service
        self.context, self.demo = context_service, demo_service
        self.resources = None

    def list(self, kind, offset=0, limit=100):
        return self.repository.list(kind, max(0, offset), min(200, max(1, limit)))

    def get(self, kind, identifier):
        try:
            return self.repository.get(kind, identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def validate_draft(self, kind, data):
        try:
            model = (ScenarioDraft if kind == "scenarios" else SuiteDraft)(**data)
            result = dump(model)
            if Redactor(result).clean(result) != result:
                raise ValueError("资产不能包含秘密值，请使用公开引用/模板")
            if len(json.dumps(result)) > 1024 * 1024:
                raise ValueError("资产超过1MiB限制")
            return result
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, Redactor(data).clean(str(exc))) from exc

    def create(self, kind, data, identifier=None):
        try:
            return self.repository.create(kind, self.validate_draft(kind, data), identifier)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def update(self, kind, identifier, revision, data, archive=False):
        try:
            return self.repository.update(
                kind, identifier, revision, self.validate_draft(kind, data), archive=archive
            )
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def version(self, kind, identifier, version):
        try:
            return self.repository.version(kind, identifier, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def preview(self, kind, identifier):
        data = self.get(kind, identifier)["draft"]
        if kind == "scenarios":
            check = preflight(data)
            if self.resources:
                for index, requirement in enumerate(data.get("fixtures", [])):
                    try:
                        definition = self.resources.fixture(
                            requirement["definition_id"], requirement["version"]
                        )
                        if not definition["data"]["contract_confirmed"]:
                            raise ValueError("fixture契约未确认")
                        if definition["data"]["strategy"] == "read_only":
                            name = "fixtures." + requirement["name"] + "."
                            for step in data["steps"]:
                                if step["operation_kind"] == "write" and name in json.dumps(
                                    step["request"]
                                ):
                                    raise ValueError("只读fixture不能用于写请求")
                    except (ValueError, HTTPException) as exc:
                        check["errors"].append({"path": f"fixtures.{index}", "message": str(exc)})
            check["valid"] = not check["errors"]
            return check
        errors = []
        if not data["scenarios"]:
            errors.append({"path": "scenarios", "message": "套件不能为空"})
        seen = set()
        for index, ref in enumerate(data["scenarios"]):
            key = (ref["scenario_id"], ref["version"])
            if key in seen:
                errors.append({"path": f"scenarios.{index}", "message": "重复场景版本"})
            seen.add(key)
            published = self.version("scenarios", *key)
            compiled = preflight(published["data"])
            errors.extend(
                {"path": f"scenarios.{index}." + e["path"], "message": e["message"]}
                for e in compiled["errors"]
            )
        return {"valid": not errors, "errors": errors, "warnings": []}

    def publish(self, kind, identifier, request):
        draft = self.get(kind, identifier)
        check = self.preview(kind, identifier)
        if not check["valid"]:
            raise HTTPException(400, check)
        if kind == "scenarios":
            data = draft["draft"]
            try:
                self.context.snapshot(
                    data["target_ref"], data["identity_ref"], data["identity_binding_ref"]
                )
            except ContextError as exc:
                raise HTTPException(400, str(exc)) from exc
        try:
            return self.repository.publish(
                kind,
                identifier,
                request.expected_revision,
                draft["draft"],
                request.change_note,
                request.author,
            )
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def plan(self, kind, identifier, version, request):
        published = self.version(kind, identifier, version)
        scenarios = (
            [published]
            if kind == "scenarios"
            else [
                self.version("scenarios", r["scenario_id"], r["version"])
                for r in published["data"]["scenarios"]
            ]
        )
        definition = TestRunDefinition(name=published["data"]["name"])
        snapshots, refs = {}, []
        for index, scenario in enumerate(scenarios):
            scope = "s" + str(index)
            data = scenario["data"]
            overrides = (
                request.parameters
                if kind == "scenarios"
                else request.parameters.get(scenario["id"], {})
            )
            try:
                compiled = compile_scenario(scenario, scope_id=scope, overrides=overrides)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if request.transport_mode == "live" and any(
                not s["contract_confirmed"] for s in data["steps"] if s["enabled"]
            ):
                raise HTTPException(400, "live_contract_missing: 所有可执行步骤需确认请求契约")
            snapshot = self.context.snapshot(
                data["target_ref"],
                data["identity_ref"],
                data["identity_binding_ref"],
                request.environment_id,
            )
            key = scope
            snapshots[key] = snapshot
            for case in compiled.cases + compiled.cleanup_cases:
                case.metadata["context_binding_id"] = key
            compiled.metadata["scopes"][scope]["host"] = snapshot["target"]["base_url"]
            compiled.metadata["scopes"][scope]["identity"] = {
                "alias": (snapshot.get("identity") or {}).get("name"),
                "tenant_id": (snapshot.get("binding") or {}).get("tenant_id"),
                "project_id": (snapshot.get("binding") or {}).get("project_id"),
            }
            fixture_plan = []
            for requirement in data.get("fixtures", []):
                if self.resources is None:
                    raise HTTPException(400, "资源provider不可用")
                fixture_plan.append(
                    {
                        **requirement,
                        "definition": self.resources.fixture(
                            requirement["definition_id"], requirement["version"]
                        ),
                    }
                )
            definition.metadata.setdefault("fixture_plan", {})[scope] = fixture_plan
            definition.cases.extend(compiled.cases)
            # 套件场景清理按准备的反序；每场景保留自己的上下文。
            definition.cleanup_cases = compiled.cleanup_cases + definition.cleanup_cases
            definition.metadata.setdefault("scopes", {}).update(compiled.metadata["scopes"])
            refs.append(
                {"id": scenario["id"], "version": scenario["version"], "hash": scenario["hash"]}
            )
        # ContextAuthPlugin 的 bootstrap 默认上下文仅作兼容，不允许调用方覆盖。
        snapshots["default"] = snapshots["s0"]
        return {
            "build": request.build,
            "execution_mode": "standard_run",
            "transport_mode": request.transport_mode,
            "run_definition": dump(definition),
            "context_snapshots": snapshots,
            "asset_ref": {
                "kind": kind,
                "id": identifier,
                "version": version,
                "hash": published["hash"],
            },
            "scenario_refs": refs,
            "scenario_version_ref": f"{kind}/{identifier}/{version}",
            "timeout_seconds": published["data"].get("timeout_seconds", 300),
            "resource_actions": {
                scope: self.resources.dry_run(requirements) if self.resources else {}
                for scope, requirements in definition.metadata.get("fixture_plan", {}).items()
            },
            "side_effects": [
                {"scenario_id": s["id"], "step_id": step["step_id"], "kind": step["operation_kind"]}
                for s in scenarios
                for step in s["data"]["steps"]
                if step["enabled"]
            ],
        }

    def run(self, kind, identifier, version, request):
        plan = self.plan(kind, identifier, version, request)
        # 内部可信编译入口，快照已由 ContextService 固定；不能从公共 payload 提供。
        return self.runs._create_prepared(
            CreateRunRequest(
                suite_id=identifier,
                environment_id=request.environment_id,
                trigger_source="platform-asset",
                requested_by=request.requested_by,
                payload=plan,
            ),
            None,
        )

    def export(self, kind, identifier, version):
        return self.version(kind, identifier, version)

    def import_standard(self, data):
        if data.get("schema_version") != 1 or asset_hash(data.get("data")) != data.get("hash"):
            raise HTTPException(400, "schema_version/hash 无效")
        return self.create("scenarios", data["data"])

    def import_demo(self, suite_id, target_ref):
        raise HTTPException(410, "demo_import_disabled: 演示资产导入已移除")

    def import_legacy(self, relative_path, target_ref):
        root = Path(__file__).resolve().parents[5]
        path = (root / relative_path).resolve()
        if (
            not path.is_relative_to(root / "data")
            or not path.is_file()
            or path.stat().st_size > 1024 * 1024
        ):
            raise HTTPException(400, "仅可导入 data 内<=1MiB的 YAML")
        loader = LegacyYamlCompatLoader()
        document = loader.load_from_path(str(path))
        definition = loader.to_run_definition(document)
        blockers = []
        for case in definition.cases:
            raw = case.source.raw
            known = {
                "host",
                "url",
                "method",
                "detail",
                "headers",
                "requestType",
                "is_run",
                "data",
                "dependence_case",
                "dependence_case_data",
                "current_request_set_cache",
                "assert",
                "sql",
                "sleep",
                "teardown",
                "allureEpic",
                "allureFeature",
                "allureStory",
            }
            for unknown in set(raw) - known:
                blockers.append(case.case_id + ": 未映射字段 " + unknown)
            for key in ["teardown", "sql", "sleep", "dependence_case", "dependence_case_data"]:
                if raw.get(key):
                    blockers.append(case.case_id + ": 未迁移能力 " + key)
        return self._import_definition(
            definition,
            target_ref,
            {
                "kind": "legacy_yaml",
                "path": relative_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
            blockers,
        )

    def _import_definition(self, definition, target_ref, source, blockers, identifier=None):
        raw = dump(definition)
        redacted = Redactor(raw).clean(raw)
        removed = redacted != raw
        if removed:
            blockers.append("已移除秘密值，需重新配置公开引用")
        steps = []
        for item in redacted["cases"]:
            steps.append(
                {
                    "step_id": item["case_id"],
                    "name": item["title"],
                    "request": item["request"],
                    "assertions": item["assertions"],
                    "extractors": item["extractors"],
                    "enabled": item["enabled"],
                    "metadata": {"migration_source": item["source"]},
                    "contract_confirmed": False,
                }
            )
        draft = {
            "name": definition.name,
            "target_ref": target_ref,
            "steps": steps,
            "source": source,
            "migration_warnings": ["导入不发送请求；需核对请求/断言/依赖"],
            "migration_blockers": blockers,
        }
        # 被移除的占位允许保存在迁移草稿；发布仍由 blockers 拒绝。
        created = self.repository.create("scenarios", dump(ScenarioDraft(**draft)), identifier)
        return {
            "asset": created,
            "report": {
                "source": source,
                "secret_values_removed": removed,
                "blockers": blockers,
                "mapping": {
                    "request": "steps.request",
                    "assert": "steps.assertions",
                    "extractors": "steps.extractors",
                },
                "network_executed": False,
            },
        }

    def import_research(self):
        root = Path(__file__).resolve().parents[5]
        sources = [
            (
                "center",
                "docs/reverse-engineering/yanji/web-2026-10-25/center/static-api.json",
                "request_configurations",
            ),
            (
                "saas",
                "docs/reverse-engineering/yanji/web-2026-10-25/saas/static-api.json",
                "request_configurations",
            ),
            ("app", "docs/reverse-engineering/yanji/1.0.22-109/js-static-facts.json", "endpoints"),
        ]
        counts = {}
        for system, relative, field in sources:
            path = root / relative
            data = json.loads(path.read_text())
            imported = 0
            for entry in data[field]:
                expression = entry.get("url_expression", entry.get("path"))
                location = {
                    "line": entry.get("line"),
                    "column_utf16": entry.get("column_utf16"),
                    "start": entry.get("start"),
                    "end": entry.get("end"),
                }
                fingerprint = asset_hash(
                    {
                        "system": system,
                        "source": relative,
                        "expression": expression,
                        "method": entry["method"],
                        "location": location,
                    }
                )
                saved = self.repository.save_coverage(
                    {
                        "id": "static-" + fingerprint[:24],
                        "system": system,
                        "module": str(expression).split("/")[3]
                        if len(str(expression).split("/")) > 3
                        else "待分类",
                        "risk": "静态请求待确认：" + str(expression),
                        "method": entry["method"],
                        "expression": expression,
                        "evidence_time": "2026-10-24" if system == "app" else "2026-10-25",
                        "evidence_level": "static_observation",
                        "source": relative,
                        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "location": location,
                        "request_fields": entry.get("data_keys"),
                        "contract_status": "unconfirmed",
                        "scenario_refs": [],
                        "contract_note": None,
                    }
                )
                imported += bool(saved)
            counts[system] = {"observations": len(data[field]), "new": imported}
        return {
            "sources": counts,
            "network_executed": False,
            "note": "数量是静态观察，不是独立在线接口或通过用例",
        }

    def update_coverage(self, identifier, revision, changes):
        current = next((row for row in self.repository.coverage() if row["id"] == identifier), None)
        if current is None:
            raise HTTPException(404, "coverage item 不存在")
        if set(changes) - {
            "risk",
            "module",
            "contract_status",
            "contract_note",
            "scenario_refs",
            "regression_id",
            "required_for_release",
        }:
            raise HTTPException(400, "不能覆盖证据来源/静态事实")
        data = {**current, **changes}
        if data.get("regression_id") is not None and data["regression_id"] not in {
            "S" + str(i).zfill(2) for i in range(1, 17)
        }:
            raise HTTPException(400, "regression_id只能关联S01—S16，未知风险不能猜测")
        if "required_for_release" in data and not isinstance(data["required_for_release"], bool):
            raise HTTPException(400, "required_for_release必须是bool")
        if data.get("regression_id"):
            data["required_for_release"] = True
        if data["contract_status"] not in {"unconfirmed", "confirmed", "blocked"}:
            raise HTTPException(400, "非法契约状态")
        if data["contract_status"] == "confirmed" and not data.get("contract_note"):
            raise HTTPException(400, "确认契约必须记录依据/确认人/日期")
        for ref in data["scenario_refs"]:
            self.version("scenarios", ref["scenario_id"], ref["version"])
        if Redactor(data).clean(data) != data:
            raise HTTPException(400, "覆盖备注不能含秘密")
        try:
            return self.repository.save_coverage(data, expected_revision=revision)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def coverage_summary(self, freshness_days=7, *, environment_id=None, build=None, run_ids=None):
        if freshness_days < 1 or freshness_days > 365:
            raise HTTPException(400, "freshness_days 必须在1—365")
        records = self.runs.repository.list_runs(limit=100000, offset=0).items
        now = datetime.now(timezone.utc)
        items = []
        for item in self.repository.coverage():
            item = deepcopy(item)
            evidence = []
            outdated = False
            for ref in item["scenario_refs"]:
                latest_version = self.repository.versions("scenarios", ref["scenario_id"])
                if latest_version and latest_version[0]["version"] != ref["version"]:
                    outdated = True
                    continue
                expected = self.version("scenarios", ref["scenario_id"], ref["version"])
                for run in records:
                    if (
                        run.transport_mode != "live"
                        or run.status.value != "succeeded"
                        or not run.eligible_for_release
                    ):
                        continue
                    if run_ids is not None and run.run_id not in run_ids:
                        continue
                    if environment_id is not None and run.environment_id != environment_id:
                        continue
                    detail = self.runs.get_run_detail(run.run_id)
                    if build is not None and detail.payload.get("build") != build:
                        continue
                    matches = [
                        r
                        for r in detail.payload.get("scenario_refs", [])
                        if r["id"] == ref["scenario_id"]
                        and r["version"] == ref["version"]
                        and r.get("hash") == expected["hash"]
                    ]
                    if matches:
                        evidence.append(
                            {
                                "run_id": run.run_id,
                                "finished_at": run.finished_at.isoformat(),
                                "scenario_ref": matches[0],
                            }
                        )
            evidence.sort(key=lambda e: e["finished_at"], reverse=True)
            latest = evidence[0] if evidence else None
            item["latest_live_evidence"] = latest
            item["coverage_status"] = (
                "unconfirmed"
                if item["contract_status"] == "unconfirmed"
                else (
                    "blocked"
                    if item["contract_status"] == "blocked"
                    else "version_stale"
                    if outdated
                    else "uncovered"
                    if not latest
                    else "stale"
                    if datetime.fromisoformat(latest["finished_at"])
                    < now - timedelta(days=freshness_days)
                    else "verified"
                )
            )
            items.append(item)
        confirmed = [item for item in items if item["contract_status"] == "confirmed"]
        return {
            "calculation_version": 1,
            "freshness_days": freshness_days,
            "total_observations": len(items),
            "confirmed_risks": len(confirmed),
            "verified_risks": sum(i["coverage_status"] == "verified" for i in confirmed),
            "unverified": [i["id"] for i in items if i["coverage_status"] != "verified"],
            "required_unverified": [
                i["id"]
                for i in items
                if i.get("required_for_release", False) and i["coverage_status"] != "verified"
            ],
            "items": items,
        }
