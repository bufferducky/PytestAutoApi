#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"
exec 9>"$root/.release.lock"
flock -n 9
image=pytestautoapi-backend:$tag
helper check-build "$release" "$(docker image inspect --format '{{.Id}}' "$image")"
helper check-previous "$release" "$helper_image"
review_schema > "$release/verification/migration-review-final.json"
backup=$root/backups/$tag
mkdir -m 700 "$backup"
mkdir -m 700 "$backup/deploy"
cp "$previous/deploy/.env" "$backup/deploy/.env"
cp "$previous/deploy/.htpasswd" "$backup/deploy/.htpasswd"
chmod 600 "$backup/deploy/.env" "$backup/deploy/.htpasswd"
snapshot pytestautoapi-backend-1 "$backup/before.json"
compose "$previous" stop web
snapshot pytestautoapi-backend-1 "$backup/quiesced.json"
helper compare "$backup/before.json" "$backup/quiesced.json"
compose "$previous" stop backend mysql
[ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-backend-1)" = false ]
[ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-mysql-1)" = false ]
[ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' pytestautoapi-backend-1)" = pytestautoapi_platform-data ]
[ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}' pytestautoapi-mysql-1)" = pytestautoapi_mysql-data ]
docker run --rm --user 0 --entrypoint sh -v pytestautoapi_mysql-data:/mysql-data:ro -v pytestautoapi_platform-data:/platform-data:ro -v "$backup:/backup" "$helper_image" -c '
set -eu
umask 077
tar -czf /backup/mysql-data.tar.gz -C /mysql-data .
tar -czf /backup/platform-data.tar.gz -C /platform-data .
tar -tzf /backup/mysql-data.tar.gz >/dev/null
tar -tzf /backup/platform-data.tar.gz >/dev/null
cd /backup
sha256sum mysql-data.tar.gz platform-data.tar.gz > SHA256SUMS
sha256sum -c SHA256SUMS
chown -R "$1:$2" /backup
chmod 600 /backup/*.tar.gz /backup/SHA256SUMS
' sh "$uid" "$gid"
printf '冷备份完成，开始独立恢复与升级演练。\n'
project=pyta-drill-run-numbers-8e11bf8
mysql_copy=pyta_drill_8e11bf8_mysql
state_copy=pyta_drill_8e11bf8_platform
! docker volume inspect "$mysql_copy" >/dev/null 2>&1
! docker volume inspect "$state_copy" >/dev/null 2>&1
docker volume create "$mysql_copy" >/dev/null
docker volume create "$state_copy" >/dev/null
docker run --rm --user 0 --entrypoint sh -v "$backup:/backup:ro" -v "$mysql_copy:/restore-mysql" -v "$state_copy:/restore-state" "$helper_image" -c 'set -eu; tar -xzf /backup/mysql-data.tar.gz -C /restore-mysql; tar -xzf /backup/platform-data.tar.gz -C /restore-state'
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
