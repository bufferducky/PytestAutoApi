"""诊断是运行事实的投影；附件、定位计时与证据保留独立记账。"""

import base64
import json
import math
from datetime import datetime, timezone

from fastapi import HTTPException

from pyta_platform_backend.services.redaction import Redactor

CATEGORIES = {
    "config": "检查字段/变量/版本和配置预检",
    "authentication": "核对认证契约与密钥引用，不输出凭证明文",
    "context": "核对身份、target、租户/项目绑定及对象归属",
    "data": "查看fixture所有权、资源池和清理待办",
    "network": "检查连接、请求超时及首次网络错误",
    "assertion": "核对精确对象、预期/实际及规则版本",
    "executor": "查看执行器/插件异常与schema版本",
    "external_service": "核对依赖服务响应和可用性，勿直接归为业务错误",
    "device": "检查设备连接、驱动、构建和能力预检",
    "unknown": "证据不足，保留原线索并补查",
}


class DiagnosticService:
    def __init__(self, run_service, resource_service, artifact_repository):
        self.runs, self.resources, self.artifacts = (
            run_service,
            resource_service,
            artifact_repository,
        )

    @staticmethod
    def category(error_type="", message="", step=None):
        normalized = (error_type or "").lower()
        message = (message or "").lower()
        if normalized in {"configuration", "config", "assertion_configuration"}:
            return "config"
        if normalized in {"authentication", "context", "data", "device", "external_service"}:
            return normalized
        if any(
            key in normalized for key in ["timeout", "connect", "readerror", "network", "transport"]
        ):
            return "network"
        if "missingtemplate" in normalized or any(
            word in message for word in ["未定义", "配置", "引用不存在", "字段缺失"]
        ):
            return "config"
        if "login" in message or "auth_" in message or "secret_ref" in message:
            return "authentication"
        if normalized:
            return "executor"
        if step and step.get("status") == "failed":
            response = step.get("response") or {}
            if response.get("status_code", 0) >= 500:
                return "external_service"
            if response.get("status_code") in {401, 403}:
                return "authentication"
            return "assertion"
        return "unknown"

    def overview(self, run_id):
        detail = self.runs.get_run_detail(run_id)
        timeline = []
        for case in detail.results:
            failure = next(
                (
                    a
                    for step in case.get("steps", [])
                    for a in step.get("assertions", [])
                    if a["status"] != "passed"
                ),
                None,
            )
            step = next(
                (s for s in case.get("steps", []) if s["status"] not in {"passed", "skipped"}), None
            )
            message = (
                case.get("error") or (step or {}).get("error") or (failure or {}).get("message")
            )
            category = self.category((step or {}).get("error_type"), message, step)
            if failure and failure["status"] == "failed" and category == "unknown":
                category = "assertion"
            if failure and failure["status"] == "error" and category == "unknown":
                category = "config"
            timeline.append(
                {
                    "case_id": case["case_id"],
                    "source_ref": (failure or {}).get("source_ref") or case["case_id"] + "/request",
                    "title": case["title"],
                    "status": case["status"],
                    "phase": case.get("metadata", {}).get("phase", case.get("phase", "main")),
                    "depends_on": case.get("metadata", {}).get("depends_on", []),
                    "category": category,
                    "message": message,
                    "next_action": CATEGORIES[category],
                    "scenario_ref": case.get("metadata", {}).get("scenario_ref"),
                    "started_at": case.get("started_at"),
                    "finished_at": case.get("finished_at"),
                    "steps": case.get("steps", []),
                }
            )
        first = next(
            (
                row
                for row in timeline
                if row["phase"] != "cleanup"
                and row["status"] not in {"passed", "skipped", "blocked"}
            ),
            None,
        )
        first = first or next(
            (row for row in timeline if row["status"] not in {"passed", "skipped"}), None
        )
        if first is None and detail.status.value not in {
            "succeeded",
            "queued",
            "running",
            "skipped",
        }:
            category = self.category(message=detail.retention_summary or detail.status_message)
            first = {
                "case_id": None,
                "category": category,
                "message": detail.retention_summary or detail.status_message,
                "next_action": CATEGORIES[category],
            }
        if first is None and detail.cleanup_status in {"cleanup_failed", "needs_reconciliation"}:
            first = {
                "case_id": None,
                "category": "data",
                "message": "资源清理/对账未完成",
                "next_action": CATEGORIES["data"],
            }
        resources = self.resources.repository.resources(run_id)
        attachments = [self.artifact(meta["artifact_id"]) for meta in self.artifacts.list(run_id)]
        public = (
            detail.model_dump(mode="json")
            if hasattr(detail, "model_dump")
            else json.loads(detail.json())
        )
        return Redactor(public).clean(
            {
                "run_id": run_id,
                "attempt_id": detail.attempt_id,
                "status": detail.status.value,
                "transport_mode": detail.transport_mode,
                "validation_scope": detail.validation_scope,
                "business_scope": detail.business_scope,
                "execution_mode": detail.execution_mode,
                "environment_id": detail.environment_id,
                "environment_name": detail.environment_name,
                "asset_ref": detail.payload.get("asset_ref"),
                "scenario_refs": detail.payload.get("scenario_refs", []),
                "trigger_source": detail.trigger_source,
                "counts": detail.counts,
                "cleanup_status": detail.cleanup_status,
                "eligible_for_release": detail.eligible_for_release,
                "original_run_id": detail.original_run_id,
                "created_at": detail.created_at,
                "started_at": detail.started_at,
                "finished_at": detail.finished_at,
                "first_failure": first,
                "timeline": timeline,
                "context_snapshots": detail.payload.get("context_snapshots", {}),
                "resources": [
                    {
                        "alias": r["alias"],
                        "state": r["state"],
                        "strategy": r["strategy"],
                        "context": r["context"],
                    }
                    for r in resources
                ],
                "artifacts": attachments,
                "evidence_completeness": "recorded"
                if detail.results
                else "expired"
                if detail.evidence_pruned_at
                else "historical_not_recorded",
            }
        )

    def add_artifact(self, run_id, payload):
        detail = self.runs.get_run_detail(run_id)
        step_id = payload.get("step_id")
        if step_id and not any(case["case_id"] == step_id for case in detail.results):
            raise HTTPException(404, "附件步骤不属于该run")
        content_type = payload.get("content_type", "application/json")
        text_types = {"application/json", "text/plain", "application/trace+json"}
        binary_types = {
            "image/png",
            "image/jpeg",
            "audio/wav",
            "audio/mpeg",
            "video/webm",
            "video/mp4",
            "application/vnd.playwright.trace+zip",
        }
        if content_type not in text_types | binary_types:
            raise HTTPException(400, "不支持的附件类型")
        if content_type in text_types:
            clean = Redactor().clean(payload.get("content"))
            content = (
                json.dumps(clean, ensure_ascii=False).encode()
                if content_type != "text/plain"
                else str(clean).encode()
            )
            status = "verified"
        else:
            try:
                content = base64.b64decode(payload.get("base64", ""), validate=True)
            except Exception as exc:
                raise HTTPException(400, "无效base64附件") from exc
            # 未核验媒体不入可导出附件，避免原始秘密落盘后再靠UI隐藏。
            if not payload.get("synthetic_test_data") or not payload.get("redaction_verified"):
                raise HTTPException(400, "媒体必须为已核验合成/脱敏测试数据；未核验不保存或外发")
            status = "verified"
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "附件必须非空且<=10MiB")
        if (
            sum(
                a["byte_size"]
                for a in self.artifacts.list(run_id)
                if a["availability"] == "available"
            )
            + len(content)
            > 50 * 1024 * 1024
        ):
            raise HTTPException(400, "单run附件总量超过50MiB")
        policy = self.artifacts.policy()
        days = (
            policy["failure_attachment_days"]
            if detail.status.value not in {"succeeded", "queued", "running"}
            else policy["attachment_days"]
        )
        return self.artifacts.add(run_id, step_id, content, content_type, status, days)

    def artifact(self, identifier, run_id=None, download=False):
        try:
            meta = self.artifacts.get_artifact(identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        if run_id and meta["run_id"] != run_id:
            raise HTTPException(404, "附件不属于此run")
        detail = self.runs.get_run_detail(meta["run_id"])
        active = detail.status.value in {"queued", "running"}
        historical = detail.validation_scope == "historical_demo" or bool(meta.get("migration"))
        expired = (
            not historical
            and not meta["pinned"]
            and not active
            and datetime.fromisoformat(meta["expires_at"]) <= datetime.now(timezone.utc)
        )
        if not download:
            return (
                {**meta, "availability": "expired_pending_cleanup"}
                if expired and meta["availability"] == "available"
                else meta
            )
        if expired:
            raise HTTPException(410, "附件保留期已过，仅保留元数据")
        if meta["availability"] == "expired":
            raise HTTPException(410, "附件已过期，保留元数据")
        if meta["redaction_status"] != "verified":
            raise HTTPException(403, "附件脱敏尚未核验")
        try:
            return meta, self.artifacts.content(meta)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    def compare(self, run_id, other_id):
        before, after = self.overview(run_id), self.overview(other_id)
        fields = [
            "environment_id",
            "transport_mode",
            "asset_ref",
            "scenario_refs",
            "context_snapshots",
        ]
        return {
            "before": before,
            "after": after,
            "changes": {
                field: {"before": before[field], "after": after[field]}
                for field in fields
                if before[field] != after[field]
            },
            "lineage": {
                "original_run_id": after["original_run_id"],
                "first_failure_preserved": before["first_failure"],
            },
        }

    def retention_preview(self):
        now = datetime.now(timezone.utc)
        ready = []
        preserved = []
        for meta in self.artifacts.all_artifacts():
            detail = self.runs.get_run_detail(meta["run_id"])
            if meta["availability"] != "available":
                continue
            if (
                detail.validation_scope == "historical_demo"
                or meta.get("migration")
                or meta["pinned"]
                or detail.status.value in {"queued", "running"}
            ):
                preserved.append(meta["artifact_id"])
                continue
            if datetime.fromisoformat(meta["expires_at"]) <= now:
                ready.append(meta["artifact_id"])
        policy = self.artifacts.policy()
        metadata_ready = []
        for run in self.runs.repository.list_runs(limit=100000, offset=0).items:
            if run.validation_scope == "historical_demo":
                continue
            if (
                not run.finished_at
                or (now - run.finished_at).total_seconds() < policy["metadata_days"] * 86400
            ):
                continue
            attachments = self.artifacts.list(run.run_id)
            if any(a["pinned"] for a in attachments):
                continue
            if any(
                a["availability"] == "available" and a["artifact_id"] not in ready
                for a in attachments
            ):
                continue
            if not self.runs.get_run_detail(run.run_id).evidence_pruned_at:
                metadata_ready.append(run.run_id)
        return {
            "ready": ready,
            "preserved": preserved,
            "metadata_ready": metadata_ready,
            "policy": policy,
            "network_executed": False,
        }

    def retention_apply(self, identifiers, run_ids=None):
        if not isinstance(identifiers, list) or not all(
            isinstance(item, str) for item in identifiers
        ):
            raise HTTPException(400, "artifact_ids必须为字符串列表")
        identifiers = list(dict.fromkeys(identifiers))
        preview = self.retention_preview()
        allowed = set(preview["ready"])
        if not set(identifiers) <= allowed:
            raise HTTPException(409, "保留计划已变化，不能回收活跃/保留证据")
        run_ids = run_ids or []
        if not set(run_ids) <= set(preview["metadata_ready"]):
            raise HTTPException(409, "元数据保留计划已变化")
        results = []
        for identifier in identifiers:
            meta = self.artifacts.get_artifact(identifier)
            try:
                self.artifacts.expire(meta)
                results.append({"id": identifier, "availability": "expired"})
            except (ValueError, OSError):
                results.append({"id": identifier, "availability": "cleanup_failed"})
        for run_id in run_ids:
            remaining = [a for a in self.artifacts.list(run_id) if a["availability"] == "available"]
            if remaining:
                raise HTTPException(409, "须先完成关联附件回收，不能先删除诊断明细")
            self.runs.repository.prune_evidence(run_id)
            results.append({"run_id": run_id, "availability": "metadata_tombstone"})
        return results

    def pin(self, identifier, pinned):
        if not isinstance(pinned, bool):
            raise HTTPException(400, "pinned必须是bool")
        try:
            meta = self.artifacts.get_artifact(identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return self.artifacts.update({**meta, "pinned": pinned})

    def timing(self, run_id, payload):
        self.runs.get_run_detail(run_id)
        try:
            return self.artifacts.timing(
                run_id, payload["opened_at"], payload["summary_at"], payload["scope"]
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, "定位计时字段/时间无效") from exc

    def filtered_runs(
        self,
        *,
        limit=20,
        offset=0,
        environment_id=None,
        target_id=None,
        build=None,
        transport_mode=None,
        scenario_id=None,
        scenario_version=None,
        status=None,
        category=None,
        since=None,
        until=None,
    ):
        from pyta_platform_backend.schemas.run import ListRunsResponse

        try:
            lower = datetime.fromisoformat(since) if since else None
            upper = datetime.fromisoformat(until) if until else None
            if lower and lower.tzinfo is None or upper and upper.tzinfo is None:
                raise ValueError()
            if lower and upper and lower > upper:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(400, "筛选时间须使用带时区ISO文本") from exc
        if scenario_version is not None and not scenario_id:
            raise HTTPException(400, "版本筛选必须同时提供scenario_id")
        records = self.runs.repository.list_runs(limit=100000, offset=0).items
        selected = []
        for record in records:
            if environment_id and record.environment_id != environment_id:
                continue
            if transport_mode and record.transport_mode != transport_mode:
                continue
            if transport_mode == "live" and record.validation_scope == "historical_demo":
                continue
            if status and record.status.value != status:
                continue
            if lower and record.created_at < lower or upper and record.created_at > upper:
                continue
            if target_id or scenario_id or category or build:
                detail = self.runs.get_run_detail(record.run_id)
                if build and detail.payload.get("build", "unspecified") != build:
                    continue
                if target_id and not any(
                    s["target"]["id"] == target_id
                    for s in detail.payload.get("context_snapshots", {}).values()
                ):
                    continue
                if scenario_id and not any(
                    ref["id"] == scenario_id
                    and (scenario_version is None or ref["version"] == scenario_version)
                    for ref in detail.payload.get("scenario_refs", [])
                ):
                    continue
                if category:
                    diagnostic = self.overview(record.run_id)
                    if (
                        not diagnostic["first_failure"]
                        or diagnostic["first_failure"]["category"] != category
                    ):
                        continue
            selected.append(record)
        limit = max(1, min(200, limit))
        offset = max(0, offset)
        return ListRunsResponse(
            total=len(selected), limit=limit, offset=offset, items=selected[offset : offset + limit]
        )

    def trends(self, environment_id, transport_mode, scenario_id, scenario_version):
        if not all(
            [environment_id, transport_mode, scenario_id, scenario_version]
        ) or transport_mode not in {"live", "mock"}:
            raise HTTPException(400, "趋势必须固定环境、模式、场景及版本，不能混合统计")
        records = self.filtered_runs(
            limit=200,
            environment_id=environment_id,
            transport_mode=transport_mode,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
        )
        finished = []
        outcomes = {}
        originals = []
        groups = {}
        rerun_success = 0
        unverified = 0
        from pyta_platform_backend.repositories.asset_repository import asset_hash

        for record in records.items:
            if not record.finished_at:
                continue
            detail = self.runs.get_run_detail(record.run_id)
            if detail.payload.get("run_purpose") == "debug":
                continue
            cases = [
                case
                for case in detail.results
                if case.get("metadata", {}).get("scenario_ref", {}).get("id") == scenario_id
                and case.get("metadata", {}).get("scenario_ref", {}).get("version")
                == scenario_version
                and case.get("phase") != "cleanup"
            ]
            if not cases or any(case["status"] in {"blocked", "skipped"} for case in cases):
                unverified += 1
                continue
            outcome = "succeeded" if all(case["status"] == "passed" for case in cases) else "failed"
            outcomes[record.run_id] = outcome
            finished.append(record)
            keys = {case.get("metadata", {}).get("context_binding_id") for case in cases}
            snapshot = {
                key: value
                for key, value in detail.payload.get("context_snapshots", {}).items()
                if key in keys
            }
            fingerprint = asset_hash(snapshot)
            groups[fingerprint] = groups.get(fingerprint, 0) + 1
            if not detail.original_run_id:
                originals.append(record)
            elif outcome == "succeeded":
                rerun_success += 1
        failures = sum(outcomes[r.run_id] != "succeeded" for r in originals)
        durations = sorted(
            (r.finished_at - (r.started_at or r.created_at)).total_seconds() for r in finished
        )
        enough = len(finished) >= 20 and len(groups) <= 1
        return {
            "sample_size": len(finished),
            "unverified_samples": unverified,
            "duration_scope": "run_wall_time",
            "configuration_groups": groups,
            "incompatible_configurations": len(groups) > 1,
            "insufficient_samples": len(finished) < 20,
            "comparable": enough,
            "limit": 200,
            "dimensions": {
                "environment_id": environment_id,
                "transport_mode": transport_mode,
                "scenario_id": scenario_id,
                "version": scenario_version,
            },
            "first_attempts": len(originals),
            "first_failures": failures,
            "rerun_successes": rerun_success,
            "first_failure_rate": failures / len(originals) if enough and originals else None,
            "rerun_success_rate": rerun_success / (len(finished) - len(originals))
            if enough and len(finished) > len(originals)
            else None,
            "duration_p95_seconds": durations[
                min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)
            ]
            if enough and durations
            else None,
        }
