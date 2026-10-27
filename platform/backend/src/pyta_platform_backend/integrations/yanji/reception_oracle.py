"""言迹接诊独立期望：读取有限事实，在Python中组合筛选与分页等价组。"""

from collections import Counter
from datetime import date, datetime, timedelta
from itertools import groupby

from pyta_platform_backend.services.business_datasources import (
    BusinessDataError,
    check_budget,
    fingerprint,
    read_connection,
    verify_permission,
)

CONTRACT = "yanji-reception@1"
FILTERS = {
    "pageNum",
    "pageSize",
    "roleId",
    "keyword",
    "statuses",
    "customerTypes",
    "receptionUserIds",
    "startDate",
    "endDate",
    "recordDurationStatus",
}
PRESETS = {
    "default",
    "status",
    "customer_type",
    "date",
    "reception_user",
    "combined",
    "keyword_existing",
    "keyword_empty",
    "no_record",
    "short_record",
    "sweep",
}
EMPTY_DIFF = {"missing_ids": [], "extra_ids": [], "duplicate_ids": [], "problems": []}


def read_facts(source, expected_user_id, keyword="", **budget):
    with read_connection(source, **budget) as connection:
        permissions = verify_permission(connection, source, expected_user_id)
        check_budget(budget.get("deadline"), budget.get("should_stop"))
        with connection.cursor() as cursor:
            # 不取回姓名/手机号；LIKE命中在DB排序规则下转为布尔事实。
            cursor.execute(
                "SELECT f.id,f.tenant_id,f.dept_id,f.reception_user,f.reception_time,"
                "f.create_time,f.status,f.customer_type,"
                "(SELECT COUNT(*) FROM customer_reception_form_iot_record ir "
                "WHERE ir.customer_reception_form_id=f.id AND ir.del_flag=0 "
                "AND ir.tenant_id=%s AND ir.dept_id=%s) AS record_count,"
                "(SELECT COALESCE(SUM(r.seconds),0) FROM customer_reception_form_iot_record ir "
                "JOIN iot_device_record r ON r.id=ir.iot_record_id AND r.del_flag=0 "
                "AND r.tenant_id=%s AND r.dept_id=%s "
                "WHERE ir.customer_reception_form_id=f.id AND ir.del_flag=0 "
                "AND ir.tenant_id=%s AND ir.dept_id=%s) AS record_seconds,"
                "CASE WHEN %s='' OR c.name LIKE CONCAT('%%',%s,'%%') "
                "OR c.phone LIKE CONCAT('%%',%s,'%%') OR c.member_id LIKE CONCAT('%%',%s,'%%') "
                "OR f.id=%s OR f.third_id=%s THEN 1 ELSE 0 END AS keyword_hit "
                "FROM customer_reception_form f LEFT JOIN customer c ON c.id=f.customer_id "
                "AND c.del_flag=0 AND c.tenant_id=%s AND c.dept_id=%s "
                "WHERE f.del_flag=0 AND f.reception_type='offline' "
                "AND f.tenant_id=%s AND f.dept_id=%s ORDER BY f.id LIMIT %s",
                (
                    *[source[k] for _ in range(3) for k in ("tenant_id", "project_id")],
                    *([keyword] * 6),
                    source["tenant_id"],
                    source["project_id"],
                    source["tenant_id"],
                    source["project_id"],
                    source["max_rows"] + 1,
                ),
            )
            rows = cursor.fetchall()
        if len(rows) > source["max_rows"]:
            raise BusinessDataError("business_datasource_row_budget_exceeded")
        for row in rows:
            for field in ("id", "tenant_id", "dept_id", "reception_user"):
                if row[field] is not None:
                    row[field] = str(row[field])
        return rows, fingerprint({"rows": rows, "permissions": permissions})


def validate_query(query, allow_templates=False):
    if set(query) - FILTERS:
        raise BusinessDataError("yanji_reception_filter_unsupported")
    if query.get("roleId") not in (None, ""):
        raise BusinessDataError("yanji_reception_role_filter_unconfirmed")
    if not allow_templates:
        for field in ("pageNum", "pageSize"):
            try:
                value = query.get(field, 1 if field == "pageNum" else 12)
                if isinstance(value, bool) or str(int(value)) != str(value) or int(value) <= 0:
                    raise ValueError()
                if field == "pageSize" and int(value) > 1000:
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise BusinessDataError("yanji_reception_pagination_invalid") from exc
        if query.get("recordDurationStatus") not in (None, "", 0, 1, 2, "0", "1", "2"):
            raise BusinessDataError("yanji_reception_duration_invalid")
        for field in ("startDate", "endDate"):
            if query.get(field):
                try:
                    date.fromisoformat(query[field])
                except (ValueError, TypeError) as exc:
                    raise BusinessDataError("yanji_reception_date_invalid") from exc
        if query.get("startDate") and query.get("endDate"):
            if query["startDate"] > query["endDate"]:
                raise BusinessDataError("yanji_reception_date_range_invalid")
    return query


def query_for_preset(preset, rows, original):
    if preset not in PRESETS:
        raise BusinessDataError("yanji_reception_preset_unknown")
    query = {"pageNum": 1, "pageSize": 12, "recordDurationStatus": 2, **original}
    if preset in {"default", "sweep"}:
        return validate_query(query)
    if preset == "keyword_empty":
        query["keyword"] = "pyta_no_match_6e98db3e_20261027"
    elif preset in {"no_record", "short_record"}:
        query["recordDurationStatus"] = 0 if preset == "no_record" else 1
    else:
        eligible = [row for row in rows if row["record_seconds"] >= 120]
        if preset in {"customer_type", "combined"}:
            eligible = [row for row in eligible if row["customer_type"]]
        if preset in {"reception_user", "combined"}:
            eligible = [row for row in eligible if row["reception_user"]]
        if preset in {"status", "combined"}:
            eligible = [row for row in eligible if row["status"] is not None]
        if not eligible:
            raise BusinessDataError("yanji_reception_coverage_gap_no_nonempty_sample")
        selected = sorted(eligible, key=lambda row: row["id"])[0]
        if preset in {"status", "combined"}:
            query["statuses"] = str(selected["status"])
        if preset in {"customer_type", "combined"}:
            query["customerTypes"] = selected["customer_type"]
        if preset in {"reception_user", "combined"}:
            query["receptionUserIds"] = selected["reception_user"]
        if preset in {"date", "combined"}:
            day = selected["reception_time"].date().isoformat()
            query.update(startDate=day, endDate=day)
        if preset == "keyword_existing":
            query["keyword"] = selected["id"]
    return validate_query(query)


def csv_values(value):
    if value is None or value == "":
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise BusinessDataError("yanji_reception_multiselect_invalid")
    return str(value).split(",")


def expected_rows(rows, query):
    validate_query(query)
    result = []
    for row in rows:
        if query.get("keyword") and not row["keyword_hit"]:
            continue
        if any(
            csv_values(query.get(param)) is not None
            and (row[field] is None or str(row[field]) not in csv_values(query[param]))
            for param, field in (
                ("statuses", "status"),
                ("customerTypes", "customer_type"),
                ("receptionUserIds", "reception_user"),
            )
        ):
            continue
        if query.get("startDate") and row["reception_time"] < datetime.fromisoformat(
            query["startDate"]
        ):
            continue
        if query.get("endDate") and row["reception_time"] >= (
            datetime.fromisoformat(query["endDate"]) + timedelta(days=1)
        ):
            continue
        duration = query.get("recordDurationStatus")
        if duration not in (None, ""):
            duration = int(duration)
            if duration == 0 and row["record_count"] != 0:
                continue
            if duration == 1 and not (row["record_count"] > 0 and row["record_seconds"] < 120):
                continue
            if duration == 2 and row["record_seconds"] < 120:
                continue
        result.append(row)
    return sorted(result, key=lambda row: row["create_time"], reverse=True)


def compare_page(expected, body, query):
    """同时间组任意排列合法；边界组数量固定，成员可为该组任意子集。"""
    diff = {key: [] for key in EMPTY_DIFF}
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise BusinessDataError("yanji_reception_response_invalid")
    data = body["data"]
    actual_rows, total = data.get("rows"), data.get("total")
    if not isinstance(actual_rows, list) or not isinstance(total, int) or isinstance(total, bool):
        raise BusinessDataError("yanji_reception_response_invalid")
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("id"), (str, int))
        or isinstance(row["id"], bool)
        for row in actual_rows
    ):
        raise BusinessDataError("yanji_reception_response_invalid")
    actual = [str(row["id"]) for row in actual_rows]
    counts = Counter(actual)
    diff["duplicate_ids"] = sorted(key for key, count in counts.items() if count > 1)
    if total != len(expected):
        diff["problems"].append(f"total: expected={len(expected)} actual={total}")
    start = (int(query.get("pageNum", 1)) - 1) * int(query.get("pageSize", 12))
    end = min(len(expected), start + int(query.get("pageSize", 12)))
    wanted_count = max(0, end - start)
    if len(actual) != wanted_count:
        diff["problems"].append(f"page_length: expected={wanted_count} actual={len(actual)}")
    allowed, required, ranks, group_index = set(), set(), {}, 0
    offset = 0
    for _, group in groupby(expected, key=lambda row: row["create_time"]):
        ids = [row["id"] for row in group]
        group_end = offset + len(ids)
        overlap = max(0, min(end, group_end) - max(start, offset))
        if overlap:
            allowed.update(ids)
            if overlap == len(ids):
                required.update(ids)
            received = sum(counts[key] for key in ids)
            if received != overlap:
                diff["problems"].append(
                    f"time_group_{group_index}: expected={overlap} actual={received}"
                )
        ranks.update({identifier: group_index for identifier in ids})
        group_index += 1
        offset = group_end
    diff["missing_ids"] = sorted(required - set(actual))
    diff["extra_ids"] = sorted(set(actual) - allowed)
    ordering = [ranks[identifier] for identifier in actual if identifier in ranks]
    if ordering != sorted(ordering):
        diff["problems"].append("create_time_order_invalid")
    # 若接口提供项目字段也校验；ID集合本身已来自固定项目，不要求API新增字段。
    return diff, actual
