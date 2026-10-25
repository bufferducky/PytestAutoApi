"""worker 投递边界。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Optional


@dataclass(frozen=True)
class DispatchTask:
    """发给 worker 的任务载荷。"""

    run_id: str
    suite_id: str
    trigger_source: str
    requested_by: str
    payload: dict[str, object]
    dispatched_at: datetime


class MemoryRunDispatcher:
    """内存版 dispatcher。

    第一阶段不上重队列，所以这里先保留一个轻量投递器边界。
    真实接入轻量 worker、消息通道或进程池时，只需要替换这个实现。
    """

    def __init__(self, channel_name: str = "memory-worker") -> None:
        self._lock = RLock()
        self.channel_name = channel_name
        self.dispatched_tasks: list[DispatchTask] = []

    def dispatch(self, task: DispatchTask) -> None:
        """记录一次任务投递。"""

        with self._lock:
            self.dispatched_tasks.append(
                DispatchTask(
                    run_id=task.run_id,
                    suite_id=task.suite_id,
                    trigger_source=task.trigger_source,
                    requested_by=task.requested_by,
                    payload=deepcopy(task.payload),
                    dispatched_at=task.dispatched_at,
                )
            )

    def pull_next(self) -> Optional[DispatchTask]:
        """按先进先出顺序取出一个待执行任务。

        第一阶段先用最简单的内存队列表达 worker 边界：
        - dispatcher 负责排队
        - worker 负责取任务并执行
        """

        with self._lock:
            if not self.dispatched_tasks:
                return None
            return self.dispatched_tasks.pop(0)

    def pull_by_run_id(self, run_id: str) -> Optional[DispatchTask]:
        """按 run_id 取出指定任务，同时保留其他任务的相对顺序。

        单人工作台的一键运行需要“点哪个跑哪个”，
        不能因为队列里已有旧任务就把这次点击的目标跑偏。
        """

        with self._lock:
            for index, task in enumerate(self.dispatched_tasks):
                if task.run_id == run_id:
                    return self.dispatched_tasks.pop(index)
            return None

    def prioritize(self, run_id):
        with self._lock:
            task = self.pull_by_run_id(run_id)
            if task:
                self.dispatched_tasks.insert(0, task)


class PersistentRunDispatcher:
    """outbox 与 run 同事务落盘；投递仅唤醒，领取不改变业务执行事实。"""

    def __init__(self, repository):
        from uuid import uuid4

        self.repository = repository
        self.store = repository._connection
        self.channel_name = "mysql-outbox"
        self.owner = uuid4().hex

    @staticmethod
    def _task(record):
        return DispatchTask(
            run_id=record.run_id,
            suite_id=record.suite_id,
            trigger_source=record.trigger_source,
            requested_by=record.requested_by,
            payload=deepcopy(record.payload),
            dispatched_at=record.created_at,
        )

    @property
    def dispatched_tasks(self):
        return [self._task(record) for record in self.repository.list_queued_records()]

    def dispatch(self, task):
        # run 的创建已原子写入 outbox；不能用这里的未脱敏 payload 替换数据库快照。
        if self.repository.get_by_id(task.run_id) is None:
            raise ValueError("任务必须先持久化")

    def _pull(self, run_id=None):
        from datetime import timedelta, timezone

        now = datetime.now(timezone.utc)
        # Keep the same repository -> Store lock order as claim/finish.
        with self.repository._transaction():
            row = self.store.execute(
                "SELECT run_id FROM run_outbox WHERE state='pending'"
                + (" AND run_id=?" if run_id else "")
                + " ORDER BY priority DESC,created_at,run_id LIMIT 1",
                (run_id,) if run_id else (),
            ).fetchone()
            if row is None:
                return None
            record = self.repository.get_by_id(row["run_id"])
            if (
                record is None
                or record.status.value != "queued"
                or record.execution.get("migration", {}).get("do_not_resume")
            ):
                self.store.execute(
                    "UPDATE run_outbox SET state='done' WHERE run_id=?",
                    (row["run_id"],),
                )
                return None
            self.store.execute(
                "UPDATE run_outbox SET state='leased',owner=?,attempt=attempt+1,lease_until=? "
                "WHERE run_id=? AND state='pending'",
                (self.owner, (now + timedelta(seconds=300)).isoformat(), record.run_id),
            )
            return self._task(record)

    def pull_next(self):
        return self._pull()

    def pull_by_run_id(self, run_id):
        return self._pull(run_id)

    def prioritize(self, run_id):
        # Keep the same repository -> Store lock order as claim/finish.
        with self.repository._transaction():
            self.store.execute(
                "UPDATE run_outbox SET priority=priority+1 WHERE run_id=? AND state='pending'",
                (run_id,),
            )

    def recover(self):
        # 持有全局 worker 锁后，queued 的领取尚未开始业务 I/O，可恢复。
        # running 先由仓储置 interrupted；对外部请求绝不自动重试。
        # Keep the same repository -> Store lock order as claim/finish.
        with self.repository._transaction():
            for record in self.repository.list_queued_records():
                self.store.execute(
                    "UPDATE run_outbox SET state='pending',owner=NULL,lease_until=NULL "
                    "WHERE run_id=?",
                    (record.run_id,),
                )
