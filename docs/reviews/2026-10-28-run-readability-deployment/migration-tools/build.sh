#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"
exec 9>"$root/.release.lock"
flock -n 9
[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' pytestautoapi-backend-1)" = "$previous/deploy/compose.yaml" ]
review_schema > "$release/verification/migration-review.json"
helper check-staged "$release"
compose "$release" config --quiet
compose "$release" build backend
image=pytestautoapi-backend:$tag
docker run --rm --entrypoint python "$image" -m alembic -c platform/backend/alembic.ini history > "$release/verification/alembic.txt"
docker run --rm -i --entrypoint python "$image" - < "$tools/image_check.py" > "$release/verification/image.json"
docker run --rm -i --entrypoint python "$image" - < "$tools/worker_smoke.py" > "$release/verification/worker.json"
helper build "$release" "$(docker image inspect --format '{{.Id}}' "$image")"
helper phase "$release" built
printf '专用迁移结构审查和新镜像隔离检查通过，生产未切换。\n'
