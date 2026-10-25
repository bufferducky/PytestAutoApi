"""HTTP 控制只唤醒后台执行，不在请求内消费长任务。"""

from pyta_platform_backend.schemas.run import RunStatus
from pyta_platform_backend.schemas.worker import RunNextResponse


class WorkerControlService:
    def __init__(self, worker_runner, run_service, worker_host=None):
        self._worker_runner = worker_runner
        self._run_service = run_service
        self._worker_host = worker_host

    def run_next(self):
        records = self._run_service.repository.list_queued_records()
        if not records:
            return RunNextResponse(consumed=False, detail=None)
        return RunNextResponse(consumed=False, detail=self.run_by_id(records[0].run_id))

    def run_by_id(self, run_id):
        detail = self._run_service.ensure_resumable(run_id)
        if detail.status == RunStatus.QUEUED:
            self._run_service.dispatcher.prioritize(run_id)
            if self._worker_host:
                self._worker_host.wake()
        if detail.status == RunStatus.QUEUED and (
            self._worker_host is None or not self._worker_host.available
        ):
            detail.status_message = "worker 未启动；任务保留在 queued，没有同步执行兜底"
        return detail

    def status(self):
        return {
            "available": bool(self._worker_host and self._worker_host.available),
            "last_error": self._worker_host.last_error if self._worker_host else None,
            "queued": len(self._run_service.repository.list_queued_records()),
        }
