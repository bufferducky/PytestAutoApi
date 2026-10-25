"""只读诊断、受控附件与显式保留操作。"""

from fastapi import APIRouter


def create_diagnostics_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["diagnostics"])

    @router.get("/runs/{run_id}/diagnostics")
    def diagnostic(run_id: str):
        return service.overview(run_id)

    @router.get("/runs/{run_id}/comparison")
    def comparison(run_id: str, other_run_id: str):
        return service.compare(run_id, other_run_id)

    @router.get("/runs/{run_id}/diagnostic-export")
    def export(run_id: str):
        return service.overview(run_id)

    @router.get("/runs/{run_id}/steps")
    def steps(run_id: str, offset: int = 0, limit: int = 20):
        return service.overview(run_id)["timeline"][
            max(0, offset) : max(0, offset) + min(200, max(1, limit))
        ]

    @router.post("/runs/{run_id}/artifacts", status_code=201)
    def add_artifact(run_id: str, payload: dict):
        return service.add_artifact(run_id, payload)

    @router.get("/runs/{run_id}/artifacts")
    def artifacts(run_id: str):
        service.runs.get_run_detail(run_id)
        return service.artifacts.list(run_id)

    @router.get("/artifacts/{artifact_id}")
    def artifact(artifact_id: str, run_id: str = None):
        return service.artifact(artifact_id, run_id)

    @router.get("/artifacts/{artifact_id}/content")
    def content(artifact_id: str, run_id: str = None):
        from fastapi import Response

        meta, data = service.artifact(artifact_id, run_id, download=True)
        return Response(
            content=data,
            media_type=meta["content_type"],
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @router.post("/artifacts/{artifact_id}/pin")
    def pin(artifact_id: str, payload: dict):
        return service.pin(artifact_id, payload.get("pinned"))

    @router.get("/artifact-retention/preview")
    def retention_preview():
        return service.retention_preview()

    @router.post("/artifact-retention/apply")
    def retention_apply(payload: dict):
        return service.retention_apply(payload.get("artifact_ids", []), payload.get("run_ids", []))

    @router.post("/runs/{run_id}/diagnostic-timing")
    def timing(run_id: str, payload: dict):
        return service.timing(run_id, payload)

    @router.get("/run-trends")
    def trends(
        environment_id: str = None,
        transport_mode: str = None,
        scenario_id: str = None,
        scenario_version: int = None,
    ):
        return service.trends(environment_id, transport_mode, scenario_id, scenario_version)

    @router.get("/artifact-retention/policy")
    def policy():
        return service.artifacts.policy()

    @router.patch("/artifact-retention/policy")
    def update_policy(payload: dict):
        from fastapi import HTTPException

        try:
            return service.artifacts.set_policy(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
