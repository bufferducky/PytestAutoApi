"""资产编辑、发布、预览、运行及覆盖；没有自动执行新发现端点的入口。"""

from fastapi import APIRouter, HTTPException

from pyta_platform_backend.schemas.assets import (
    AssetRunRequest,
    DraftDebugRequest,
    PublishRequest,
    SaveDraftRequest,
)


def create_assets_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["assets"])

    @router.post("/scenarios/debug", status_code=202)
    def debug_draft(payload: DraftDebugRequest):
        return service.debug(payload)

    def register(kind):
        def list_assets(offset: int = 0, limit: int = 100):
            return service.list(kind, offset, limit)

        def create_asset(payload: dict):
            return service.create(kind, payload)

        def detail(identifier: str):
            return service.get(kind, identifier)

        def update(identifier: str, payload: SaveDraftRequest):
            return service.update(kind, identifier, payload.expected_revision, payload.draft)

        def archive(identifier: str, revision: int):
            data = service.get(kind, identifier)["draft"]
            return service.update(kind, identifier, revision, data, archive=True)

        def copy(identifier: str):
            data = service.get(kind, identifier)["draft"]
            return service.create(kind, {**data, "name": data["name"] + "（副本）"})

        def preview(identifier: str):
            return service.preview(kind, identifier)

        def publish(identifier: str, payload: PublishRequest):
            return service.publish(kind, identifier, payload)

        def versions(identifier: str):
            return service.repository.versions(kind, identifier)

        def export(identifier: str, version: int):
            return service.export(kind, identifier, version)

        def plan(identifier: str, version: int, payload: AssetRunRequest):
            try:
                return service.plan(kind, identifier, version, payload)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

        def run(identifier: str, version: int, payload: AssetRunRequest):
            try:
                return service.run(kind, identifier, version, payload)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

        # 既有 /suites GET 是兼容目录；新版本资产目录使用 /suite-assets，
        # /suites/{id}/versions/... 仍与正式发布路径对齐。
        root = "/suite-assets" if kind == "suites" else "/scenarios"
        route = "/" + kind
        router.get(root)(list_assets)
        router.post(root, status_code=201)(create_asset)
        router.get(route + "/{identifier}/draft")(detail)
        router.patch(route + "/{identifier}/draft")(update)
        router.post(route + "/{identifier}/archive")(archive)
        router.post(route + "/{identifier}/copy", status_code=201)(copy)
        router.post(route + "/{identifier}/preflight")(preview)
        router.post(route + "/{identifier}/publish", status_code=201)(publish)
        router.get(route + "/{identifier}/versions")(versions)
        router.get(route + "/{identifier}/versions/{version}/export")(export)
        router.post(route + "/{identifier}/versions/{version}/plan")(plan)
        router.post(route + "/{identifier}/versions/{version}/runs", status_code=202)(run)

    register("scenarios")
    register("suites")

    @router.post("/imports/standard", status_code=201)
    def import_standard(payload: dict):
        return service.import_standard(payload)

    @router.post("/imports/yanji-query", status_code=201)
    def import_yanji_query(payload: dict):
        from pyta_platform_backend.integrations.yanji.query_pack import import_query_pack

        return import_query_pack(service, payload)

    @router.get("/business-datasources")
    def business_datasources():
        from pyta_platform_backend.services.business_datasources import public_sources

        try:
            return public_sources()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/business-datasources/{identifier}/preflight")
    def business_datasource_preflight(identifier: str, payload: dict):
        from pyta_platform_backend.services.business_datasources import preflight_source

        if not isinstance(payload.get("execute_query", False), bool):
            raise HTTPException(400, "execute_query必须是布尔值")
        try:
            snapshot = service.context.snapshot(
                payload.get("target_ref"), payload.get("identity_ref"), payload.get("binding_ref")
            )
            return preflight_source(
                identifier,
                snapshot,
                payload.get("expected_user_id"),
                payload.get("execute_query", False),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/imports/yanji-reception", status_code=201)
    def import_yanji_reception(payload: dict):
        from pyta_platform_backend.integrations.yanji.reception_pack import import_reception_pack

        return import_reception_pack(service, payload)

    @router.get("/regression-packs/yanji")
    def yanji_contracts():
        import json
        from importlib.resources import files

        try:
            return json.loads(
                files("pyta_platform_backend.integrations.yanji.data")
                .joinpath("yanji-contracts.json")
                .read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "yanji_contract_bundle_unavailable") from exc

    @router.post("/imports/legacy", status_code=201)
    def import_legacy(payload: dict):
        if not payload.get("target_ref"):
            raise HTTPException(400, "请选择导入场景的目标系统")
        if not payload.get("path") and "yaml_text" not in payload:
            raise HTTPException(400, "请上传 YAML 内容或提供旧路径")
        return service.import_legacy(
            payload.get("path", "uploaded.yaml"), payload["target_ref"], payload.get("yaml_text")
        )

    @router.post("/imports/demo", status_code=201)
    def import_demo(payload: dict):
        return service.import_demo(payload.get("suite_id"), payload.get("target_ref"))

    @router.post("/coverage-items/import-research")
    def import_research():
        return service.import_research()

    @router.get("/coverage-items")
    def coverage(offset: int = 0, limit: int = 100):
        return service.repository.coverage()[
            max(0, offset) : max(0, offset) + min(200, max(1, limit))
        ]

    @router.patch("/coverage-items/{identifier}")
    def update_coverage(identifier: str, payload: dict):
        return service.update_coverage(identifier, payload["expected_revision"], payload["changes"])

    @router.get("/coverage-summary")
    def summary(freshness_days: int = 7):
        return service.coverage_summary(freshness_days)

    return router
