"""旧 worker 导入兼容；正式入口为 workers.run_worker.RunWorker。"""

from pyta_platform_backend.workers.run_worker import RunWorker, WorkerExecutionResult

# 保持旧导入的类身份，不复制执行实现。
MemoryWorkerRunner = RunWorker

__all__ = ["MemoryWorkerRunner", "RunWorker", "WorkerExecutionResult"]
