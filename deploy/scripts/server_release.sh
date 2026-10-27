#!/bin/sh
# 在154宿主机执行；所有Python检查借用现有镜像，不安装宿主机依赖。
set -eu

action=${1:-}
tag=${2:-}
mode=${3:---plan}
root=${PYTA_DEPLOY_ROOT:-/home/ubuntu/pytestautoapi}
case "$action" in stage|build|activate|accept|rollback) ;; *)
    echo '用法: sh server_release.sh stage|build|activate|accept|rollback TAG [--apply]' >&2
    exit 2 ;;
esac
case "$tag" in ''|*[!a-zA-Z0-9._-]*|*..*|[!a-zA-Z0-9]*) echo '无效tag' >&2; exit 2;; esac
[ "${#tag}" -le 64 ] || { echo 'tag过长' >&2; exit 2; }
case "$root" in /*) ;; *) echo '发布根目录须为绝对路径' >&2; exit 2;; esac
case "$mode" in --plan) printf '计划: %s %s，根目录 %s；未操作服务器。\n' "$action" "$tag" "$root"; exit 0;;
    --apply) ;; *) echo '仅支持--plan或--apply' >&2; exit 2;; esac
[ "$#" -le 3 ] || exit 2

command -v flock >/dev/null
exec 9>"$root/.release.lock"
flock -n 9 || { echo '其他发布操作持有锁' >&2; exit 1; }
tools=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
release=$root/releases/$tag
incoming=$root/incoming/$tag
current=$(readlink -f "$root/current")
[ "$(dirname -- "$current")" = "$root/releases" ] || { echo 'current不在releases内' >&2; exit 1; }
[ -f "$current/deploy/.env" ]
helper_image=$(docker inspect --format '{{.Image}}' pytestautoapi-backend-1)
uid=$(id -u)
gid=$(id -g)
helper() {
    docker run --rm --user "$uid:$gid" --entrypoint python \
        -v "$root:$root" -v "$tools:/release-tools:ro" "$helper_image" \
        /release-tools/state.py "$@"
}
compose() { directory=$1; shift; docker compose -p pytestautoapi -f "$directory/deploy/compose.yaml" --env-file "$directory/deploy/.env" "$@"; }
assert_running() {
    expected=$1
    config=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' pytestautoapi-backend-1)
    [ "$(readlink -f "$config")" = "$expected/deploy/compose.yaml" ] || { echo '运行版本与预期目录不同，停止' >&2; exit 1; }
}
snapshot() {
    destination=$1
    docker exec -i pytestautoapi-backend-1 python - < "$tools/inventory.py" > "$destination.tmp"
    chmod 600 "$destination.tmp"
    mv "$destination.tmp" "$destination"
}
image_id() { docker image inspect --format '{{.Id}}' "pytestautoapi-backend:$tag"; }
previous_release() {
    previous=$(helper previous "$release")
    [ "$(dirname -- "$previous")" = "$root/releases" ] && [ -d "$previous" ] || exit 1
}

case "$action" in
stage)
    assert_running "$current"
    helper stage "$incoming" "$release" "$current" "$helper_image"
    compose "$release" config --quiet
    printf '已准备 %s；线上未切换。\n' "$release"
    ;;
build)
    previous_release
    [ "$current" = "$previous" ]
    assert_running "$current"
    helper schema "$release" "$previous"
    compose "$release" config --quiet
    helper check-staged "$release"
    compose "$release" build backend
    image="pytestautoapi-backend:$tag"
    docker run --rm --entrypoint python "$image" -m alembic -c platform/backend/alembic.ini history > "$release/verification/alembic.txt"
    docker run --rm -i --entrypoint python "$image" - < "$tools/image_check.py" > "$release/verification/image.json.tmp"
    mv "$release/verification/image.json.tmp" "$release/verification/image.json"
    docker run --rm -i --entrypoint python "$image" - < "$tools/worker_smoke.py" > "$release/verification/worker.json.tmp"
    mv "$release/verification/worker.json.tmp" "$release/verification/worker.json"
    helper build "$release" "$(image_id)"
    helper phase "$release" built
    echo '镜像隔离检查通过；线上未切换。'
    ;;
activate|rollback)
    previous_release
    helper schema "$release" "$previous"
    if [ "$action" = activate ]; then
        [ "$current" = "$previous" ]
        assert_running "$previous"
        helper check-build "$release" "$(image_id)"
        helper check-previous "$release" "$helper_image"
        source_release=$previous
        target_release=$release
        backup=$root/backups/$tag
    else
        case "$current" in "$release"|"$previous") ;; *) echo 'current已有其他发布，禁止回滚' >&2; exit 1;; esac
        assert_running "$release"
        prior_tag=$(basename -- "$previous")
        prior_image=$(docker image inspect --format '{{.Id}}' "pytestautoapi-backend:$prior_tag")
        helper check-previous "$release" "$prior_image"
        source_release=$release
        target_release=$previous
        backup=$root/backups/$tag-rollback-$(date -u +%Y%m%dT%H%M%SZ)
    fi
    compose "$target_release" config --quiet
    mkdir "$backup"
    chmod 700 "$backup"
    mkdir -m 700 "$backup/deploy"
    cp "$source_release/deploy/.env" "$backup/deploy/.env"
    cp "$source_release/deploy/.htpasswd" "$backup/deploy/.htpasswd"
    chmod 600 "$backup/deploy/.env" "$backup/deploy/.htpasswd"
    snapshot "$backup/before.json"
    # 先安装失败恢复，再停止入口；恢复只切应用，永不覆盖当前数据卷。
    stopped=0
    recover() {
        result=$?
        trap - EXIT HUP INT TERM
        if [ "$result" -ne 0 ] && [ "$stopped" -eq 1 ]; then
            echo '发布失败，尝试恢复操作前的应用与现有数据卷。' >&2
            if compose "$source_release" up -d --no-build --wait --wait-timeout 120 mysql backend web; then
                snapshot "$backup/recovered.json"
                helper compare "$backup/before.json" "$backup/recovered.json"
            else
                echo '自动恢复失败：保持所有卷和发布目录，按SOP人工恢复。' >&2
            fi
        fi
        exit "$result"
    }
    trap recover EXIT
    trap 'exit 130' HUP INT TERM
    stopped=1
    compose "$source_release" stop web
    # 封闭公网写入口后再检查，避免第一次检查与停写间进入新任务。
    snapshot "$backup/quiesced.json"
    helper compare "$backup/before.json" "$backup/quiesced.json"
    compose "$source_release" stop backend mysql
    [ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-backend-1)" = false ]
    [ "$(docker inspect --format '{{.State.Running}}' pytestautoapi-mysql-1)" = false ]
    # 核对实际卷名，防止误备份或备份到空卷。
    [ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' pytestautoapi-backend-1)" = pytestautoapi_platform-data ]
    [ "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}' pytestautoapi-mysql-1)" = pytestautoapi_mysql-data ]
    docker run --rm --user 0 --entrypoint sh \
        -v pytestautoapi_mysql-data:/mysql-data:ro \
        -v pytestautoapi_platform-data:/platform-data:ro \
        -v "$backup:/backup" "$helper_image" -c '
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
    compose "$target_release" up -d --no-build --wait --wait-timeout 120 mysql backend web
    actual_image=$(docker inspect --format '{{.Image}}' pytestautoapi-backend-1)
    if [ "$action" = activate ]; then
        helper check-running "$release" "$actual_image"
    else
        helper check-previous "$release" "$actual_image"
    fi
    snapshot "$backup/after.json"
    helper compare "$backup/quiesced.json" "$backup/after.json"
    if [ "$action" = activate ]; then
        cp "$backup/after.json" "$release/verification/after.json"
        helper phase "$release" activated
        echo '新服务健康、数据指纹一致；current暂不改变，执行公网验收后accept。'
    else
        helper link "$previous"
        helper phase "$release" rolled-back
        echo '应用已回滚；保留现有数据和回滚前备份。'
    fi
    stopped=0
    trap - EXIT HUP INT TERM
    ;;
accept)
    previous_release
    [ "$current" = "$previous" ]
    assert_running "$release"
    helper check-build "$release" "$(image_id)"
    helper check-running "$release" "$helper_image"
    snapshot "$release/verification/accept-inventory.json"
    helper compare "$release/verification/after.json" "$release/verification/accept-inventory.json"
    helper accept "$release"
    echo '公网回执与数据核验通过，current已原子切换。'
    ;;
esac
