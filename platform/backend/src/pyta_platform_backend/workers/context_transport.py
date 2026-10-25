"""每个 run/目标/身份/项目独立会话；仅声明安全的查询允许一次鉴权重放。"""

import hashlib
import math
import os
import re
import time
from urllib.parse import urljoin, urlsplit

from testflow_engine import EnginePlugin, HttpxTransport, RequestSpec
from testflow_engine._field_path import resolve_field_path
from testflow_engine.executor.transport import TransportAdapter


class ContextError(ValueError):
    request_sent = False

    def __init__(self, code, category="configuration"):
        super().__init__(code)
        self.category = category


def secret_value(reference):
    if not re.fullmatch(r"env:PYTA_SECRET_[A-Z0-9_]+", reference or ""):
        raise ContextError("secret_ref 只能引用 env:PYTA_SECRET_*，不能读取任意文件/变量")
    value = os.environ.get(reference[4:])
    if not value:
        raise ContextError(f"secret_ref 不可用: {reference}")
    return value


def endpoint(base_url, path):
    if not path.startswith("/") or path.startswith("//") or ".." in path.split("/"):
        raise ContextError("认证/预检路径必须是目标内的绝对相对路径")
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def origin(url):
    parsed = urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname, parsed.port


class BoundedAttempts(list):
    def __init__(self, limit=100):
        super().__init__()
        self.limit, self.request_count, self.replay_count = limit, 0, 0

    def append(self, event):
        if event.get("kind") == "request":
            self.request_count += 1
            self.replay_count += int(event.get("replay") == 1)
        super().append(event)
        if len(self) > self.limit:
            del self[1]

    def extend(self, events):
        for event in events:
            self.append(event)


class ContextTransport(TransportAdapter):
    def __init__(self, snapshots, remember_secret=None, timeout_seconds=300):
        self.snapshots = snapshots
        self.remember_secret = remember_secret or (lambda value: None)
        self.sessions = {}
        self.deadline = time.monotonic() + timeout_seconds
        self.bootstrap_traces = {}

    def _session(self, key):
        if key not in self.snapshots:
            raise ContextError("未固定所选上下文快照", "context")
        snapshot = self.snapshots[key]
        target = snapshot["target"]
        identity, binding = snapshot.get("identity"), snapshot.get("binding")
        cache_key = (
            target["id"],
            target["revision"],
            identity["id"] if identity else None,
            binding["tenant_id"] if binding else None,
            binding["project_id"] if binding else None,
        )
        if cache_key not in self.sessions:
            self.sessions[cache_key] = _Session(snapshot, self.remember_secret, self.deadline)
        return self.sessions[cache_key]

    def send(self, request, context, case):
        key = case.metadata.get("context_binding_id", "default")
        session = self._session(key)
        traces = context.artifacts.setdefault("http_attempts", {}).setdefault(
            case.case_id, BoundedAttempts(case.wait_policy.trace_limit if case.wait_policy else 100)
        )
        traces.extend(self.bootstrap_traces.pop(key, []))
        original_deadline = session.deadline
        request_deadline = context.plugin_state.get("execution", {}).get(
            "request_deadline_monotonic"
        )
        if request_deadline is not None:
            session.deadline = min(session.deadline, request_deadline)
        try:
            return session.send(request, context, case, traces)
        finally:
            session.deadline = original_deadline

    def preflight(self, key="default"):
        traces = []
        session = self._session(key)
        session.login(None, None, traces)
        for check in session.target.get("checks", []):
            if not check["query_contract_confirmed"]:
                raise ContextError("query_contract_missing", "service")
            request = RequestSpec(
                method=check["method"],
                url=endpoint(session.target["base_url"], check["path"]),
                body=check["body"] if check["method"] != "GET" else None,
                timeout_seconds=min(5, session.remaining()),
            )
            session.inject(request)
            try:
                response = session.transport.send(request, None, None)
            except Exception as exc:
                raise ContextError("preflight_service_unavailable", "service") from exc
            if (
                response.status_code != 200
                or resolve_field_path(response.body, check["success_code_path"])
                != check["success_code"]
            ):
                raise ContextError("preflight_query_failed", "service")
            binding = session.snapshot.get("binding")
            for field, expected in [("tenant_path", "tenant_id"), ("project_path", "project_id")]:
                if (
                    check.get(field)
                    and binding
                    and str(resolve_field_path(response.body, check[field])) != binding[expected]
                ):
                    raise ContextError("context_response_mismatch", "context")
        return {
            "configuration": "passed",
            "authentication": "passed" if session.auth["mode"] != "none" else "not_required",
            "context": "passed" if session.target.get("checks") else "not_verified",
            "service": "passed" if session.target.get("checks") else "not_verified",
        }

    def close(self):
        for session in self.sessions.values():
            session.transport.close()


class _Session:
    def __init__(self, snapshot, remember_secret, deadline):
        self.snapshot = snapshot
        self.target = snapshot["target"]
        self.auth = self.target["auth"]
        self.remember_secret = remember_secret
        self.deadline, self.login_attempts = deadline, 0
        self.token, self.expiry = None, None
        self.transport = HttpxTransport(follow_redirects=False)

    def login(self, context, case, traces):
        if self.auth["mode"] == "none":
            return
        if not self.auth["contract_confirmed"]:
            raise ContextError("auth_contract_missing", "authentication")
        identity = self.snapshot.get("identity")
        if not identity:
            raise ContextError("identity_missing", "authentication")
        self.login_attempts += 1
        if self.login_attempts > 3:
            raise ContextError("login_attempt_limit", "authentication")
        username = secret_value(identity["username_secret_ref"])
        password = secret_value(identity["password_secret_ref"])
        self.remember_secret(password)
        if self.auth["password_transform"] == "md5":
            password = hashlib.md5(password.encode()).hexdigest()
        self.remember_secret(username)
        self.remember_secret(password)
        body = {self.auth["username_field"]: username, self.auth["password_field"]: password}
        request = RequestSpec(
            method="POST",
            url=endpoint(self.target["base_url"], self.auth["login_path"]),
            body_type=self.auth["request_mode"],
            body=body,
            timeout_seconds=min(self.auth["timeout_seconds"], self.remaining()),
        )
        try:
            request.timeout_seconds = min(request.timeout_seconds, self.remaining())
            response = self.transport.send(request, context, case)
        except Exception as exc:
            raise ContextError("login_service_unavailable", "service") from exc
        traces.append({"kind": "authentication", "status_code": response.status_code})
        if response.status_code != 200:
            raise ContextError("login_http_failed", "authentication")
        code = resolve_field_path(response.body, self.auth["success_code_path"])
        if code != self.auth["success_code"]:
            raise ContextError("login_business_code_failed", "authentication")
        token = resolve_field_path(response.body, self.auth["token_path"])
        if not isinstance(token, str) or not token:
            raise ContextError("login_token_missing", "authentication")
        if self.auth["header_template"] == "Bearer {token}" and token.startswith("Bearer "):
            raise ContextError("token_format_mismatch", "authentication")
        self.remember_secret(token)
        self.token = token
        self.expiry = None
        if self.auth.get("expiry_path"):
            raw = resolve_field_path(response.body, self.auth["expiry_path"])
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
                raise ContextError("login_expiry_invalid", "authentication")
            self.expiry = (
                raw / 1000
                if self.auth["expiry_format"] == "epoch_milliseconds"
                else (
                    time.time() + raw if self.auth["expiry_format"] == "relative_seconds" else raw
                )
            )

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("上下文运行预算已耗尽")
        return remaining

    def inject(self, request):
        headers = dict(request.headers)
        binding = self.snapshot.get("binding")
        inject = {}
        if self.auth["mode"] != "none":
            inject[self.auth["header_name"]] = self.auth["header_template"].format(token=self.token)
        if binding:
            inject.update({"Tenant-Id": binding["tenant_id"], "Dept-Id": binding["project_id"]})
        for key, value in inject.items():
            for existing in list(headers):
                if existing.lower() == key.lower():
                    if str(headers[existing]) != str(value):
                        raise ContextError("request_context_override_rejected", "context")
                    del headers[existing]
            headers[key] = value
        request.headers = headers

    def send(self, request, context, case, traces):
        if origin(request.url) != origin(self.target["base_url"]):
            raise ContextError("request_target_mismatch", "context")
        original_headers = dict(request.headers)
        if self.auth["mode"] != "none" and (
            self.token is None or self.expiry is not None and self.expiry <= time.time() + 1
        ):
            self.login(context, case, traces)
        self.inject(request)
        request.timeout_seconds = min(request.timeout_seconds, self.remaining())
        response = self.transport.send(request, context, case)
        traces.append(
            {
                "kind": "request",
                "status_code": response.status_code,
                "business_code": resolve_field_path(response.body, self.auth["success_code_path"]),
            }
        )
        unauthorized = (
            response.status_code == 401
            or resolve_field_path(response.body, self.auth["success_code_path"])
            == self.auth["unauthorized_business_code"]
        )
        state = context.plugin_state.get("execution", {}) if context else {}
        stopping = state.get("should_stop")
        if (
            not (stopping and stopping())
            and unauthorized
            and case.metadata.get("safe_to_replay") is True
            and case.metadata.get("operation_kind") == "query"
            and self.auth["mode"] != "none"
        ):
            self.login(context, case, traces)
            request.headers = original_headers
            self.inject(request)
            request.timeout_seconds = min(request.timeout_seconds, self.remaining())
            response = self.transport.send(request, context, case)
            traces.append(
                {
                    "kind": "request",
                    "status_code": response.status_code,
                    "business_code": resolve_field_path(
                        response.body, self.auth["success_code_path"]
                    ),
                    "replay": 1,
                }
            )
        return response


class ContextAuthPlugin(EnginePlugin):
    def __init__(self, transport):
        self.transport = transport

    def before_case(self, case, context):
        execution = context.plugin_state.get("execution", {})
        if execution.get("phase") == "cleanup":
            self.transport.deadline = execution["deadline_monotonic"]
            for session in self.transport.sessions.values():
                session.deadline = self.transport.deadline
        key = case.metadata.get("context_binding_id", "default")
        if key not in self.transport.snapshots:
            raise ContextError("context_snapshot_missing", "context")
        snapshot = self.transport.snapshots[key]
        context.variables["host"] = snapshot["target"]["base_url"]
        context.variables["identity"] = {
            "alias": (snapshot.get("identity") or {}).get("name"),
            "tenant_id": (snapshot.get("binding") or {}).get("tenant_id"),
            "project_id": (snapshot.get("binding") or {}).get("project_id"),
        }

    def before_run(self, run, context):
        traces = context.artifacts.setdefault("authentication", [])
        self.transport.bootstrap_traces["default"] = traces
        self.transport._session("default").login(context, None, traces)


def resolve_references(value, remember_secret):
    if isinstance(value, dict):
        if "secret_ref" in value:
            if set(value) - {"secret_ref", "transform"}:
                raise ContextError("secret_ref 结构不合法")
            resolved = secret_value(value["secret_ref"])
            remember_secret(resolved)
            transform = value.get("transform", "none")
            if transform == "md5":
                resolved = hashlib.md5(resolved.encode()).hexdigest()
                remember_secret(resolved)
            elif transform != "none":
                raise ContextError("不支持的凭证转换")
            return resolved
        return {key: resolve_references(child, remember_secret) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_references(child, remember_secret) for child in value]
    return value
