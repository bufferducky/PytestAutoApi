#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"
exec 9>"$root/.release.lock"
flock -n 9
image=pytestautoapi-backend:$tag
backup=$root/backups/$tag
project=pyta-drill-run-numbers-8e11bf8
mysql_copy=pyta_drill_8e11bf8_mysql
state_copy=pyta_drill_8e11bf8_platform
[ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-backend-1)" = false ]
[ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-mysql-1)" = false ]
helper check-build "$release" "$(docker image inspect --format '{{.Id}}' "$image")"
docker run --rm --user "$uid:$gid" --entrypoint sh -v "$backup:/backup:ro" "$helper_image" -c 'cd /backup && sha256sum -c SHA256SUMS'
docker volume inspect "$mysql_copy" >/dev/null
docker volume inspect "$state_copy" >/dev/null
compose "$previous" config --format json | docker run --rm -i --user "$uid:$gid" --entrypoint python -v "$root:$root" "$helper_image" "$migration_tools/prepare_drill.py" "$previous" "$backup/drill-compose.json" "$project" "$mysql_copy" "$state_copy"
drill() { docker compose -p "$project" -f "$backup/drill-compose.json" "$@"; }
drill config --quiet
drill up -d --no-build --wait --wait-timeout 150 mysql backend
clone=$(drill ps -q backend)
snapshot "$clone" "$backup/restored-before.json"
helper compare "$backup/quiesced.json" "$backup/restored-before.json"
printf '冷备份恢复读取与全部API内容指纹一致。\n'
drill stop backend
docker run --rm --user "$uid:$gid" --entrypoint python -v "$backup:/backup" "$helper_image" -c 'import json,sys; from pathlib import Path; p=Path("/backup/drill-compose.json"); d=json.loads(p.read_text()); d["services"]["backend"]["image"]=sys.argv[1]; p.write_text(json.dumps(d))' "$image"
drill run --rm --no-deps backend python -m alembic -c platform/backend/alembic.ini upgrade head
drill up -d --no-build --wait --wait-timeout 150 backend
clone=$(drill ps -q backend)
snapshot "$clone" "$backup/restored-migrated.json"
helper compare "$backup/quiesced.json" "$backup/restored-migrated.json"
snapshot "$clone" "$backup/drill-numbers.json" numbers
drill exec -T backend python -m alembic -c platform/backend/alembic.ini current > "$backup/drill-alembic.txt"
grep -q '0002_run_numbers' "$backup/drill-alembic.txt"
drill stop backend mysql
printf '恢复副本0002迁移、原ID/内容保全和全部编号核验通过。\n'
compose "$release" up -d --no-build --wait --wait-timeout 150 mysql
compose "$release" run --rm --no-deps backend python -m alembic -c platform/backend/alembic.ini upgrade head
compose "$release" up -d --no-build --wait --wait-timeout 150 backend
helper check-running "$release" "$(docker inspect --format '{{.Image}}' pytestautoapi-backend-1)"
snapshot pytestautoapi-backend-1 "$backup/after-compatible.json"
helper compare "$backup/quiesced.json" "$backup/after-compatible.json"
snapshot pytestautoapi-backend-1 "$backup/production-numbers.json" numbers
cmp "$backup/drill-numbers.json" "$backup/production-numbers.json"
compose "$release" exec -T backend python -m alembic -c platform/backend/alembic.ini current > "$release/verification/alembic-current.txt"
grep -q '0002_run_numbers' "$release/verification/alembic-current.txt"
compose "$release" up -d --no-build --wait --wait-timeout 120 web
snapshot pytestautoapi-backend-1 "$release/verification/after.json" plain
cp "$backup/production-numbers.json" "$release/verification/run-numbers.json"
helper phase "$release" activated
printf '生产0002迁移完成、历史内容一致、编号与恢复演练一致；等待公网验收accept。\n'
