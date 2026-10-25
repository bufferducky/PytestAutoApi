from fastapi import APIRouter, HTTPException


def create_evaluations_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["evaluations"])

    @router.get("/evaluation-datasets")
    def datasets():
        return service.repository.definitions("datasets")

    @router.post("/evaluation-datasets", status_code=201)
    def dataset(payload: dict):
        return service.dataset(payload)

    @router.post("/evaluation-datasets/seed-local", status_code=201)
    def seed():
        return service.seed()

    @router.get("/rubrics")
    def rubrics():
        return service.repository.definitions("rubrics")

    @router.post("/rubrics", status_code=201)
    def rubric(payload: dict):
        return service.rubric(payload)

    @router.post("/evaluation-runs", status_code=202)
    def run(payload: dict):
        try:
            return service.run(payload)
        except KeyError as exc:
            raise HTTPException(400, "缺少dataset/rubric版本引用") from exc

    @router.get("/evaluation-runs/{run_id}")
    def report(run_id: str):
        return service.report(run_id)

    @router.get("/evaluation-runs/{run_id}/comparison")
    def comparison(run_id: str, other_run_id: str):
        return service.compare(run_id, other_run_id)

    @router.post("/evaluation-runs/{run_id}/samples/{sample_id}/reviews", status_code=201)
    def review(run_id: str, sample_id: str, payload: dict):
        return service.review(run_id, sample_id, payload)

    @router.post("/evaluation-datasets/{identifier}/versions/{version}/revoke")
    def revoke(identifier: str, version: int, payload: dict):
        return service.revoke(identifier, version, payload.get("reason"))

    @router.post("/rubrics/{identifier}/versions/{version}/calibration-preview")
    def calibration_preview(identifier: str, version: int, payload: dict):
        return service.calibration_preview(identifier, version, payload)

    @router.post("/rubrics/{identifier}/versions/{version}/approve-calibration", status_code=201)
    def approve_calibration(identifier: str, version: int, payload: dict):
        return service.approve_calibration(identifier, version, payload)

    return router
