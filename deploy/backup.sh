#!/usr/bin/env bash
set -euo pipefail
umask 0077
backup_root=/srv/dari/backups
backup_path="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_path"
# libpq obtains connection parameters from PGSERVICEFILE; passwords never appear in argv.
test -n "${PGSERVICE:-}"
pg_dump --format=custom --file="$backup_path/database.dump"
tar -czf "$backup_path/media.tar.gz" -C /srv/dari/shared media private-media
sha256sum "$backup_path/database.dump" "$backup_path/media.tar.gz" > "$backup_path/SHA256SUMS"
echo "Backup created: $backup_path. Copy to the configured encrypted off-server storage."
