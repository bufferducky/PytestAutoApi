"""应用生命周期内的单执行槽；文件锁拒绝同一状态库的双实例消费。"""

import fcntl
import hashlib
from pathlib import Path
from threading import Event, Thread


class WorkerHost:
    def __init__(self, runner, repository, database_path):
        self.runner, self.repository = runner, repository
        self.database_path = database_path
        self._stop, self._wake = Event(), Event()
        self._thread, self._guard = None, None
        self.last_error = None
        self.last_heartbeat = None
        self.recovery_callback = None
        self.on_run_finished = None
        self.notification_error = None
        self._mysql_guard = None

    @property
    def available(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self):
        if self._thread is not None:
            raise RuntimeError("worker 已启动")
        if str(self.database_path).startswith("mysql"):
            from sqlalchemy import text

            from pyta_platform_backend.db.store import engine_for

            self._mysql_guard = engine_for(self.database_path).connect()
            database = self._mysql_guard.engine.url.database
            self._mysql_lock_name = "pyta-worker:" + database
            # MySQL permits 64-character database names, but GET_LOCK names also
            # have a 64-character limit including our namespace prefix.
            if len(self._mysql_lock_name) > 64:
                self._mysql_lock_name = "pyta-worker:" + hashlib.sha256(
                    database.encode()
                ).hexdigest()[:52]
            acquired = self._mysql_guard.execute(
                text("SELECT GET_LOCK(:name, 0)"),
                {"name": self._mysql_lock_name},
            ).scalar()
            if acquired != 1:
                self._mysql_guard.close()
                self._mysql_guard = None
                raise RuntimeError("该 MySQL 数据库已有 worker；只支持单实例")
        elif self.database_path != ":memory:":
            path = Path(self.database_path).expanduser().resolve()
            self._guard = open(str(path) + ".worker.lock", "a")
            try:
                fcntl.flock(self._guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self._guard.close()
                self._guard = None
                raise RuntimeError("该状态库已有 worker；只支持单实例") from exc
        try:
            self.repository.recover_interrupted()
            if self.recovery_callback:
                self.recovery_callback()
            self._thread = Thread(target=self._loop, name="testflow-worker", daemon=True)
            self._thread.start()
        except BaseException:
            self._release_guard()
            raise

    def _loop(self):
        try:
            while not self._stop.is_set():
                from datetime import datetime, timezone

                self.last_heartbeat = datetime.now(timezone.utc).isoformat()
                try:
                    if self._mysql_guard is not None:
                        from sqlalchemy import text

                        held = self._mysql_guard.execute(
                            text("SELECT IS_USED_LOCK(:name)=CONNECTION_ID()"),
                            {"name": self._mysql_lock_name},
                        ).scalar()
                        if held != 1:
                            raise RuntimeError("worker 数据库锁丢失，停止消费")
                    detail = self.runner.run_next()
                    if detail is not None:
                        if self.on_run_finished:
                            try:
                                deliveries = self.on_run_finished(detail)
                                self.notification_error = (
                                    "notification_delivery_pending"
                                    if isinstance(deliveries, list)
                                    and any(item.get("pending") for item in deliveries)
                                    else None
                                )
                            except Exception as exc:
                                self.notification_error = type(exc).__name__
                        continue
                except Exception as exc:
                    # 存储故障不假报成功；当前 running 交启动对账处理，不盲重试。
                    self.last_error = type(exc).__name__
                    if self._mysql_guard is not None:
                        # 连接故障不能悄悄重建一个已不持锁的消费者。
                        self._stop.set()
                self._wake.wait(0.1)
                self._wake.clear()
        finally:
            self._release_guard()

    def _release_guard(self):
        if self._mysql_guard is not None:
            try:
                from sqlalchemy import text

                self._mysql_guard.execute(
                    text("SELECT RELEASE_LOCK(:name)"),
                    {"name": self._mysql_lock_name},
                )
            finally:
                self._mysql_guard.close()
                self._mysql_guard = None
        if self._guard:
            self._guard.close()
            self._guard = None

    def wake(self):
        self._wake.set()

    def stop(self):
        self._stop.set()
        for record in self.repository.list_running_records():
            if record.status.value == "running":
                self.repository.cancel(record.run_id)
        self._wake.set()
        if self._thread:
            # 当前 I/O 只能在请求超时边界退出；不在 API 线程无限等待。
            self._thread.join(timeout=5)
