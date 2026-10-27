"""发布文件校验与回执；由服务器已有镜像中的 Python 执行。"""

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TAG = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\Z")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def validate_tag(tag):
    if not TAG.fullmatch(tag) or ".." in tag:
        raise ValueError("tag 须为1—64位字母数字/点/下划线/短横线，不能含 ..")
    return tag


def checked_extract(archive, destination, allowed):
    """只接受正常文件/目录；先校验整包，防止链接或越界写入。"""
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not (member.isfile() or member.isdir())
                or not name.parts
                or name.parts[0] not in allowed
                or any(
                    p in {".env", ".htpasswd", "access.txt", ".runtime", "__pycache__"}
                    or p.startswith("._")
                    for p in name.parts
                )
            ):
                raise ValueError("发布包含越界、链接或不允许的文件")
        # 不继承本机0600代码权限或扩展属性；部署配置随后单独600写入。
        for member in members:
            path = Path(destination).joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o755)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                path.chmod(0o755 if member.mode & 0o111 else 0o644)


def verify_bundle(incoming):
    incoming = Path(incoming)
    manifest = read(incoming / "manifest.json")
    validate_tag(manifest["tag"])
    if manifest["schema_version"] != 1 or not re.fullmatch(r"[a-f0-9]{40}", manifest["commit"]):
        raise ValueError("manifest 版本或提交号无效")
    if manifest.get("checks", {}).get("passed") is not True:
        raise ValueError("发布包缺少通过的本地检查")
    for name in ("source.tar.gz", "frontend.tar.gz"):
        if sha(incoming / name) != manifest["archives"][name]:
            raise ValueError("发布包 SHA-256 不匹配")
    required_tools = {
        "state.py",
        "server_release.sh",
        "inventory.py",
        "image_check.py",
        "worker_smoke.py",
        "verify_public.py",
    }
    if not required_tools.issubset(manifest["tools"]):
        raise ValueError("发布包缺少必要工具")
    for name, digest in manifest["tools"].items():
        if PurePosixPath(name).name != name or sha(incoming / "tools" / name) != digest:
            raise ValueError("发布工具 SHA-256 不匹配")
    return manifest


def stage(incoming, release, previous, previous_image_id=""):
    incoming, release, previous = map(Path, (incoming, release, previous))
    manifest = verify_bundle(incoming)
    if release.name != manifest["tag"] or release.exists():
        raise ValueError("发布目录已存在或 tag 不匹配")
    if not previous.is_dir() or not (previous / "deploy/.env").is_file():
        raise ValueError("缺少已运行版本配置；首次部署须按SOP单独处理")
    release.mkdir(mode=0o755)
    checked_extract(
        incoming / "source.tar.gz",
        release,
        {"src", "platform", "deploy", "pyproject.toml", "README.md", ".dockerignore"},
    )
    checked_extract(incoming / "frontend.tar.gz", release, {"platform"})
    for path, digest in manifest["assets"].items():
        asset = PurePosixPath(path)
        if not path.startswith("/assets/") or ".." in asset.parts:
            raise ValueError("资源路径无效")
        if sha(release / "platform/frontend/dist" / path.lstrip("/")) != digest:
            raise ValueError("前端资源指纹不匹配")
    shutil.copy2(incoming / "manifest.json", release / "manifest.json")
    shutil.copytree(incoming / "tools", release / "release-tools")
    env = (previous / "deploy/.env").read_text()
    lines = [
        line for line in env.splitlines() if not re.match(r"\s*(?:export\s+)?RELEASE_TAG\s*=", line)
    ]
    # 文件创建时即600，避免先以默认0644写入秘密再chmod的短暂窗口。
    descriptor = os.open(release / "deploy/.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join([*lines, "RELEASE_TAG=" + release.name]) + "\n")
    shutil.copyfile(previous / "deploy/.htpasswd", release / "deploy/.htpasswd")
    (release / "deploy/.htpasswd").chmod(0o644)
    write(release / "verification/staged-inputs.json", release_inputs(release))
    write(
        release / "verification/state.json",
        {
            "tag": release.name,
            "previous": str(previous.resolve()),
            "phase": "staged",
            "previous_image_id": previous_image_id,
            "previous_config": {
                name: sha(previous / name)
                for name in ("deploy/.env", "deploy/.htpasswd", "deploy/compose.yaml")
            },
            "manifest_sha256": sha(release / "manifest.json"),
        },
    )


def schema_files(root):
    root = Path(root)
    paths = [root / "platform/backend/src/pyta_platform_backend/db/schema.py"]
    paths += sorted((root / "platform/backend/alembic").rglob("*.py"))
    if not paths[0].is_file() or len(paths) < 3:
        raise ValueError("缺少schema/迁移文件")
    return {str(path.relative_to(root)): sha(path) for path in paths}


def check_schema(release, previous):
    if schema_files(release) != schema_files(previous):
        raise ValueError("schema/迁移脚本有变化，转SOP数据库迁移流程，自动发布停止")


def fingerprint_check(before, after):
    if read(before)["records"] != read(after)["records"]:
        raise ValueError("资产/运行/版本ID或内容指纹变化，验收失败")


def build_inputs(release):
    release = Path(release)
    manifest = verify_bundle(release.parent.parent / "incoming" / release.name)
    if sha(release / "manifest.json") != sha(
        release.parent.parent / "incoming" / release.name / "manifest.json"
    ):
        raise ValueError("发布清单与原包不一致")
    current = release_inputs(release)
    if current != read(release / "verification/staged-inputs.json"):
        raise ValueError("解包后源码或配置已偏离原发布包，须使用新tag重新stage")
    return {
        "manifest_sha256": sha(release / "manifest.json"),
        "inputs": current,
        "tag": manifest["tag"],
    }


def release_inputs(release):
    release = Path(release)
    paths = [release / "pyproject.toml", release / ".dockerignore"]
    for name in ("src", "platform/backend", "platform/frontend/dist", "deploy", "release-tools"):
        paths.extend(p for p in (release / name).rglob("*") if p.is_file())
    return {
        str(p.relative_to(release)): sha(p)
        for p in paths
        if "__pycache__" not in p.parts and not p.name.startswith("._")
    }


def check_previous(release, image):
    release = Path(release)
    data = read(release / "verification/state.json")
    previous = Path(data["previous"])
    if data.get("previous_image_id") != image:
        raise ValueError("上一镜像ID发生变化，停止自动发布/回滚")
    if data["previous_config"] != {name: sha(previous / name) for name in data["previous_config"]}:
        raise ValueError("上一版本配置发生变化，须人工核实")


def build_record(release, image):
    release = Path(release)
    data = build_inputs(release)
    data["image_id"] = image
    write(release / "verification/build.json", data)


def check_build(release, image):
    release = Path(release)
    data = read(release / "verification/build.json")
    current = {**build_inputs(release), "image_id": image}
    if data != current:
        raise ValueError("镜像/源码/配置与已验收build不一致，须重新build")


def accept(release):
    release = Path(release)
    report = read(release / "verification/public.json")
    state = read(release / "verification/state.json")
    manifest = read(release / "manifest.json")
    if state["phase"] != "activated":
        raise ValueError("仅已切换且数据核验通过的版本可accept")
    expected = {
        "schema_version": 1,
        "tag": manifest["tag"],
        "commit": manifest["commit"],
        "manifest_sha256": sha(release / "manifest.json"),
        "passed": True,
        "browser_passed": True,
        "url": "https://test.ysspace2099.com",
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("缺少匹配本版本且浏览器通过的公网验收")
    checked = datetime.fromisoformat(report["checked_at"])
    age = (datetime.now(timezone.utc) - checked).total_seconds()
    if not 0 <= age <= 3600:
        raise ValueError("公网回执已过期，须在1小时内accept")
    switch_link(release)
    state["phase"] = "accepted"
    write(release / "verification/state.json", state)


def switch_link(release):
    release = Path(release).resolve()
    if release.parent.name != "releases" or not release.is_dir():
        raise ValueError("只能链接已存在的发布目录")
    link = release.parent.parent / "current"
    temporary = link.with_name(".current-next")
    if temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(release)
    os.replace(temporary, link)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "stage",
            "schema",
            "compare",
            "build",
            "check-build",
            "check-previous",
            "check-running",
            "check-staged",
            "accept",
            "previous",
            "phase",
            "link",
        ],
    )
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.action == "stage":
        stage(*args.paths)
    elif args.action == "schema":
        check_schema(*args.paths)
    elif args.action == "compare":
        fingerprint_check(*args.paths)
    elif args.action == "build":
        build_record(*args.paths)
    elif args.action == "check-build":
        check_build(*args.paths)
    elif args.action == "check-staged":
        build_inputs(args.paths[0])
    elif args.action == "check-running":
        if read(Path(args.paths[0]) / "verification/build.json")["image_id"] != args.paths[1]:
            raise ValueError("实际运行容器镜像与已验收镜像不同")
    elif args.action == "check-previous":
        check_previous(*args.paths)
    elif args.action == "accept":
        accept(*args.paths)
    elif args.action == "link":
        switch_link(args.paths[0])
    elif args.action == "previous":
        print(read(Path(args.paths[0]) / "verification/state.json")["previous"])
    else:
        release, phase = args.paths
        path = Path(release) / "verification/state.json"
        data = read(path)
        data["phase"] = phase
        write(path, data)


if __name__ == "__main__":
    main()
