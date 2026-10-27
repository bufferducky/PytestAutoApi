import io
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone

import pytest
import release
import state


def add_archive(path, files):
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


@pytest.fixture
def staged(tmp_path):
    previous = tmp_path / "releases/previous"
    incoming = tmp_path / "incoming/release-1"
    target = tmp_path / "releases/release-1"
    (previous / "deploy").mkdir(parents=True)
    (previous / "deploy/.env").write_text("MYSQL_PASSWORD='synthetic-only'\nRELEASE_TAG=previous\n")
    (previous / "deploy/.htpasswd").write_text("synthetic-hash")
    incoming.mkdir(parents=True)
    (incoming / "tools").mkdir()
    for name in (
        "state.py",
        "server_release.sh",
        "inventory.py",
        "image_check.py",
        "worker_smoke.py",
        "verify_public.py",
    ):
        (incoming / "tools" / name).write_text("# tool\n")
    files = {
        "pyproject.toml": b"# test\n",
        ".dockerignore": b"*\n",
        "README.md": b"# test\n",
        "deploy/compose.yaml": b"name: pytestautoapi\n",
        "platform/backend/src/pyta_platform_backend/db/schema.py": b"# schema\n",
        "platform/backend/alembic/env.py": b"# env\n",
        "platform/backend/alembic/versions/0001_mysql.py": b"# migration\n",
    }
    add_archive(incoming / "source.tar.gz", files)
    add_archive(
        incoming / "frontend.tar.gz",
        {
            "platform/frontend/dist/index.html": b'<script src="/assets/app.js"></script>',
            "platform/frontend/dist/assets/app.js": b"console.log('test')",
        },
    )
    manifest = {
        "schema_version": 1,
        "tag": "release-1",
        "commit": "a" * 40,
        "checks": {"passed": True},
        "archives": {
            name: state.sha(incoming / name) for name in ("source.tar.gz", "frontend.tar.gz")
        },
        "tools": {p.name: state.sha(p) for p in (incoming / "tools").iterdir()},
        "assets": {
            "/assets/app.js": __import__("hashlib").sha256(b"console.log('test')").hexdigest()
        },
    }
    state.write(incoming / "manifest.json", manifest)
    for name, data in files.items():
        path = previous / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    state.stage(incoming, target, previous, "sha256:previous")
    (tmp_path / "current").symlink_to(previous)
    return incoming, target, previous


def test_stage_preserves_credentials_and_binds_tag(staged):
    _, target, previous = staged
    assert (target / "deploy/.env").read_text() == (
        "MYSQL_PASSWORD='synthetic-only'\nRELEASE_TAG=release-1\n"
    )
    assert (target / "deploy/.env").stat().st_mode & 0o777 == 0o600
    assert (target / "deploy/.htpasswd").read_bytes() == (
        previous / "deploy/.htpasswd"
    ).read_bytes()
    assert (target / "platform/frontend/dist/assets/app.js").stat().st_mode & 0o777 == 0o644
    with pytest.raises(ValueError, match="已存在"):
        state.stage(staged[0], target, previous)


@pytest.mark.parametrize("tag", ["../prod", "-tag", "a;touch x", "a\nb", "a" * 65, "..", "a/b"])
def test_tag_rejected_before_any_mutation(tag):
    with pytest.raises(ValueError):
        state.validate_tag(tag)


def test_archive_path_and_link_rejected(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    add_archive(archive, {"../escape": b"bad"})
    with pytest.raises(ValueError):
        state.checked_extract(archive, tmp_path / "out", {"src"})
    assert not (tmp_path / "escape").exists()
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("src/link")
        member.type, member.linkname = tarfile.SYMTYPE, "/tmp"
        bundle.addfile(member)
    with pytest.raises(ValueError):
        state.checked_extract(archive, tmp_path / "out", {"src"})


def test_bundle_tamper_and_schema_change_refuse(staged):
    incoming, target, previous = staged
    state.check_schema(target, previous)
    (target / "platform/backend/src/pyta_platform_backend/db/schema.py").write_text("changed")
    with pytest.raises(ValueError, match="迁移"):
        state.check_schema(target, previous)
    (incoming / "frontend.tar.gz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="SHA"):
        state.verify_bundle(incoming)


def test_build_marker_rejects_changed_source_or_image(staged):
    _, target, _ = staged
    state.build_record(target, "sha256:original")
    state.check_build(target, "sha256:original")
    with pytest.raises(ValueError, match="镜像"):
        state.check_build(target, "sha256:other")
    (target / "deploy/.env").write_text("changed-config")
    with pytest.raises(ValueError, match="配置"):
        state.check_build(target, "sha256:original")


def test_accept_requires_recent_matching_browser_receipt(staged):
    _, target, previous = staged
    path = target / "verification/state.json"
    data = state.read(path)
    data["phase"] = "activated"
    state.write(path, data)
    report = {
        "schema_version": 1,
        "tag": "release-1",
        "commit": "a" * 40,
        "manifest_sha256": state.sha(target / "manifest.json"),
        "passed": True,
        "browser_passed": False,
        "url": "https://test.ysspace2099.com",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    state.write(target / "verification/public.json", report)
    with pytest.raises(ValueError, match="浏览器"):
        state.accept(target)
    assert (target.parent.parent / "current").resolve() == previous
    report["browser_passed"] = True
    report["checked_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    state.write(target / "verification/public.json", report)
    with pytest.raises(ValueError, match="过期"):
        state.accept(target)
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    state.write(target / "verification/public.json", report)
    state.accept(target)
    assert (target.parent.parent / "current").resolve() == target
    assert state.read(path)["phase"] == "accepted"


def test_data_fingerprint_change_is_failure(tmp_path):
    state.write(tmp_path / "before.json", {"records": {"runs": {"id": "before"}}})
    state.write(tmp_path / "after.json", {"records": {"runs": {"id": "after"}}})
    with pytest.raises(ValueError, match="指纹"):
        state.fingerprint_check(tmp_path / "before.json", tmp_path / "after.json")


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in release.EXPORT:
        target = repo / path
        if "." in target.name or target.name == "Makefile":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# fixture\n")
        else:
            target.mkdir(parents=True)
            (target / "placeholder").write_text("fixture")
    for path in release.RUNTIME:
        target = repo / path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# fixture\n")
    tools = repo / "deploy/scripts"
    tools.mkdir(parents=True)
    for name in (
        "state.py",
        "server_release.sh",
        "inventory.py",
        "image_check.py",
        "worker_smoke.py",
        "verify_public.py",
    ):
        (tools / name).write_text("# committed-v1\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repo,
        check=True,
    )
    return repo


def test_pack_uses_committed_tree_and_does_not_publish_on_failed_checks(git_repo, tmp_path):
    output = tmp_path / "out"
    seen = []

    def fail(args, cwd, env, log):
        seen.append(cwd)
        assert git_repo not in cwd.parents
        raise RuntimeError("injected build failure")

    with pytest.raises(RuntimeError, match="injected"):
        release.prepare("HEAD", "test-1", output, sys.executable, repo=git_repo, run=fail)
    assert seen
    assert not (output / "manifest.json").exists()
    assert not (output / "bundle.tar.gz").exists()


def test_pack_manifest_covers_actual_built_resources(git_repo, tmp_path):
    def fake_check(args, cwd, env, log):
        log.write_text("test passed")
        if args[:3] == ["npm", "run", "build"]:
            dist = cwd / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text('<script src="/assets/app.js"></script>')
            (dist / "assets/app.js").write_text("const release=1")

    output = tmp_path / "ok"
    manifest = release.prepare(
        "HEAD", "test-1", output, sys.executable, repo=git_repo, run=fake_check
    )
    assert manifest["checks"]["commands"] == 8
    assert manifest["assets"]["/assets/app.js"]
    state.verify_bundle(output)
    with tarfile.open(output / "bundle.tar.gz") as archive:
        assert not any(name.startswith("local-checks") for name in archive.getnames())
    assert (
        manifest["commit"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo, text=True).strip()
    )


def test_source_changed_after_stage_cannot_be_bound_to_original_commit(staged):
    _, target, _ = staged
    code = target / "platform/backend/src/pyta_platform_backend/new_code.py"
    code.write_text("print('changed after export')")
    with pytest.raises(ValueError, match="偏离原发布包"):
        state.build_record(target, "sha256:unverified")
    assert not (target / "verification/build.json").exists()


def test_historical_revision_carries_its_own_checked_tools(git_repo, tmp_path):
    first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo, text=True).strip()
    (git_repo / "deploy/scripts/state.py").write_text("# committed-v2\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.test",
            "commit",
            "-qm",
            "new tools",
        ],
        cwd=git_repo,
        check=True,
    )

    def fake_check(args, cwd, env, log):
        if args[:3] == ["npm", "run", "build"]:
            dist = cwd / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text('<script src="/assets/a.js"></script>')
            (dist / "assets/a.js").write_text("v1")

    output = tmp_path / "old-release"
    release.prepare(first, "historical", output, sys.executable, repo=git_repo, run=fake_check)
    assert (output / "tools/state.py").read_text() == "# committed-v1\n"
