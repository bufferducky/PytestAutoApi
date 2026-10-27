"""读取既有平台API；仅输出ID/版本与公开内容指纹，不导出正文。"""

import hashlib
import json
from urllib.request import urlopen

PATHS = {
    "environments": "environments",
    "scenarios": "scenarios",
    "suites": "suite-assets",
    "schedules": "schedule-plans",
    "targets": "targets",
    "identities": "identity-profiles",
    "bindings": "context-bindings",
    "fixtures": "fixture-definitions",
    "media": "media-datasets",
    "journeys": "journeys",
    "devices": "device-profiles",
    "evaluation_datasets": "evaluation-datasets",
    "rubrics": "rubrics",
}
VERSIONED = {"fixtures", "media", "journeys", "devices", "evaluation_datasets", "rubrics"}


def get(path):
    with urlopen("http://127.0.0.1:8000/api/v1/" + path, timeout=30) as response:
        return json.load(response)


def fingerprint(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def collect(fetch=get):
    records = {}
    for kind, path in PATHS.items():
        rows = []
        if kind in {"scenarios", "suites"}:
            while True:
                page = fetch(path + "?limit=100&offset=" + str(len(rows)))
                rows.extend(page)
                if len(page) < 100:
                    break
        else:
            rows = fetch(path)
        if not isinstance(rows, list):
            raise ValueError("asset list shape changed")
        index = {}
        for row in rows:
            # 接口返回全部版本，用组合键保留每一版；不能按ID覆盖成最旧版。
            key = json.dumps([row["id"], row["version"]]) if kind in VERSIONED else str(row["id"])
            if key in index:
                raise ValueError("duplicate asset identity/version")
            index[key] = fingerprint(row)
        records[kind] = index
        if kind == "environments":
            records["environment_details"] = {
                str(row["id"]): fingerprint(fetch("environments/" + row["id"])) for row in rows
            }
        if kind == "schedules" and any(row.get("status") == "active" for row in rows):
            raise ValueError("active schedules require drain")
        if kind in {"scenarios", "suites"}:
            prefix = "scenarios" if kind == "scenarios" else "suites"
            records[kind + "_versions"] = {
                str(row["id"]): fingerprint(fetch(prefix + "/" + row["id"] + "/versions"))
                for row in rows
            }
    runs = []
    while True:
        page = fetch("runs?limit=100&offset=" + str(len(runs)))
        runs.extend(page["items"])
        if len(runs) >= page["total"]:
            break
        if not page["items"]:
            raise ValueError("incomplete run pagination")
    if any(row["status"] in {"queued", "running"} for row in runs):
        raise ValueError("active runs require drain")
    records["runs"] = {row["run_id"]: fingerprint(row) for row in runs}
    records["run_details"] = {
        row["run_id"]: fingerprint(fetch("runs/" + row["run_id"])) for row in runs
    }
    worker = fetch("worker/status")
    if not worker["available"] or worker["last_error"] is not None or worker["queued"] != 0:
        raise ValueError("worker not idle/healthy")
    return {
        "records": records,
        "counts": {kind: len(rows) for kind, rows in records.items()},
        "worker": worker,
    }


if __name__ == "__main__":
    print(json.dumps(collect(), sort_keys=True))
