"""管理公开配置、引用校验和运行快照；没有全局当前登录用户。"""

from copy import deepcopy
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import HTTPException

from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.schemas.context import ContextBinding, IdentityProfile, TargetProfile
from pyta_platform_backend.services.redaction import Redactor
from pyta_platform_backend.workers.context_transport import (
    ContextError,
    ContextTransport,
    endpoint,
    secret_value,
)

MODELS = {
    "targets": TargetProfile,
    "identity-profiles": IdentityProfile,
    "context-bindings": ContextBinding,
}


class ContextService:
    def __init__(self, repository, management_repository, run_repository):
        self.repository, self.management = repository, management_repository
        self.runs = run_repository
        self._preflight_lock = Lock()
        self._preflight_times = {}
        for environment in self.management.list_environments():
            identifier = "default-" + environment.id
            if not self.repository.exists("targets", identifier):
                self.save(
                    "targets",
                    {
                        "id": identifier,
                        "name": environment.name + "（迁移目标）",
                        "environment_id": environment.id,
                        "base_url": environment.base_url,
                    },
                    creating=True,
                )

    def list(self, kind):
        return self.repository.list(kind)

    def get(self, kind, identifier):
        try:
            return self.repository.get(kind, identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def save(self, kind, data, *, creating=False):
        try:
            model = MODELS[kind](**data)
            data = model.model_dump() if hasattr(model, "model_dump") else model.dict()
            if Redactor(data).clean(data) != data:
                raise ValueError("公开配置不能包含凭证明文，请使用 secret_ref")
            if kind == "targets":
                parsed = urlsplit(data["base_url"])
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("base_url 必须是无凭证/查询参数的 HTTP(S) 地址")
                for upload_origin in data["allowed_upload_origins"]:
                    upload = urlsplit(upload_origin)
                    if (
                        upload.scheme not in {"http", "https"}
                        or not upload.hostname
                        or upload.username
                        or upload.password
                        or upload.query
                        or upload.fragment
                        or upload.path not in {"", "/"}
                    ):
                        raise ValueError("allowed_upload_origins只能是明确无凭证的HTTP(S)源")
                data["base_url"] = data["base_url"].rstrip("/")
                if self.management.get_environment_by_id(data["environment_id"]) is None:
                    raise KeyError("environment 不存在")
                endpoint(data["base_url"], data["auth"]["login_path"])
                for check in data["checks"]:
                    endpoint(data["base_url"], check["path"])
            elif kind == "identity-profiles":
                for target_id in data["target_ids"]:
                    self.repository.get("targets", target_id)
                # 只检查引用语法，配置创建不需要也不回显实际值。
                import re

                if not all(
                    re.fullmatch(r"env:PYTA_SECRET_[A-Z0-9_]+", data[field])
                    for field in ["username_secret_ref", "password_secret_ref"]
                ):
                    raise ValueError("凭证必须引用 env:PYTA_SECRET_*")
            else:
                target = self.repository.get("targets", data["target_id"])
                identity = self.repository.get("identity-profiles", data["identity_id"])
                if target["id"] not in identity["target_ids"]:
                    raise ValueError("身份不支持该 target")
            return self.repository.save(kind, data, creating=creating)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, Redactor(data).clean(str(exc))) from exc

    def delete(self, kind, identifier, revision):
        current = self.get(kind, identifier)
        if current["revision"] != revision:
            raise HTTPException(409, "配置已更新")
        for binding in self.list("context-bindings"):
            if (
                kind == "targets"
                and binding["target_id"] == identifier
                or kind == "identity-profiles"
                and binding["identity_id"] == identifier
            ):
                raise HTTPException(409, "配置被上下文绑定引用，请先解除引用")
        if kind == "targets" and any(
            identifier in identity["target_ids"] for identity in self.list("identity-profiles")
        ):
            raise HTTPException(409, "目标被身份配置引用")
        for record in self.runs.list_queued_records() + self.runs.list_running_records():
            for snapshot in record.payload.get("context_snapshots", {}).values():
                field = {
                    "targets": "target",
                    "identity-profiles": "identity",
                    "context-bindings": "binding",
                }[kind]
                if (snapshot.get(field) or {}).get("id") == identifier:
                    raise HTTPException(409, "配置被待执行/运行任务引用")
        try:
            return self.repository.save(kind, current, deleting=True)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def snapshot(self, target_id, identity_id=None, binding_id=None, environment_id=None):
        target = self.get("targets", target_id)
        if environment_id and target["environment_id"] != environment_id:
            raise ContextError("target 不属于所选 environment", "context")
        binding = self.get("context-bindings", binding_id) if binding_id else None
        if target["requires_context"] and binding is None:
            raise ContextError("context_binding_missing", "context")
        if binding:
            if (
                binding["target_id"] != target_id
                or identity_id
                and binding["identity_id"] != identity_id
            ):
                raise ContextError("context_binding_mismatch", "context")
            identity_id = binding["identity_id"]
        identity = self.get("identity-profiles", identity_id) if identity_id else None
        if identity and target_id not in identity["target_ids"]:
            raise ContextError("identity_target_mismatch", "context")
        if target["auth"]["mode"] != "none":
            if not target["auth"]["contract_confirmed"]:
                raise ContextError("auth_contract_missing", "authentication")
            if identity is None:
                raise ContextError("identity_missing", "authentication")
        if self.management.get_environment_by_id(target["environment_id"]) is None:
            raise ContextError("target_environment_missing", "context")
        return deepcopy({"target": target, "identity": identity, "binding": binding})

    def prepare(self, request, payload):
        if not request.target_id:
            return payload  # 旧 inline 定义兼容；新版资产选择明确 target。
        if "context_snapshots" in payload:
            raise ContextError("上下文快照由服务生成，不能通过 payload 覆盖")
        snapshots = {
            "default": self.snapshot(
                request.target_id,
                request.identity_id,
                request.context_binding_id,
                request.environment_id,
            )
        }
        for binding_id in request.additional_context_binding_ids:
            binding = self.get("context-bindings", binding_id)
            snapshots[binding_id] = self.snapshot(
                binding["target_id"], binding_id=binding_id, environment_id=request.environment_id
            )
        for case in payload.get("run_definition", {}).get("cases", []) + payload.get(
            "run_definition", {}
        ).get("cleanup_cases", []):
            if case.get("metadata", {}).get("context_binding_id", "default") not in snapshots:
                raise ContextError("case_context_snapshot_missing", "context")
        payload = deepcopy(payload)
        payload["context_snapshots"] = snapshots
        return payload

    def preflight(self, environment_id, request):
        if request.execute_login:
            key = (request.target_id, request.identity_id, request.context_binding_id)
            with self._preflight_lock:
                now = monotonic()
                recent = [t for t in self._preflight_times.get(key, []) if t > now - 60]
                if len(recent) >= 3:
                    raise HTTPException(429, "预检登录频率上限：每身份/上下文每分钟 3 次")
                self._preflight_times[key] = recent + [now]
        try:
            snapshot = self.snapshot(
                request.target_id, request.identity_id, request.context_binding_id, environment_id
            )
            identity = snapshot.get("identity")
            if identity:
                secret_value(identity["username_secret_ref"])
                secret_value(identity["password_secret_ref"])
            if not request.execute_login:
                return {
                    "configuration": "passed",
                    "authentication": "not_run",
                    "context": "not_run",
                    "service": "not_run",
                }
            transport = ContextTransport({"default": snapshot})
            try:
                return transport.preflight()
            finally:
                transport.close()
        except ContextError as exc:
            return {
                "configuration": "failed" if exc.category == "configuration" else "passed",
                "authentication": "failed" if exc.category == "authentication" else "not_verified",
                "context": "failed" if exc.category == "context" else "not_verified",
                "service": "failed" if exc.category == "service" else "not_verified",
                "error_code": str(exc),
            }
