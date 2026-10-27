"""数据库期望接入现有HTTP步骤；分页展开仍逐请求记录到原引擎。"""

import math
from collections import Counter
from copy import deepcopy

from pyta_platform_backend.integrations.yanji.reception_oracle import (
    CONTRACT,
    EMPTY_DIFF,
    compare_page,
    expected_rows,
    query_for_preset,
    read_facts,
)
from pyta_platform_backend.services.business_datasources import (
    BusinessDataError,
    resolve_source,
)
from testflow_engine import EnginePlugin


class BusinessDatabasePlugin(EnginePlugin):
    name = "business-database"

    def __init__(self, plan, snapshots, *, deadline, should_stop=None, redactor=None):
        self.plan, self.snapshots = plan, snapshots
        self.deadline, self.should_stop, self.redactor = deadline, should_stop, redactor
        self.pending, self.sweeps = {}, {}

    def source(self, case):
        check = case.metadata.get("database_check")
        if not check:
            return None
        if check.get("contract_ref") != CONTRACT:
            raise BusinessDataError("business_database_contract_unknown")
        key = case.metadata.get("context_binding_id")
        snapshot = self.snapshots.get(key)
        if not snapshot:
            raise BusinessDataError("business_database_context_missing")
        source = resolve_source(check["datasource_ref"], snapshot)
        if self.plan.get(case.metadata.get("scope_id")) != source:
            raise BusinessDataError("business_datasource_configuration_drift")
        if (
            case.request.method.value != "GET"
            or case.request.url != "{{host}}/api/v1/reception_form/page"
        ):
            raise BusinessDataError("business_database_request_invalid")
        return source

    def facts(self, source, check, keyword=""):
        return read_facts(
            source,
            check["expected_user_id"],
            keyword,
            deadline=self.deadline,
            should_stop=self.should_stop,
            remember_secret=self.redactor._collect if self.redactor else None,
        )

    def prepare(self, definition):
        expanded, expanded_dependencies = [], {}
        for case in definition.cases:
            check = case.metadata.get("database_check")
            if not case.enabled or not check:
                expanded.append(case)
                continue
            source = self.source(case)
            if not check.get("sweep"):
                expanded.append(case)
                continue
            rows, stamp = self.facts(source, check)
            query = query_for_preset("sweep", rows, case.request.query)
            if query.get("keyword"):
                rows, stamp = self.facts(source, check, query["keyword"])
            wanted = expected_rows(rows, query)
            pages = max(1, math.ceil(len(wanted) / int(query["pageSize"])))
            if pages > 100:
                raise BusinessDataError("yanji_reception_page_budget_exceeded")
            group = case.case_id
            self.sweeps[group] = {"fingerprint": stamp, "seen": [], "expected": wanted}
            for page in range(1, pages + 1):
                item = deepcopy(case)
                item.case_id += "__page_" + str(page)
                item.title += " · 第" + str(page) + "页"
                item.metadata["step_id"] += "__page_" + str(page)
                item.metadata["sweep_group"] = group
                item.metadata["sweep_last"] = page == pages
                item.metadata["expanded_page_count"] = pages
                if page > 1:
                    item.depends_on.append(group + "__page_" + str(page - 1))
                item.request.query = {**query, "pageNum": page}
                expanded.append(item)
            expanded_dependencies[group] = group + "__page_" + str(pages)
        # 下游依赖的是整个分页步骤，展开后必须等待最后一页核验通过。
        for case in expanded + definition.cleanup_cases:
            case.depends_on = [expanded_dependencies.get(dep, dep) for dep in case.depends_on]
        definition.cases = expanded

    def before_case(self, case, context):
        check = case.metadata.get("database_check")
        if not check:
            return
        source = self.source(case)
        rows, stamp = self.facts(source, check)
        query = query_for_preset(check.get("filter_preset", "default"), rows, case.request.query)
        if query.get("keyword"):
            rows, stamp = self.facts(source, check, query["keyword"])
        if case.metadata.get("sweep_group"):
            if self.sweeps[case.metadata["sweep_group"]]["fingerprint"] != stamp:
                raise BusinessDataError("yanji_reception_data_changed")
        case.request.query = query
        wanted = expected_rows(rows, query)
        self.pending[case.case_id] = (source, query, wanted, stamp)
        context.variables.setdefault("runtime", {})["database_diff"] = deepcopy(EMPTY_DIFF)

    def after_response(self, case, response, context):
        check = case.metadata.get("database_check")
        if not check:
            if case.metadata.get("yanji_identity") and isinstance(response.body, dict):
                data = response.body.get("data") or {}
                response.body = {
                    "code": response.body.get("code"),
                    "data": {
                        key: data[key] for key in ("userId", "tenantId", "deptId") if key in data
                    },
                }
            return
        try:
            source, query, wanted, before = self.pending.pop(case.case_id)
            _, after = self.facts(source, check, query.get("keyword", ""))
            if before != after:
                raise BusinessDataError("yanji_reception_data_changed")
            diff, actual = compare_page(wanted, response.body, query)
            group = case.metadata.get("sweep_group")
            if group:
                sweep = self.sweeps[group]
                if after != sweep["fingerprint"]:
                    raise BusinessDataError("yanji_reception_data_changed")
                sweep["seen"].extend(actual)
                if case.metadata["sweep_last"]:
                    expected_counts = Counter(row["id"] for row in sweep["expected"])
                    actual_counts = Counter(sweep["seen"])
                    diff["missing_ids"] += sorted((expected_counts - actual_counts).elements())
                    diff["extra_ids"] += sorted((actual_counts - expected_counts).elements())
                    diff["duplicate_ids"] += sorted(
                        key for key, count in actual_counts.items() if count > 1
                    )
            context.variables["runtime"]["database_diff"] = diff
            context.variables["runtime"]["database_evidence"] = {
                "contract_ref": CONTRACT,
                "datasource_hash": source["hash"],
                "expected_total": len(wanted),
                "actual_total": response.body["data"]["total"],
                "snapshot_fingerprint": before,
            }
        except BusinessDataError as exc:
            exc.request_sent = True
            raise
        finally:
            # 结果只需ID/数量；即使DB出错，也不把客户姓名/手机/画像落库。
            body = response.body if isinstance(response.body, dict) else {}
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            response.body = {
                "code": body.get("code"),
                "data": {
                    "total": data.get("total"),
                    "rows": [{"id": row.get("id")} for row in rows if isinstance(row, dict)],
                },
            }

    def after_case(self, case, result, context):
        if case.metadata.get("database_check"):
            evidence = context.variables.get("runtime", {}).get("database_evidence")
            if evidence:
                result.metadata["database_evidence"] = evidence
            for step in result.steps:
                for assertion in step.assertions:
                    if assertion.name == "数据库接诊集合与分页":
                        assertion.rule_version = CONTRACT
                        assertion.source_ref = (
                            "business-datasource:"
                            + case.metadata["database_check"]["datasource_ref"]
                        )
