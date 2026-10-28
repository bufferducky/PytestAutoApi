#!/bin/sh
set -eu
tag=20261028-run-readability-8e11bf8
root=/home/ubuntu/pytestautoapi
incoming=$root/incoming/$tag
release=$root/releases/$tag
tools=$incoming/tools
migration_tools=$incoming/migration-tools
previous=$(readlink -f "$root/current")
[ "$previous" = "$root/releases/20261027-frontend-ux-1a3e797" ]
uid=$(id -u)
gid=$(id -g)
helper_image=$(docker inspect --format '{{.Image}}' pytestautoapi-backend-1)
helper() {
    docker run --rm --user "$uid:$gid" --entrypoint python -v "$root:$root" -v "$tools:/release-tools:ro" "$helper_image" /release-tools/state.py "$@"
}
compose() {
    directory=$1; shift
    docker compose -p pytestautoapi -f "$directory/deploy/compose.yaml" --env-file "$directory/deploy/.env" "$@"
}
snapshot() {
    container=$1; destination=$2; kind=${3:-compatible}
    docker exec "$container" mkdir -p /tmp/pyta-release-check
    docker cp "$tools/inventory.py" "$container:/tmp/pyta-release-check/inventory.py"
    docker cp "$migration_tools/migration_inventory.py" "$container:/tmp/pyta-release-check/migration_inventory.py"
    docker exec --user 0 "$container" chmod 644 /tmp/pyta-release-check/inventory.py /tmp/pyta-release-check/migration_inventory.py
    if [ "$kind" = plain ]; then
        docker exec "$container" python /tmp/pyta-release-check/inventory.py > "$destination"
    elif [ "$kind" = numbers ]; then
        docker exec "$container" python /tmp/pyta-release-check/migration_inventory.py --numbers > "$destination"
    else
        docker exec "$container" python /tmp/pyta-release-check/migration_inventory.py > "$destination"
    fi
    chmod 600 "$destination"
}
review_schema() {
    docker run --rm --user "$uid:$gid" --entrypoint python -v "$root:$root:ro" "$helper_image" "$migration_tools/review_schema.py" "$previous" "$release"
}
