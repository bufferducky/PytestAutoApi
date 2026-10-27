import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import state
from test_release_state import staged as staged

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/scripts/server_release.sh"

FAKE_DOCKER = r"""
import json,os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
root=Path(os.environ['PYTA_DEPLOY_ROOT'])
with open(os.environ['FAKE_LOG'],'a') as log:log.write(json.dumps(args)+'\n')
running=root/'running'
if args[0]=='inspect':
    fmt=args[args.index('--format')+1]
    if fmt == '{{.Image}}':
        image='sha256:test' if Path(running.read_text()).name=='release-1' else 'sha256:previous'
        if os.environ.get('WRONG_RUNNING') and image=='sha256:test':image='sha256:wrong'
        print(image)
    elif 'config_files' in fmt:print(running.read_text()+'/deploy/compose.yaml')
    elif '.State.Running' in fmt:print('false' if (root/'stopped').exists() else 'true')
    elif '/state' in fmt:print('pytestautoapi_platform-data')
    elif '/var/lib/mysql' in fmt:print('pytestautoapi_mysql-data')
    else:raise SystemExit(3)
elif args[:2]==['image','inspect']:
    print('sha256:previous' if args[-1].endswith(':previous') else 'sha256:test')
elif args[0]=='run':
    if '/release-tools/state.py' in args:
        script=Path(os.environ['REAL_TOOLS'])/'state.py'
        tail=args[args.index('/release-tools/state.py')+1:]
        raise SystemExit(subprocess.call([sys.executable,str(script),*tail]))
    if args[args.index('--entrypoint')+1]=='sh':
        if os.environ.get('FAIL_BACKUP'):raise SystemExit(42)
        backup=next(x[:-8] for x in args if x.endswith(':/backup'))
        Path(backup,'backup-verified').write_text('ok')
elif args[0]=='exec':
    if os.environ.get('BUSY'):raise SystemExit(33)
    print(json.dumps({'records':{'runs':{'existing':'hash'}},'worker':{'available':True,'queued':0}}))
elif args[0]=='compose':
    directory=Path(args[args.index('-f')+1]).parent.parent
    cmd=args[args.index('--env-file')+2:]
    if cmd[0]=='stop' and 'mysql' in cmd:(root/'stopped').touch()
    if cmd[0]=='up':
        if os.environ.get('FAIL_TARGET') and directory.name=='release-1':raise SystemExit(17)
        running.write_text(str(directory))
        (root/'stopped').unlink(missing_ok=True)
else:raise SystemExit(4)
"""


@pytest.fixture
def server(staged, tmp_path):
    _, target, previous = staged
    root = target.parent.parent
    (root / "backups").mkdir()
    (root / "running").write_text(str(previous))
    state.build_record(target, "sha256:test")
    binary = tmp_path / "bin"
    binary.mkdir()
    docker = binary / "docker"
    docker.write_text("#!" + sys.executable + "\n" + FAKE_DOCKER)
    docker.chmod(0o755)
    flock = binary / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n")
    flock.chmod(0o755)
    env = {
        **os.environ,
        "PYTA_DEPLOY_ROOT": str(root),
        "REAL_TOOLS": str(SCRIPT.parent),
        "FAKE_LOG": str(root / "commands.jsonl"),
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
    }

    def invoke(action="activate", apply=True, **extra):
        return subprocess.run(
            ["sh", str(SCRIPT), action, "release-1", "--apply" if apply else "--plan"],
            env={**env, **extra},
            capture_output=True,
            text=True,
            timeout=15,
        )

    return root, target, previous, invoke


def commands(root):
    return [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]


def test_default_plan_never_calls_docker(server):
    root, _, _, invoke = server
    result = invoke(apply=False)
    assert result.returncode == 0, result.stderr
    assert not (root / "commands.jsonl").exists()


def test_busy_or_schema_change_stops_before_service_stop(server):
    root, target, _, invoke = server
    result = invoke(BUSY="1")
    assert result.returncode != 0
    assert not any("stop" in cmd for cmd in commands(root))
    (target / "platform/backend/src/pyta_platform_backend/db/schema.py").write_text("new schema")
    result = invoke()
    assert result.returncode != 0
    assert not any("stop" in cmd for cmd in commands(root))


def test_backup_failure_restores_previous_without_starting_target(server):
    root, _, previous, invoke = server
    result = invoke(FAIL_BACKUP="1")
    assert result.returncode == 42, result.stdout + result.stderr
    calls = commands(root)
    started = [cmd[cmd.index("-f") + 1] for cmd in calls if cmd[0] == "compose" and "up" in cmd]
    assert started == [str(previous / "deploy/compose.yaml")]
    assert (root / "current").resolve() == previous
    assert not any("down" in cmd for cmd in calls)


def test_target_start_failure_restores_previous_and_keeps_current(server):
    root, target, previous, invoke = server
    result = invoke(FAIL_TARGET="1")
    assert result.returncode == 17, result.stdout + result.stderr
    assert (root / "running").read_text() == str(previous)
    assert (root / "current").resolve() == previous
    assert (root / "backups/release-1/backup-verified").is_file()
    assert not (target / "verification/after.json").exists()


def test_activation_waits_for_public_accept_and_rollback_preserves_data(server):
    root, target, previous, invoke = server
    result = invoke()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "current").resolve() == previous
    assert (root / "running").read_text() == str(target)
    assert state.read(target / "verification/state.json")["phase"] == "activated"
    denied = invoke("accept")
    assert denied.returncode != 0
    assert (root / "current").resolve() == previous
    rollback = invoke("rollback")
    assert rollback.returncode == 0, rollback.stdout + rollback.stderr
    assert (root / "running").read_text() == str(previous)
    assert state.read(target / "verification/state.json")["phase"] == "rolled-back"
    calls = commands(root)
    assert not any("down" in cmd for cmd in calls)
    assert len(list((root / "backups").glob("*rollback-*"))) == 1


def test_wrong_actual_container_image_recovers_old_application(server):
    root, _, previous, invoke = server
    result = invoke(WRONG_RUNNING="1")
    assert result.returncode != 0
    assert (root / "running").read_text() == str(previous)
    assert (root / "current").resolve() == previous


def test_accept_rejects_actual_image_different_from_tag(server):
    root, _, previous, invoke = server
    assert invoke().returncode == 0
    result = invoke("accept", WRONG_RUNNING="1")
    assert result.returncode != 0
    assert "实际运行容器" in result.stderr
    assert (root / "current").resolve() == previous
