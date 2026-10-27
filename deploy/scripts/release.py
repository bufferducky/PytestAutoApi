#!/usr/bin/env python3
"""从固定 Git 提交构建、验证并打包；本工具不连接服务器。"""

import argparse
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from state import checked_extract, sha, validate_tag

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = (
    "pyproject.toml",
    "README.md",
    ".dockerignore",
    "src",
    "platform/backend/src",
    "platform/backend/alembic",
    "platform/backend/alembic.ini",
    "deploy/Dockerfile",
    "deploy/compose.yaml",
    "deploy/nginx.conf",
)
EXPORT = (
    "src",
    "platform",
    "tests",
    "deploy",
    "pyproject.toml",
    "README.md",
    "pytest.ini",
    "Makefile",
    ".dockerignore",
)


def command(args, cwd, env, log):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"检查失败：{args[0]}；详情在本地 {log}")


def archive_paths(root, paths, output):
    # 使用Python归档避免macOS AppleDouble/xattrs；权限按发布可读要求规范化。
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        for name in paths:
            path = root / name
            candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
            for item in candidates:
                if item.is_symlink():
                    raise ValueError("发布源码不能包含符号链接")
                if not item.is_file():
                    continue
                relative = item.relative_to(root)
                if any(
                    p in {"__pycache__", ".env", ".htpasswd", "access.txt", ".runtime"}
                    or p.startswith("._")
                    for p in relative.parts
                ):
                    continue
                info = tarfile.TarInfo(relative.as_posix())
                data = item.read_bytes()
                info.size, info.mode = len(data), 0o644
                bundle.addfile(info, io.BytesIO(data))


def prepare(revision, tag, output, python, *, repo=ROOT, run=command):
    validate_tag(tag)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("输出目录必须不存在，失败的发布包也不自动覆盖")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip():
        raise ValueError("工作树须干净；先提交需要发布的改动")
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=repo, text=True
    ).strip()
    python = Path(python).expanduser().absolute()
    if not python.is_file():
        raise ValueError("指定的Python解释器不存在")
    output.mkdir(parents=True, mode=0o700)
    logs = output / "local-checks"
    logs.mkdir(mode=0o700)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTA_TEST_MYSQL_URL", "PYTA_RUN_BROWSER_TESTS", "PYTHONPATH"}
    }
    env.update(VITE_API_BASE_URL="/api/v1", PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="pyta-release-") as directory:
        stage = Path(directory)
        source = stage / "checkout"
        source.mkdir()
        archive = stage / "checkout.tar.gz"
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", str(archive), commit, "--", *EXPORT],
            cwd=repo,
            check=True,
        )
        checked_extract(archive, source, {name.split("/")[0] for name in EXPORT})
        env["PYTHONPATH"] = os.pathsep.join(
            str(source / p) for p in ("src", "platform/backend/src")
        )
        commands = [
            (["npm", "ci"], source / "platform/frontend", env),
            (
                [
                    str(python),
                    "-m",
                    "ruff",
                    "check",
                    "platform/backend/src",
                    "src/testflow_engine",
                    "deploy/scripts",
                ],
                source,
                env,
            ),
            (
                [
                    str(python),
                    "-m",
                    "pytest",
                    "tests/engine",
                    "tests/compat",
                    "tests/backend",
                    "tests/deploy",
                    "-q",
                ],
                source,
                env,
            ),
            (
                ["npm", "run", "build", "--", "--mode", "production"],
                source / "platform/frontend",
                env,
            ),
        ]
        for script in ("reliability", "environment-variables", "environment-unsaved"):
            commands.append((["node", f"tests/frontend/{script}.cjs"], source, env))
        commands.append(
            (
                [
                    str(python),
                    "-m",
                    "pytest",
                    "tests/backend/test_platform_frontend_browser.py",
                    "-q",
                ],
                source,
                {**env, "PYTA_RUN_BROWSER_TESTS": "1"},
            )
        )
        for index, (args, cwd, check_env) in enumerate(commands):
            print(f"本地检查 {index + 1}/{len(commands)}: {' '.join(args)}", flush=True)
            run(args, cwd, check_env, logs / f"{index + 1:02d}.log")
        archive_paths(source, RUNTIME, output / "source.tar.gz")
        archive_paths(source, ("platform/frontend/dist",), output / "frontend.tar.gz")
        tools = output / "tools"
        tools.mkdir()
        for path in (source / "deploy/scripts").iterdir():
            if path.suffix in {".py", ".sh"}:
                (tools / path.name).write_bytes(path.read_bytes())
        dist = source / "platform/frontend/dist"
        html = (dist / "index.html").read_text()
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
        if not assets:
            raise ValueError("前端产物未包含入口资源")
        manifest = {
            "schema_version": 1,
            "tag": tag,
            "commit": commit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "passed": True,
                "commands": len(commands),
                "browser": True,
                "mysql_integration": "not_run",
            },
            "archives": {name: sha(output / name) for name in ("source.tar.gz", "frontend.tar.gz")},
            "tools": {p.name: sha(p) for p in sorted(tools.iterdir())},
            "assets": {asset: sha(dist / asset.lstrip("/")) for asset in assets},
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        # local-checks仅本地保留，上传包不携带测试输出或运行环境信息。
        archive_paths(
            output,
            ("source.tar.gz", "frontend.tar.gz", "manifest.json", "tools"),
            output / "bundle.tar.gz",
        )
    print("发布包：", output / "bundle.tar.gz")
    print("SHA-256：", sha(output / "bundle.tar.gz"))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=ROOT / ".venv/bin/python")
    parser.add_argument("--plan", action="store_true", help="只显示计划，不构建、不写文件")
    args = parser.parse_args()
    validate_tag(args.tag)
    if args.plan:
        print(
            json.dumps(
                {
                    "revision": args.revision,
                    "tag": args.tag,
                    "output": str(args.output),
                    "remote_actions": False,
                },
                indent=2,
            )
        )
        return
    prepare(args.revision, args.tag, args.output, args.python)


if __name__ == "__main__":
    main()
