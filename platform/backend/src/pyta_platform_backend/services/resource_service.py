"""fixture定义、媒体校验和手动清理；仅操作有所有权证据的测试对象。"""

import hashlib
import json
import wave
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException

from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.schemas.resources import FixtureDefinition, MediaManifest, PoolResource
from pyta_platform_backend.services.redaction import Redactor


class ResourceService:
    def __init__(self, repository, run_service, media_root=None):
        self.repository, self.runs = repository, run_service
        self.media_root = Path(
            media_root or Path(__file__).resolve().parents[5] / "Files" / "test-media"
        ).resolve()

    def define(self, data):
        data = deepcopy(data)
        identifier = data.pop("id", None)
        try:
            definition = FixtureDefinition(**data)
            public = (
                definition.model_dump() if hasattr(definition, "model_dump") else definition.dict()
            )
            if Redactor(public).clean(public) != public:
                raise ValueError("fixture不能保存凭证明文")
            if definition.strategy == "create" and (
                definition.acquire_request is None or definition.release_request is None
            ):
                raise ValueError("create必须有已确认创建和清理请求")
            if definition.strategy in {"lease", "read_only"} and not definition.pool_id:
                raise ValueError("lease/read_only必须指定专属pool")
            if definition.strategy == "read_only" and not definition.object_id:
                raise ValueError("read_only必须显式指定已核验object_id")
            if (
                definition.strategy == "lease"
                and definition.restore_required
                and (definition.snapshot_request is None or definition.release_request is None)
            ):
                raise ValueError("借用可写对象必须有原值查询与恢复请求")
            return self.repository.define(
                "fixtures", {**public, **({"id": identifier} if identifier else {})}
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, Redactor(data).clean(str(exc))) from exc

    def fixture(self, identifier, version):
        try:
            return self.repository.version("fixtures", identifier, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def add_pool(self, data):
        try:
            model = PoolResource(**data)
            values = model.model_dump() if hasattr(model, "model_dump") else model.dict()
            target = self.runs.context_service.get("targets", values["target_id"])
            if target["requires_context"] and not any(
                binding["target_id"] == target["id"]
                and binding["tenant_id"] == values["tenant_id"]
                and binding["project_id"] == values["project_id"]
                for binding in self.runs.context_service.list("context-bindings")
            ):
                raise ValueError("资源池tenant/project未匹配已配置测试绑定")
            return self.repository.add_pool(values)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def dry_run(self, plan):
        return {
            "fixtures": [
                {
                    "name": r["name"],
                    "strategy": r["definition"]["data"]["strategy"],
                    "version": r["definition"]["version"],
                    "depends_on": r["depends_on"],
                }
                for r in plan
            ],
            "network_executed": False,
        }

    def media(self, data):
        data = deepcopy(data)
        identifier = data.pop("id", None)
        try:
            manifest = MediaManifest(**data)
            self.validate_media(manifest)
            public = manifest.model_dump() if hasattr(manifest, "model_dump") else manifest.dict()
            return self.repository.define(
                "media", {**public, **({"id": identifier} if identifier else {})}
            )
        except (ValueError, OSError, wave.Error) as exc:
            raise HTTPException(400, str(exc)) from exc

    def validate_media(self, manifest):
        path = (self.media_root / manifest.path).resolve()
        if not path.is_relative_to(self.media_root) or not path.is_file():
            raise ValueError("音频必须位于专属测试媒体目录")
        if (
            not manifest.authorized
            or not manifest.redacted
            or not manifest.source
            or not manifest.applicable_scenarios
        ):
            raise ValueError("音频缺少来源授权/脱敏/适用场景")
        size = path.stat().st_size
        if size != manifest.byte_size or size > 16 * 1024 * 1024:
            raise ValueError("音频大小不匹配或超过16MiB")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest.sha256:
            raise ValueError("音频hash不匹配")
        if manifest.format == "wav":
            with wave.open(str(path), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            if abs(duration - manifest.duration_seconds) > 0.02:
                raise ValueError("WAV时长与manifest不一致")
        elif not (raw.startswith(b"ID3") or raw[:1] == b"\xff"):
            raise ValueError("MP3格式不匹配")
        return path

    def media_preflight(self, identifier, version):
        try:
            value = self.repository.version("media", identifier, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        self.validate_media(MediaManifest(**value["data"]))
        return {
            "id": identifier,
            "version": version,
            "hash": value["hash"],
            "valid": True,
            "upload_contract": "not_verified",
            "network_executed": False,
        }

    def cleanup_preflight(self, run_id):
        self.runs.get_run_detail(run_id)
        rows = self.repository.resources(run_id)
        ready = [
            r["id"]
            for r in rows
            if r.get("object_id")
            and "[REDACTED]" not in json.dumps(r.get("cleanup_variables", {}))
            and r["state"] in {"acquired", "in_use", "cleanup_failed", "needs_reconciliation"}
        ]
        return {
            "run_id": run_id,
            "ready": ready,
            "blocked": [r["id"] for r in rows if r["state"] == "ownership_unknown"],
            "network_executed": False,
            "preflight_token": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest(),
        }

    def cleanup(self, run_id, token):
        detail = self.runs.get_run_detail(run_id)
        if detail.status.value in {"queued", "running"}:
            raise HTTPException(409, "运行未结束，不能抢占清理")
        preflight = self.cleanup_preflight(run_id)
        if preflight["preflight_token"] != token:
            raise HTTPException(409, "资源已变化，请重新预检")
        from pyta_platform_backend.workers.resource_plugin import cleanup_record

        results = []
        for record in reversed(self.repository.resources(run_id)):
            if record["id"] in preflight["ready"]:
                try:
                    cleanup_record(self.repository, record)
                    results.append({"id": record["id"], "state": "released"})
                except Exception:
                    results.append({"id": record["id"], "state": "cleanup_failed"})
        current = self.repository.resources(run_id)
        status = (
            "succeeded"
            if all(r["state"] == "released" for r in current)
            else "needs_reconciliation"
        )
        self.runs.repository.update_cleanup(run_id, status)
        self.repository.audit(run_id, "manual_cleanup", results)
        return {"results": results, "blocked": preflight["blocked"]}

    def confirm_reconciled(self, run_id, resource_id, reason):
        self.runs.get_run_detail(run_id)
        record = next(
            (r for r in self.repository.resources(run_id) if r["id"] == resource_id), None
        )
        if record is None:
            raise HTTPException(404, "不属于该run的资源")
        if not reason or len(reason.strip()) < 5:
            raise HTTPException(400, "必须提供核查依据")
        if self.runs.get_run_detail(run_id).status.value in {"queued", "running"}:
            raise HTTPException(409, "运行未结束")
        if record["state"] not in {"ownership_unknown", "needs_reconciliation", "cleanup_failed"}:
            raise HTTPException(409, "资源不需要人工对账")
        if record.get("lease"):
            self.repository.release_lease(record["lease"])
        record["state"] = "released"
        self.repository.put_resource(record)
        self.repository.audit(
            run_id, "manual_reconciliation", {"id": resource_id, "reason": Redactor().clean(reason)}
        )
        return record

    def renew(self, resource_id, run_id, seconds):
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 86400:
            raise HTTPException(400, "续租秒数必须在1—86400")
        if self.runs.get_run_detail(run_id).status.value != "running":
            raise HTTPException(409, "只允许有效运行续租")
        record = next(
            (r for r in self.repository.resources(run_id) if r["id"] == resource_id), None
        )
        if record is None or not record.get("lease"):
            raise HTTPException(404, "未找到属于此run的租约资源")
        try:
            record["lease"] = self.repository.renew(record["lease"], seconds)
            self.repository.put_resource(record)
            self.repository.audit(
                run_id, "renew", {"id": resource_id, "expires_at": record["lease"]["expires_at"]}
            )
            return record["lease"]
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def upload_media(
        self, identifier, version, *, signed_url, target_id, contract_confirmed, context_service
    ):
        # 供worker/provider调用；不在管理API中同步运行长上传任务。
        from urllib.parse import urlsplit

        import httpx

        if not contract_confirmed:
            raise ValueError("upload_contract_missing")
        manifest = self.repository.version("media", identifier, version)
        path = self.validate_media(MediaManifest(**manifest["data"]))
        target = context_service.get("targets", target_id)
        destination = urlsplit(signed_url)
        allowed = urlsplit(target["base_url"])
        origins = {(allowed.scheme, allowed.hostname, allowed.port)}
        for origin_value in target.get("allowed_upload_origins", []):
            parsed = urlsplit(origin_value)
            origins.add((parsed.scheme, parsed.hostname, parsed.port))
        if (destination.scheme, destination.hostname, destination.port) not in origins:
            raise ValueError("签名上传目标不在已选择测试target的明确白名单内")
        if destination.username or destination.password:
            raise ValueError("上传URL不能含用户凭证")
        try:
            with httpx.Client(follow_redirects=False, timeout=30) as client:
                with path.open("rb") as audio:
                    response = client.put(
                        signed_url,
                        content=audio,
                        headers={"Content-Length": str(path.stat().st_size)},
                    )
            if not 200 <= response.status_code < 300:
                raise ValueError("媒体上传失败")
            return {
                "id": identifier,
                "version": version,
                "sha256": manifest["data"]["sha256"],
                "byte_size": path.stat().st_size,
                "uploaded": True,
            }
        except httpx.HTTPError as exc:
            # 不回显签名URL、响应正文或底层异常中的URL。
            raise ValueError("媒体上传服务不可用") from exc
