"""历史评估报告与规则管理；新执行始终禁用。"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException

from pyta_platform_backend.repositories.asset_repository import asset_hash
from pyta_platform_backend.services.redaction import Redactor


class EvaluationService:
    def __init__(self, repository, runs):
        self.repository, self.runs = repository, runs
        self._calibration_lock = RLock()
        self.root = Path(__file__).resolve().parents[5]
        self.providers = {}

    def _version(self, kind, identifier, version):
        try:
            return self.repository.version(kind, identifier, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def validate_sample(self, sample):
        if (
            not all(sample.get(k) for k in ["sample_id", "category", "source", "applicable_tasks"])
            or not sample.get("authorized")
            or not sample.get("redacted")
        ):
            raise ValueError("样本缺ID/来源/授权/脱敏/适用矩阵")
        if Redactor(sample).clean(sample) != sample:
            raise ValueError("样本包含已识别敏感值")
        if sample.get("media"):
            media = sample["media"]
            path = (self.root / media["path"]).resolve()
            if (
                not path.is_relative_to(self.root / "Files" / "test-media")
                or not path.is_file()
                or path.stat().st_size > 16 * 1024 * 1024
            ):
                raise ValueError("媒体路径/大小不合法")
            if (
                path.stat().st_size != media["byte_size"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != media["sha256"]
            ):
                raise ValueError("评估媒体hash/大小不匹配")

    def dataset(self, data):
        data = dict(data)
        identifier = data.pop("id", None)
        if len(json.dumps(data)) > 4 * 1024 * 1024:
            raise HTTPException(400, "数据集定义超过4MiB")
        samples = data.get("samples", [])
        if data.get("schema_version", 1) != 1:
            raise HTTPException(400, "不支持的dataset schema_version")
        if not samples or len(samples) > 1000:
            raise HTTPException(400, "样本数须1—1000")
        try:
            ids = []
            for sample in samples:
                self.validate_sample(sample)
                ids.append(sample["sample_id"])
            if len(set(ids)) != len(ids):
                raise ValueError("sample_id重复")
            return self.repository.define(
                "datasets", {**data, **({"id": identifier} if identifier else {})}
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def register_provider(self, reference, callback, *, authorized_paid_calls=False):
        if not authorized_paid_calls or "@" not in reference or not callable(callback):
            raise ValueError("只有明确授权的受控provider才能注册")
        self.providers[reference] = callback

    def seed(self):
        raise HTTPException(410, "evaluation_seed_disabled: 内置演示数据导入已移除")

    def rubric(self, data):
        data = dict(data)
        identifier = data.pop("id", None)
        if data.get("rule_ref", "deterministic-rubric@1") != "deterministic-rubric@1":
            raise HTTPException(400, "未知rubric规则")
        if data.get("calibrated"):
            raise HTTPException(400, "不能自报已校准；先记录至少10个独立人工复核并另行批准质量门禁")
        if any(field in data for field in ["calibration", "approval", "calibrated_scope"]):
            raise HTTPException(400, "校准与审批字段只能由校准流程生成")
        if "thresholds" in data:
            self._validate_thresholds(data["thresholds"])
        public = {
            **data,
            "calibrated": False,
            "mode": "report_only",
            "rule_ref": "deterministic-rubric@1",
        }
        if Redactor(public).clean(public) != public:
            raise HTTPException(400, "rubric不能含秘密")
        return self.repository.define(
            "rubrics", {**public, **({"id": identifier} if identifier else {})}
        )

    def run(self, payload):
        raise HTTPException(
            409,
            {
                "code": "evaluation_execution_disabled",
                "message": "新评估执行已禁用；历史报告仍可读取",
            },
        )

    def save_report(self, run_id, data):
        with self.repository.transaction():
            self.repository._connection.execute(
                "INSERT INTO evaluation_reports (run_id,data_json) VALUES (?,?)",
                (run_id, json.dumps(Redactor().clean(data), ensure_ascii=False)),
            )

    def report(self, run_id):
        self.runs.get_run_detail(run_id)
        with self.repository._lock:
            row = self.repository._connection.execute(
                "SELECT data_json FROM evaluation_reports WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "评估报告尚未生成")
        result = json.loads(row[0])
        result["human_reviews"] = self.reviews(run_id)
        reviewed = {
            review["sample_id"]
            for review in result["human_reviews"]
            if review["review_source"] == "human"
        }
        conflicts = []
        for review in result["human_reviews"]:
            machine = next(
                (r for r in result["results"] if r["sample_id"] == review["sample_id"]), None
            )
            if machine and review["decision"] != machine.get("quality", {}).get("status"):
                conflicts.append(review["id"])
        result["review_conflicts"] = conflicts
        result["human_calibration"] = {
            "independently_reviewed_samples": len(reviewed),
            "minimum_required": 10,
            "thresholds_calibrated": result.get("quality_gate") == "calibrated_rule_report_only",
            "mode": "report_only",
        }
        return result

    def review(self, run_id, sample_id, payload):
        with self._calibration_lock:
            return self._review(run_id, sample_id, payload)

    def _review(self, run_id, sample_id, payload):
        allowed = {"decision", "reviewer", "reason", "review_source"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise HTTPException(400, "复核只能包含判定、复核人、理由与来源，不能改写ID/时间/归属")
        if any(
            not isinstance(payload.get(field), str) or not payload[field].strip()
            for field in ["decision", "reviewer", "reason"]
        ):
            raise HTTPException(400, "复核判定/复核人/理由须为非空文本")
        report = self.report(run_id)
        if not any(result["sample_id"] == sample_id for result in report["results"]):
            raise HTTPException(404, "样本结果不属于此run")
        if (
            payload.get("decision") not in {"passed", "failed", "undetermined"}
            or not payload.get("reviewer")
            or not payload.get("reason")
        ):
            raise HTTPException(400, "复核须独立判定/复核人/理由")
        if payload.get("review_source", "human") not in {"human", "test_fixture"}:
            raise HTTPException(400, "review_source不合法")
        data = {
            "id": uuid4().hex,
            "sample_id": sample_id,
            "run_id": run_id,
            **{key: value for key, value in payload.items() if key in allowed},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "review_source": payload.get("review_source", "human"),
        }
        data = Redactor().clean(data)
        with self.repository.transaction():
            self.repository._connection.execute(
                "INSERT INTO human_reviews (id,run_id,sample_id,data_json) VALUES (?,?,?,?)",
                (data["id"], run_id, sample_id, json.dumps(data, ensure_ascii=False)),
            )
        return data

    def reviews(self, run_id):
        with self.repository._lock:
            rows = self.repository._connection.execute(
                "SELECT data_json FROM human_reviews WHERE run_id=?", (run_id,)
            ).fetchall()
        return sorted(
            [json.loads(row[0]) for row in rows],
            key=lambda review: (review.get("created_at", ""), review["id"]),
        )

    def compare(self, run_id, other_id):
        a, b = self.report(run_id), self.report(other_id)
        if (a["dataset_hash"], a["rubric_hash"], a["task"], a["repeats"]) != (
            b["dataset_hash"],
            b["rubric_hash"],
            b["task"],
            b["repeats"],
        ):
            raise HTTPException(400, "不同集合/规则/任务/采样策略不能直接比较")
        return {
            "before": a,
            "after": b,
            "same_dataset_rubric": True,
            "note": "比较同一样本结果，不替代人工质量校准",
        }

    def revoke(self, identifier, version, reason):
        self._version("datasets", identifier, version)
        if not isinstance(reason, str) or len(reason.strip()) < 5:
            raise HTTPException(400, "撤回须说明依据")
        return self.repository.define(
            "dataset-revocations",
            {
                "dataset_id": identifier,
                "dataset_version": version,
                "reason": Redactor().clean(reason),
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _validate_thresholds(thresholds):
        keys = {
            "minimum_concept_coverage",
            "require_forbidden_constraint",
            "require_structure_complete",
        }
        if not isinstance(thresholds, dict) or set(thresholds) != keys:
            raise HTTPException(400, "阈值必须显式包含minimum_concept_coverage及两个require开关")
        coverage = thresholds["minimum_concept_coverage"]
        if (
            isinstance(coverage, bool)
            or not isinstance(coverage, (int, float))
            or not math.isfinite(coverage)
            or not 0 <= coverage <= 1
        ):
            raise HTTPException(400, "概念覆盖阈值必须为[0,1]有限数")
        if any(
            not isinstance(thresholds[key], bool) for key in keys - {"minimum_concept_coverage"}
        ):
            raise HTTPException(400, "require开关必须是bool")

    def calibration_preview(self, identifier, version, payload):
        rubric = self._version("rubrics", identifier, version)
        ids = payload.get("run_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > 100
            or not all(isinstance(item, str) for item in ids)
        ):
            raise HTTPException(400, "校准run_ids须为1—100个运行ID")
        thresholds = payload.get("thresholds")
        self._validate_thresholds(thresholds)
        scope = None
        selected = {}
        blockers = []
        review_snapshot = []
        for run_id in dict.fromkeys(ids):
            detail = self.runs.get_run_detail(run_id)
            if detail.status.value in {"queued", "running"}:
                raise HTTPException(409, "评估仍在运行，不能固定校准依据")
            report = self.report(run_id)
            if any(
                row["data"]["dataset_id"] == report["dataset_ref"]["id"]
                and row["data"]["dataset_version"] == report["dataset_ref"]["version"]
                for row in self.repository.definitions("dataset-revocations")
            ):
                raise HTTPException(409, "样本集已撤回，不能批准校准")
            if (
                report["rubric_ref"] != {"id": identifier, "version": version}
                or report["rubric_hash"] != rubric["hash"]
            ):
                raise HTTPException(409, "校准证据必须来自所选原始规则版本")
            current = {
                "dataset_hash": report["dataset_hash"],
                "task": report["task"],
                "repeats": report["repeats"],
                "provider_ref": report["provider_ref"],
                "model_config_hash": asset_hash(report["model_config"]),
            }
            if scope is not None and current != scope:
                raise HTTPException(409, "不能混合不同集合/任务/采样/provider/模型的人工校准")
            scope = current
            if report["task"] not in {"text", "analysis"}:
                raise HTTPException(400, "当前阈值校准仅支持文本/分析，不能伪造ASR或听感校准")
            if report["unassessed"] or report["external_service_failures"]:
                blockers.append({"run_id": run_id, "reason": "评估未完整或依赖服务失败"})
            latest = {}
            for review in report["human_reviews"]:
                if review["review_source"] == "human":
                    latest[review["sample_id"]] = review
            for sample_id, review in latest.items():
                review_snapshot.append(review)
                if review["decision"] == "undetermined":
                    continue
                selected[sample_id] = {
                    "sample_id": sample_id,
                    "run_id": run_id,
                    "review_id": review["id"],
                    "decision": review["decision"],
                    "machine_quality_statuses": list(
                        dict.fromkeys(
                            row.get("quality", {}).get("status", "not_assessed")
                            for row in report["results"]
                            if row["sample_id"] == sample_id
                        )
                    ),
                    "reviewer": review["reviewer"],
                    "reason": review["reason"],
                }
        if len(selected) < 10:
            blockers.append(
                {
                    "reason": "至少10个不同样本的独立human复核，test_fixture不计数",
                    "count": len(selected),
                }
            )
        basis = {
            "rubric_hash": rubric["hash"],
            "scope": scope,
            "run_ids": list(dict.fromkeys(ids)),
            "thresholds": thresholds,
            "reviews": review_snapshot,
        }
        return {
            "ready": not blockers,
            "blockers": blockers,
            "reviewed_samples": list(selected.values()),
            "independently_reviewed_samples": len(selected),
            "scope": scope,
            "thresholds": thresholds,
            "preview_token": asset_hash(basis),
            "mode": "report_only",
            "network_executed": False,
        }

    def approve_calibration(self, identifier, version, payload):
        # 单实例平台内审核与批准串行，预检令牌校验后不能穿插另一条复核写入。
        with self._calibration_lock:
            return self._approve_calibration(identifier, version, payload)

    def _approve_calibration(self, identifier, version, payload):
        approver = payload.get("approved_by")
        reason = payload.get("approval_reason")
        if (
            not isinstance(approver, str)
            or not approver.strip()
            or not isinstance(reason, str)
            or len(reason.strip()) < 5
        ):
            raise HTTPException(400, "必须显式填写批准人和批准依据；本服务不自动批准真实阈值")
        preview = self.calibration_preview(identifier, version, payload)
        if payload.get("preview_token") != preview["preview_token"]:
            raise HTTPException(409, "校准依据已变化或缺少预检令牌，请重新预检")
        if not preview["ready"]:
            raise HTTPException(
                409, {"message": "人工校准条件不足", "blockers": preview["blockers"]}
            )
        previous = self._version("rubrics", identifier, version)
        calibration = {
            **preview["scope"],
            "source_rubric_ref": {"id": identifier, "version": version, "hash": previous["hash"]},
            "run_ids": list(dict.fromkeys(payload["run_ids"])),
            "review_ids": [item["review_id"] for item in preview["reviewed_samples"]],
            "approved_by": approver.strip(),
            "approval_reason": reason.strip(),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "basis_hash": preview["preview_token"],
        }
        updated = {
            **previous["data"],
            "id": identifier,
            "calibrated": True,
            "mode": "report_only",
            "thresholds": preview["thresholds"],
            "calibration": calibration,
        }
        if Redactor(updated).clean(updated) != updated:
            raise HTTPException(400, "批准依据不能包含敏感值")
        return self.repository.define("rubrics", updated)
