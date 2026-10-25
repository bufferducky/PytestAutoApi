"""默认无发送器；只有显式本地配置授权的sender才能外发，故障不改变业务结果。"""

from pyta_platform_backend.repositories.asset_repository import asset_hash
from pyta_platform_backend.services.redaction import Redactor


class NotificationService:
    def __init__(self, repository):
        self.repository = repository
        self.channels = {}

    def register_authorized_sender(self, channel, sender, *, authorized=False):
        if not authorized or not callable(sender):
            raise ValueError("必须显式授权接收通道和发送器")
        self.channels[channel] = sender

    def notify(self, channel, state, summary, *, stream=None, fingerprint_summary=None):
        sender = self.channels.get(channel)
        if sender is None:
            return {"sent": False, "reason": "disabled_or_not_authorized"}
        public = Redactor().clean(summary)
        basis = Redactor().clean(fingerprint_summary) if fingerprint_summary is not None else public
        fingerprint = asset_hash({"state": state, "summary": basis})
        state_key = channel if stream is None else channel + ":" + asset_hash(stream)
        previous = self.repository.notification(state_key)
        if previous and previous.get("fingerprint") == fingerprint and previous.get("delivered"):
            return {"sent": False, "reason": "unchanged"}
        if state == "succeeded" and (previous is None or previous.get("state") == "succeeded"):
            return {"sent": False, "reason": "healthy_unchanged"}
        attempts = (
            previous.get("attempts", 0) + 1
            if previous and previous.get("fingerprint") == fingerprint
            else 1
        )
        if attempts > 3:
            return {"sent": False, "reason": "delivery_retry_limit", "pending": True}
        record = {
            "stream": stream,
            "run_id": public.get("run_id") if isinstance(public, dict) else None,
            "state": state,
            "fingerprint": fingerprint,
            "attempts": attempts,
            "delivered": False,
        }
        try:
            sender({"state": state, "summary": public})
            record["delivered"] = True
        except Exception:
            record["error"] = "notification_delivery_failed"
        self.repository.save_notification(state_key, record)
        return {"sent": record["delivered"], "pending": not record["delivered"]}

    def notify_finished(self, detail):
        if detail.status.value in {"queued", "running", "cancelled", "skipped"}:
            return []
        contexts = detail.payload.get("context_snapshots", {})
        stream = {
            "suite_id": detail.suite_id,
            "environment_id": detail.environment_id,
            "transport_mode": detail.transport_mode,
            "execution_mode": detail.execution_mode,
            "targets": sorted({snapshot["target"]["id"] for snapshot in contexts.values()}),
        }
        state = detail.status.value
        if state == "succeeded" and detail.cleanup_status != "succeeded":
            state = "needs_action"
        stable = {
            **stream,
            "asset_ref": detail.payload.get("asset_ref"),
            "state": state,
            "cleanup_status": detail.cleanup_status,
            "failures": [
                {
                    "case_id": case["case_id"],
                    "status": case["status"],
                    "error_types": [step.get("error_type") for step in case.get("steps", [])],
                    "assertions": [
                        {
                            "name": a["name"],
                            "status": a["status"],
                            "source_ref": a.get("source_ref"),
                        }
                        for step in case.get("steps", [])
                        for a in step.get("assertions", [])
                        if a["status"] != "passed"
                    ],
                }
                for case in detail.results
                if case["status"] not in {"passed", "skipped"}
            ],
        }
        summary = {
            **stable,
            "run_id": detail.run_id,
            "validation_scope": detail.validation_scope,
            "counts": detail.counts,
            "eligible_for_release": detail.eligible_for_release,
        }
        outcomes = []
        for channel in list(self.channels):
            try:
                outcomes.append(
                    {
                        "channel": channel,
                        **self.notify(
                            channel, state, summary, stream=stream, fingerprint_summary=stable
                        ),
                    }
                )
            except Exception:
                # 持久化/通道故障与执行结果分开；不因通知异常重新执行业务。
                outcomes.append(
                    {
                        "channel": channel,
                        "sent": False,
                        "pending": True,
                        "reason": "notification_state_unavailable",
                    }
                )
        return outcomes
