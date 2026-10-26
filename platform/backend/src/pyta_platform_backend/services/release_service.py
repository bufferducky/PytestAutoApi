"""发布报告是证据摘要，不执行部署；缺R07真实契约始终列未验证。"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from pyta_platform_backend.services.redaction import Redactor


def exit_code(detail):
    if detail.payload.get("run_purpose") == "debug":
        return 3
    status = detail.status.value if hasattr(detail.status, "value") else detail.status
    if status == "failed":
        return 1
    if status in {"error", "interrupted", "timed_out"}:
        return 2
    valid_ui = (
        detail.execution_mode == "ui_journey"
        and detail.transport_mode == "live"
        and detail.cleanup_status == "succeeded"
        and detail.counts.get("assertions", 0) > 0
        and not detail.counts.get("blocked")
        and not detail.counts.get("skipped")
        and not detail.evidence_pruned_at
        and not detail.payload.get("rerun_selection", {}).get("partial")
    )
    if status != "succeeded" or not (detail.eligible_for_release or valid_ui):
        return 3
    return 0


class ReleaseService:
    def __init__(self, repository, runs, assets):
        self.repository, self.runs, self.assets = repository, runs, assets
        self.journeys = None

    def build(self, payload):
        mode = payload.get("mode", "report_only")
        if mode not in {"report_only", "strict"}:
            raise HTTPException(400, "mode必须report_only/strict")
        ids = payload.get("run_ids", [])
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, "run_ids必须非空")
        details = [self.runs.get_run_detail(identifier) for identifier in dict.fromkeys(ids)]
        environments = {detail.environment_id for detail in details}
        scoped_environment = next(iter(environments)) if len(environments) == 1 else None
        build = payload.get("build", "unspecified")
        coverage = self.assets.coverage_summary(
            environment_id=scoped_environment, build=build, run_ids=ids
        )
        risks = coverage["required_unverified"]
        # 这些缺口来自用户确认暂缓的业务包；不能因静态账本为空就变成0风险。
        company = []
        for index in range(1, 17):
            key = "S" + str(index).zfill(2)
            verified = any(
                item.get("regression_id") == key and item["coverage_status"] == "verified"
                for item in coverage["items"]
            )
            if not verified:
                company.append(key)
        ui_readiness = (
            self.journeys.readiness(environment_id=scoped_environment, build=build, run_ids=ids)
            if self.journeys
            else None
        )
        ui_unverified = (
            [r["risk_id"] for r in ui_readiness["risks"] if r["validation"] != "verified"]
            if ui_readiness
            else ["W01", "W02", "W03", "W04", "A01", "A02", "A03", "A04"]
        )
        unverified = list(dict.fromkeys(risks + company + ui_unverified))
        reasons = []
        for detail in details:
            if exit_code(detail) != 0:
                reasons.append(
                    {
                        "run_id": detail.run_id,
                        "status": detail.status.value,
                        "validation_scope": detail.validation_scope,
                        "cleanup_status": detail.cleanup_status,
                    }
                )
            if not detail.finished_at or detail.finished_at < datetime.now(
                timezone.utc
            ) - timedelta(days=7):
                reasons.append({"run_id": detail.run_id, "reason": "evidence_stale_or_incomplete"})
        versions = {str(detail.payload.get("asset_ref")) for detail in details}
        if len(environments) > 1:
            reasons.append({"reason": "mixed_environments"})
        declared_builds = {
            detail.payload.get("build") for detail in details if detail.payload.get("build")
        }
        if payload.get("build") in {None, "", "unspecified"}:
            reasons.append({"reason": "build_unspecified"})
        elif declared_builds != {payload["build"]} or any(
            not detail.payload.get("build") for detail in details
        ):
            reasons.append({"reason": "run_build_evidence_missing_or_mismatched"})
        if unverified:
            reasons.append({"reason": "unverified_business_risks", "count": len(unverified)})
        codes = [exit_code(detail) for detail in details]
        code = 2 if 2 in codes else 1 if 1 in codes else 3 if reasons or 3 in codes else 0
        report = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "build": payload.get("build", "unspecified"),
            "run_ids": [d.run_id for d in details],
            "environment_ids": list(environments),
            "asset_versions": list(versions),
            "results": [
                {
                    "run_id": d.run_id,
                    "status": d.status.value,
                    "mode": d.transport_mode,
                    "counts": d.counts,
                    "cleanup_status": d.cleanup_status,
                    "validation_scope": d.validation_scope,
                }
                for d in details
            ],
            "unverified_risks": unverified,
            "unverified_discovered_observations": coverage["unverified"],
            "journey_risk_evidence": ui_readiness,
            "coverage_scope": {
                "environment_id": scoped_environment,
                "build": build,
                "run_ids": ids,
            },
            "reasons": reasons,
            "eligible_for_release": mode == "strict" and code == 0,
            "exit_code": code,
            "decision": "report_only_no_deployment_approval"
            if mode == "report_only"
            else "blocked"
            if code
            else "evidence_conditions_satisfied",
            "deferred_company_validation": "无证据风险不计通过；解除须有同范围契约和新鲜live结果",
        }
        return self.repository.report(Redactor(report).clean(report))
