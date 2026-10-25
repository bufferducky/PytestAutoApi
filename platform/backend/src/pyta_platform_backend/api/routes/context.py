"""上下文配置与受控登录预检。"""

from fastapi import APIRouter, HTTPException

from pyta_platform_backend.schemas.context import (
    ContextBinding,
    IdentityProfile,
    PreflightRequest,
    TargetProfile,
)


def create_context_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["context"])

    def register(kind, model):
        # 使用工厂固定 kind/model，避免循环闭包把三组接口都指向最后一组。
        def list_profiles():
            return service.list(kind)

        def create_profile(payload: model):
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            return service.save(kind, data, creating=True)

        def update_profile(identifier: str, payload: model):
            if payload.id != identifier:
                raise HTTPException(400, "路径与配置 ID 不一致")
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            return service.save(kind, data)

        def delete_profile(identifier: str, revision: int):
            return service.delete(kind, identifier, revision)

        router.get("/" + kind)(list_profiles)
        router.post("/" + kind, status_code=201)(create_profile)
        router.patch("/" + kind + "/{identifier}")(update_profile)
        router.delete("/" + kind + "/{identifier}")(delete_profile)

    register("targets", TargetProfile)
    register("identity-profiles", IdentityProfile)
    register("context-bindings", ContextBinding)

    @router.post("/environments/{environment_id}/preflight")
    def preflight(environment_id: str, payload: PreflightRequest):
        return service.preflight(environment_id, payload)

    return router
