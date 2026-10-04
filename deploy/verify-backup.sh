#!/usr/bin/env bash
# Run on a separate restore host with a dedicated libpq service that can CREATE DATABASE.
# Restores into a newly created, unique database; never into the shop database.
set -euo pipefail
umask 0077
test -n "${PGSERVICE:-}"
backup_path="$(realpath -e "${1:?Supply the downloaded backup directory}")"
test -d "$backup_path"
test -f "$backup_path/database.dump"
test -f "$backup_path/media.tar.gz"
test -f "$backup_path/SHA256SUMS"
(cd "$backup_path" && sha256sum --check SHA256SUMS)
tar -tzf "$backup_path/media.tar.gz" >/dev/null
restore_db="dari_restore_$(date -u +%Y%m%d%H%M%S)_$$"
case "$restore_db" in dari_restore_[0-9]*_[0-9]*) ;; *) exit 1 ;; esac
# Install trap only AFTER successful creation: never drop a pre-existing DB.
createdb -- "$restore_db"
trap 'dropdb --if-exists -- "$restore_db"' EXIT
pg_restore --exit-on-error --no-owner --no-acl --dbname="$restore_db" "$backup_path/database.dump"
psql --dbname="$restore_db" --no-psqlrc --set=ON_ERROR_STOP=1 \
    --command='SELECT count(*) AS orders FROM orders_order; SELECT count(*) AS products FROM catalog_product;'
echo 'Backup checksums, media archive and isolated PostgreSQL restore passed.'
