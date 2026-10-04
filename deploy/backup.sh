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
(cd "$backup_path" && sha256sum database.dump media.tar.gz > SHA256SUMS)
# Optional encrypted off-server repository; initialise it separately once.
# Authentication belongs in the root-only backup EnvironmentFile, not argv.
if [ -n "${RESTIC_REPOSITORY:-}" ]; then
    command -v restic >/dev/null
    test -n "${RESTIC_PASSWORD_FILE:-}"
    test -r "$RESTIC_PASSWORD_FILE"
    restic backup --tag dari-store "$backup_path"
    restic check
    date -u +%FT%TZ > "$backup_root/last-offsite-success"
else
    echo 'Off-server copy is not configured (RESTIC_REPOSITORY).' >&2
    if [ "${BACKUP_REQUIRE_OFFSITE:-false}" = true ]; then
        exit 1
    fi
fi
date -u +%FT%TZ > "$backup_root/last-local-success"
echo "Backup created: $backup_path"
