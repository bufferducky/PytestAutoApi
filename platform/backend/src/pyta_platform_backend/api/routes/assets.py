"""资产编辑、发布、预览、运行及覆盖；没有自动执行新发现端点的入口。"""

from fastapi import APIRouter, HTTPException

from pyta_platform_backend.schemas.assets import AssetRunRequest, PublishRequest, SaveDraftRequest


def create_assets_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["assets"])

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

    @router.post("/imports/legacy", status_code=201)
    def import_legacy(payload: dict):
        return service.import_legacy(payload["path"], payload["target_ref"])

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
