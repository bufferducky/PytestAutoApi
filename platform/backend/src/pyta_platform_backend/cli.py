"""统一CI入口；只复用平台API，不在CLI再造执行器。"""

import argparse
import json
import sys
import time
from urllib.parse import quote

import httpx


def result_code(data):
    status = data.get("status")
    if status == "failed":
        return 1
    if status in {"error", "interrupted", "timed_out"}:
        return 2
    if status != "succeeded" or not data.get("eligible_for_release"):
        return 3
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PytestAutoApi CI：0通过，1业务失败，2执行错误，3阻塞/未验证"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    sub = parser.add_subparsers(dest="command", required=True)
    for action in ["get", "wait", "cancel", "export"]:
        cmd = sub.add_parser(action)
        cmd.add_argument("run_id")
        if action == "wait":
            cmd.add_argument("--timeout", type=float, default=300)
    submit = sub.add_parser("submit")
    submit.add_argument("suite_id")
    submit.add_argument("version", type=int)
    submit.add_argument("--mode", choices=["live"], default="live")
    submit.add_argument("--environment-id")
    submit.add_argument("--request-file", help="只含公开参数的JSON；不要放凭证明文")
    submit.add_argument("--build", default="unspecified")
    submit.add_argument("--wait", action="store_true")
    submit.add_argument("--timeout", type=float, default=300)
    release = sub.add_parser("release")
    release.add_argument("run_ids", nargs="+")
    release.add_argument("--mode", choices=["report_only", "strict"], default="report_only")
    release.add_argument("--build", default="unspecified")
    args = parser.parse_args(argv)
    run_id = getattr(args, "run_id", None)

    def emit(value):
        print(json.dumps(value, ensure_ascii=False, default=str))

    with httpx.Client(
        base_url=args.base_url.rstrip("/") + "/", timeout=10, follow_redirects=False
    ) as client:
        try:
            if args.command == "submit":
                data = {}
                if args.request_file:
                    from pathlib import Path

                    path = Path(args.request_file)
                    if path.stat().st_size > 1024 * 1024:
                        raise ValueError("请求文件过大")
                    data = json.loads(path.read_text())
                data.update(
                    transport_mode=args.mode, environment_id=args.environment_id, build=args.build
                )
                response = client.post(
                    f"suites/{quote(args.suite_id, safe='')}/versions/{args.version}/runs",
                    json=data,
                )
                response.raise_for_status()
                run_id = response.json()["run_id"]
                emit({"run_id": run_id, "url": args.base_url.rstrip("/") + "/runs/" + run_id})
                if not args.wait:
                    return 3  # 已受理不等于业务通过。
            if args.command == "cancel":
                response = client.post("runs/" + quote(run_id, safe="") + "/cancel")
                response.raise_for_status()
                emit(response.json())
                return 3
            if args.command == "release":
                response = client.post(
                    "release-reports",
                    json={"run_ids": args.run_ids, "mode": args.mode, "build": args.build},
                )
                response.raise_for_status()
                data = response.json()
                emit(data)
                return data["exit_code"]
            if args.command == "export":
                response = client.get("runs/" + quote(run_id, safe="") + "/diagnostic-export")
                response.raise_for_status()
                emit(response.json())
                return 3
            waiting = args.command == "wait" or args.command == "submit" and args.wait
            if waiting and (args.timeout <= 0 or not args.timeout < 86401):
                raise ValueError("timeout必须在(0,86400]")
            deadline = time.monotonic() + (args.timeout if waiting else 0)
            while True:
                response = client.get("runs/" + quote(run_id, safe=""))
                response.raise_for_status()
                data = response.json()
                if data["status"] not in {"queued", "running"}:
                    emit(data)
                    return result_code(data)
                if not waiting:
                    emit(data)
                    return 3
                if time.monotonic() >= deadline:
                    cancelled = client.post("runs/" + quote(run_id, safe="") + "/cancel")
                    emit(
                        {
                            "run_id": run_id,
                            "error": "ci_wait_timeout",
                            "cancel_status": cancelled.status_code,
                        }
                    )
                    return 2
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        except KeyboardInterrupt:
            if run_id:
                try:
                    client.post("runs/" + quote(run_id, safe="") + "/cancel")
                except httpx.HTTPError:
                    pass
            emit({"run_id": run_id, "error": "ci_cancelled"})
            return 3
        except (httpx.HTTPError, ValueError, OSError, KeyError) as exc:
            # 不回显异常中的完整URL、响应正文或环境secret。
            emit(
                {
                    "run_id": run_id,
                    "error": type(exc).__name__,
                    "message": "CI请求/配置失败，请查看脱敏平台结果",
                }
            )
            return 2


if __name__ == "__main__":
    sys.exit(main())
