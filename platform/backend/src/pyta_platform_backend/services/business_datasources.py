"""受控业务只读来源；与平台状态库完全独立，不接受页面提交SQL。"""

import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager

import pymysql
from pydantic import Field

from pyta_platform_backend.schemas.context import PublicModel
from pyta_platform_backend.workers.context_transport import secret_value


class BusinessDataError(ValueError):
    category = "data"
    request_sent = False


class BusinessDatasource(PublicModel):
    id: str
    name: str = "言迹只读测试库"
    host: str
    port: int = Field(3306, ge=1, le=65535)
    schema_name: str = Field("yanji", alias="schema")
    username_secret_ref: str
    password_secret_ref: str
    allowed_target_origin: str = "https://api-test.yanjiai.com"
    tenant_id: str
    project_id: str
    max_rows: int = Field(5000, ge=1, le=10000)
    connect_timeout_seconds: int = Field(5, ge=1, le=5)
    query_timeout_seconds: int = Field(10, ge=1, le=10)


def dump(model):
    return (
        model.model_dump(by_alias=True)
        if hasattr(model, "model_dump")
        else model.dict(by_alias=True)
    )


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def registry():
    try:
        raw = json.loads(os.environ.get("PYTA_BUSINESS_DATASOURCES_JSON", "[]"))
        if not isinstance(raw, list):
            raise ValueError()
        result = {}
        for item in raw:
            source = dump(BusinessDatasource(**item))
            if (
                not re.fullmatch(r"[\w-]{1,64}", source["id"])
                or source["id"] in result
                or source["schema"] != "yanji"
                or source["allowed_target_origin"] != "https://api-test.yanjiai.com"
                or not source["tenant_id"].isdigit()
                or not source["project_id"].isdigit()
                or not source["host"]
            ):
                raise ValueError()
            for key in ("username_secret_ref", "password_secret_ref"):
                if not re.fullmatch(r"env:PYTA_SECRET_[A-Z0-9_]+", source[key]):
                    raise ValueError()
            result[source["id"]] = {**source, "hash": fingerprint(source)}
        return result
    except (ValueError, TypeError) as exc:
        raise BusinessDataError("business_datasource_configuration_invalid") from exc


def resolve_source(identifier, context_snapshot=None):
    source = registry().get(identifier)
    if source is None:
        raise BusinessDataError("business_datasource_missing")
    if context_snapshot is not None:
        target, binding = context_snapshot["target"], context_snapshot.get("binding") or {}
        if (
            target["base_url"].rstrip("/") != source["allowed_target_origin"]
            or str(binding.get("tenant_id")) != source["tenant_id"]
            or str(binding.get("project_id")) != source["project_id"]
            or not context_snapshot.get("identity")
        ):
            raise BusinessDataError("business_datasource_context_mismatch")
    return source


def configuration(source):
    try:
        secret_value(source["username_secret_ref"])
        secret_value(source["password_secret_ref"])
        return "passed", None
    except ValueError:
        return "failed", "business_datasource_secret_missing"


def public_sources():
    result = []
    for source in registry().values():
        state, error = configuration(source)
        public = {k: v for k, v in source.items() if not k.endswith("secret_ref")}
        result.append({**public, "configuration": state, "configuration_error": error})
    return result


def check_budget(deadline=None, should_stop=None):
    stop = should_stop() if should_stop else None
    if stop:
        exc = BusinessDataError("business_datasource_cancelled")
        exc.execution_status = stop
        raise exc
    if deadline is not None and time.monotonic() >= deadline:
        exc = BusinessDataError("business_datasource_budget_exhausted")
        exc.execution_status = "timed_out"
        raise exc


@contextmanager
def read_connection(source, *, deadline=None, should_stop=None, remember_secret=None):
    check_budget(deadline, should_stop)
    connection = None
    try:
        username = secret_value(source["username_secret_ref"])
        password = secret_value(source["password_secret_ref"])
        if remember_secret:
            remember_secret(username)
            remember_secret(password)
        remaining = max(1, math.ceil(deadline - time.monotonic())) if deadline else 10
        timeout = min(source["query_timeout_seconds"], remaining)
        connection = pymysql.connect(
            host=source["host"],
            port=source["port"],
            user=username,
            password=password,
            database=source["schema"],
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=min(source["connect_timeout_seconds"], remaining),
            read_timeout=timeout,
            write_timeout=timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (timeout * 1000,))
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        check_budget(deadline, should_stop)
        yield connection
        check_budget(deadline, should_stop)
    except BusinessDataError:
        raise
    except Exception as exc:
        # DB驱动错误可能含口令、SQL值和服务器详情；公开证据仅保留分类码。
        raise BusinessDataError("business_datasource_query_failed") from exc
    finally:
        if connection is not None:
            try:
                try:
                    connection.rollback()
                finally:
                    connection.close()
            except Exception as exc:
                raise BusinessDataError("business_datasource_release_failed") from exc


def verify_permission(connection, source, expected_user_id):
    if not isinstance(expected_user_id, str) or not expected_user_id.isdigit():
        raise BusinessDataError("business_datasource_expected_user_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT u.id AS user_id, ur.role_id, CAST(r.is_super AS UNSIGNED) AS is_super, "
            "r.purpose FROM `user` u JOIN user_department ud ON ud.user_id=u.id "
            "AND ud.del_flag=0 AND ud.status=0 JOIN user_role ur ON ur.user_id=u.id "
            "AND ur.del_flag=0 AND ur.dept_id=ud.department_id AND ur.tenant_id=%s "
            "JOIN role r ON r.id=ur.role_id AND r.del_flag=0 AND r.tenant_id=%s "
            "AND r.dept_id=ud.department_id WHERE u.id=%s AND u.del_flag=0 AND u.status=0 "
            "AND u.tenant_id=%s AND ud.tenant_id=%s AND ud.department_id=%s LIMIT 20",
            (
                source["tenant_id"],
                source["tenant_id"],
                expected_user_id,
                source["tenant_id"],
                source["tenant_id"],
                source["project_id"],
            ),
        )
        roles = cursor.fetchall()
    if not roles or len(roles) >= 20 or not any(row["is_super"] == 1 for row in roles):
        raise BusinessDataError("business_datasource_permission_unconfirmed")
    # purpose来自服务端任意首角色，故所有有效角色都必须为空，避免猜测首行。
    if any(row["purpose"] for row in roles):
        raise BusinessDataError("business_datasource_permission_unconfirmed")
    return sorted(roles, key=lambda row: str(row["role_id"]))


def preflight_source(identifier, snapshot, expected_user_id, execute_query=False):
    result = {
        "configuration": "failed",
        "connection": "not_verified",
        "permission": "not_verified",
        "errors": [],
    }
    try:
        source = resolve_source(identifier, snapshot)
        result["configuration"], error = configuration(source)
        if error:
            raise BusinessDataError(error)
        if execute_query:
            with read_connection(source) as connection:
                result["connection"] = "passed"
                verify_permission(connection, source, expected_user_id)
                result["permission"] = "passed"
    except ValueError as exc:
        if result["configuration"] == "passed":
            result["permission" if result["connection"] == "passed" else "connection"] = "failed"
        result["errors"].append(str(exc))
    return result
