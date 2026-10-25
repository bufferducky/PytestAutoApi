"""受控HTTP资源provider。每个scope独立fixture；finally后按获取反序恢复/删除。"""

from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.services.redaction import Redactor
from pyta_platform_backend.workers.context_transport import ContextError, ContextTransport
from testflow_engine import EnginePlugin, ExecutionContext, RequestSpec
from testflow_engine import TestCaseDefinition as Case
from testflow_engine._field_path import resolve_field_path
from testflow_engine.executor.rendering import RequestTemplateRenderer


class FixtureError(ContextError):
    pass


class FixtureBlocked(FixtureError):
    execution_status = "blocked"


class FixtureStopped(FixtureError):
    def __init__(self, status):
        super().__init__("fixture_preparation_" + status, "data")
        self.execution_status = status


def ensure_fixture_active(context):
    execution = context.plugin_state.get("execution", {})
    if execution.get("phase") != "cleanup":
        signal = execution.get("should_stop")
        stopped = signal() if signal else None
        if stopped:
            raise FixtureStopped(
                stopped if stopped in {"cancelled", "timed_out", "error"} else "cancelled"
            )
    deadline = execution.get("deadline_monotonic")
    if deadline is not None and monotonic() >= deadline:
        raise FixtureStopped("timed_out")


def _send(definition, request, context, transport, key):
    ensure_fixture_active(context)
    if request is None:
        raise FixtureError("fixture_action_missing", "data")
    rendered = RequestTemplateRenderer().render(RequestSpec(**request), context)
    remaining = (
        context.plugin_state.get("execution", {}).get("deadline_monotonic", monotonic() + 30)
        - monotonic()
    )
    if remaining <= 0:
        raise TimeoutError("fixture时间预算耗尽")
    rendered.timeout_seconds = min(rendered.timeout_seconds, remaining)
    case = Case(
        case_id="fixture-action",
        title="fixture",
        request=rendered,
        metadata={"context_binding_id": key},
    )
    response = transport.send(rendered, context, case)
    if (
        response.status_code >= 400
        or resolve_field_path(response.body, definition["success_code_path"])
        != definition["success_code"]
    ):
        if (
            resolve_field_path(response.body, definition["success_code_path"])
            not in definition["already_absent_codes"]
        ):
            raise FixtureError("fixture_business_action_failed", "data")
    return response


class ResourcePlugin(EnginePlugin):
    def __init__(self, repository, transport, snapshots, plan, *, redactor=None):
        self.repository, self.transport, self.snapshots = repository, transport, snapshots
        self.plan = plan
        self.redactor = redactor or Redactor()
        self.acquired = []
        self.scopes = {}
        self.failed = set()

    def before_case(self, case, context):
        scope = case.metadata.get("scope_id", "scenario")
        phase = context.plugin_state.get("execution", {}).get("phase")
        if phase == "cleanup":
            return
        ensure_fixture_active(context)
        if scope in self.failed:
            raise FixtureBlocked("fixture_scope_acquire_failed", "data")
        if scope not in self.scopes:
            self.scopes[scope] = context
            try:
                context.variables.setdefault("runtime", {}).update(
                    run_id=context.run_id, test_prefix="auto-" + context.run_id[:12]
                )
                for requirement in self.plan.get(scope, []):
                    self.acquire(requirement, scope, context, case)
            except Exception:
                self.failed.add(scope)
                raise
        ensure_fixture_active(context)
        for record in self.acquired:
            if record["scope_id"] == scope and record.get("lease"):
                self.repository.check_lease(record["lease"])
                record["state"] = "in_use"
                self.repository.put_resource(record)

    def acquire(self, requirement, scope, context, case):
        ensure_fixture_active(context)
        context.variables.setdefault("runtime", {})["test_prefix"] = (
            "auto-" + context.run_id[:12] + "-" + scope + "-" + requirement["name"]
        )
        definition = requirement["definition"]["data"]
        if definition["provider_ref"] != "http-resource@1" or not definition["contract_confirmed"]:
            raise FixtureBlocked("fixture_contract_or_provider_missing", "data")
        key = case.metadata.get("context_binding_id", "default")
        snapshot = self.snapshots.get(key) or {}
        target = snapshot.get("target") or {}
        if not target.get("id") or not target.get("base_url"):
            raise FixtureBlocked("fixture_context_snapshot_missing", "context")
        binding = snapshot.get("binding") or {}
        if target.get("requires_context") and not all(
            binding.get(field) for field in ("tenant_id", "project_id")
        ):
            raise FixtureBlocked("fixture_context_binding_missing", "context")
        owner = {
            "target_id": target["id"],
            "tenant_id": binding.get("tenant_id", ""),
            "project_id": binding.get("project_id", ""),
        }
        record = {
            "id": uuid4().hex,
            "run_id": context.run_id,
            "fixture_id": requirement["name"],
            "scope_id": scope,
            "alias": scope + "." + requirement["name"],
            "state": "acquiring",
            "strategy": definition["strategy"],
            "definition": requirement["definition"],
            "context": owner,
            "context_snapshot": snapshot,
            "context_key": key,
            "depends_on": requirement["depends_on"],
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "cleanup_variables": {},
            "object_id": None,
        }
        self.repository.put_resource(record)
        self.acquired.append(record)
        fixtures = context.variables.setdefault("fixtures", {})
        try:
            if definition["strategy"] == "create":
                response = _send(
                    definition, definition["acquire_request"], context, self.transport, key
                )
                record["object_id"] = resolve_field_path(response.body, definition["id_path"])
                if record["object_id"] is None:
                    raise FixtureError("fixture_id_missing_after_create", "data")
            elif definition["strategy"] == "lease":
                record["lease"] = self.repository.lease(
                    definition["pool_id"], record["id"], owner, definition["lease_seconds"]
                )
                record["object_id"] = record["lease"]["object_id"]
            else:
                candidates = [
                    r
                    for r in self.repository.pool()
                    if r["pool_id"] == definition["pool_id"]
                    and r["object_id"] == definition["object_id"]
                    and all(r[k] == owner[k] for k in owner)
                ]
                if not candidates:
                    raise FixtureBlocked("readonly_test_resource_not_verified", "data")
                record["object_id"] = definition["object_id"]
            fixtures[requirement["name"]] = {"id": record["object_id"], "alias": record["alias"]}
            if not isinstance(record["object_id"], (str, int)) or isinstance(
                record["object_id"], bool
            ):
                raise FixtureError("fixture_id_invalid", "data")
            record["object_id"] = str(record["object_id"])
            fixtures[requirement["name"]]["id"] = record["object_id"]
            record["state"] = "acquired"
            self.repository.put_resource(record)
            if definition["strategy"] == "lease" and definition["restore_required"]:
                response = _send(
                    definition, definition["snapshot_request"], context, self.transport, key
                )
                # 原值是业务公开状态，不允许持久保存秘密用于恢复。
                if self.redactor.clean(response.body) != response.body:
                    raise FixtureError("restore_snapshot_contains_secret", "data")
                fixtures[requirement["name"]]["original"] = response.body
            record["cleanup_variables"] = self.redactor.clean(
                {
                    key: context.variables.get(key, {})
                    for key in ["fixtures", "outputs", "params", "runtime"]
                }
            )
            self.repository.put_resource(record)
        except Exception as exc:
            record["failure_reason"] = self.redactor.clean(str(exc))
            record["state"] = (
                "ownership_unknown"
                if definition["strategy"] == "create" and not record["object_id"]
                else "cleanup_failed"
            )
            self.repository.put_resource(record)
            if isinstance(exc, RunConflict):
                raise FixtureBlocked(str(exc), "data") from exc
            raise

    def after_case(self, case, result, context):
        scope = case.metadata.get("scope_id", "scenario")
        if context.plugin_state.get("execution", {}).get("phase") == "cleanup":
            return
        try:
            for record in self.acquired:
                if record["scope_id"] == scope and record["state"] in {"acquired", "in_use"}:
                    record["cleanup_variables"] = self.redactor.clean(
                        {
                            key: context.variables.get(key, {})
                            for key in ["fixtures", "outputs", "params", "runtime"]
                        }
                    )
                    self.repository.put_resource(record)
        except Exception:
            self.failed.add(scope)
            raise

    def after_run(self, result, context):
        for record in reversed(self.acquired):
            if record["state"] == "ownership_unknown":
                result.cleanup_status = "cleanup_failed"
                continue
            if not record.get("object_id"):
                continue
            own = self.scopes.get(record["scope_id"], context)
            own.plugin_state = context.plugin_state
            try:
                cleanup_record(self.repository, record, context=own, transport=self.transport)
            except Exception:
                result.cleanup_status = "cleanup_failed"


def cleanup_record(repository, record, context=None, transport=None):
    if not record.get("object_id") or record["state"] == "ownership_unknown":
        raise FixtureError("ownership_unverified", "data")
    owned = next(
        (r for r in repository.resources(record["run_id"]) if r["id"] == record["id"]), None
    )
    if (
        owned is None
        or owned["context"] != record["context"]
        or owned.get("object_id") != record["object_id"]
    ):
        raise FixtureError("resource_ownership_mismatch", "data")
    record = owned
    if record.get("simulated"):
        raise FixtureBlocked("historical_simulated_resource_read_only", "data")
    snapshot = record.get("context_snapshot") or {}
    target = snapshot.get("target") or {}
    if (
        not target.get("id")
        or not target.get("base_url")
        or target["id"] != record["context"].get("target_id")
    ):
        raise FixtureBlocked("fixture_context_snapshot_missing", "context")
    definition = record["definition"]["data"]
    created_transport = False
    if context is None:
        variables = deepcopy(record["cleanup_variables"])
        fixtures = variables.setdefault("fixtures", {})
        for known in repository.resources(record["run_id"]):
            if (
                known["scope_id"] == record["scope_id"]
                and known.get("object_id")
                and known["state"] != "ownership_unknown"
            ):
                fixtures.setdefault(
                    known["fixture_id"], {"id": known["object_id"], "alias": known["alias"]}
                )
        context = ExecutionContext(
            run_id=record["run_id"],
            variables={
                **variables,
                "host": record["context_snapshot"]["target"]["base_url"],
            },
        )
        context.plugin_state["execution"] = {
            "phase": "cleanup",
            "deadline_monotonic": monotonic() + 60,
        }
    try:
        if transport is None:
            transport = ContextTransport({record["context_key"]: record["context_snapshot"]})
            created_transport = True
        if isinstance(transport, ContextTransport):
            transport.deadline = context.plugin_state.get("execution", {}).get(
                "deadline_monotonic", monotonic() + 60
            )
            for session in transport.sessions.values():
                session.deadline = transport.deadline
        record["state"] = "releasing"
        repository.put_resource(record)
        should_restore = (
            record["strategy"] == "create"
            or record["strategy"] == "lease"
            and definition["restore_required"]
        )
        if should_restore:
            _send(
                definition, definition["release_request"], context, transport, record["context_key"]
            )
        if record.get("lease"):
            repository.release_lease(record["lease"])
        record["state"] = "released"
        repository.put_resource(record)
        repository.audit(
            record["run_id"], "release", {"id": record["id"], "object_id": record["object_id"]}
        )
    except Exception:
        record["state"] = "cleanup_failed"
        repository.put_resource(record)
        raise
    finally:
        if created_transport:
            transport.close()
