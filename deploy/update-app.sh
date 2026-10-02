#!/usr/bin/env bash
# Update an existing installation, preserving its environment, Nginx and timers.
# Run as root: bash deploy/update-app.sh /srv/dari/releases/<new-release>
set -euo pipefail
umask 0022

test "$(id -u)" -eq 0
exec 9>/run/lock/dari-release.lock
flock -n 9 || { echo 'Another release operation is running.' >&2; exit 1; }

release_path="$(realpath -e "${1:?Supply a new prepared release directory}")"
case "$release_path" in /srv/dari/releases/*) ;; *) echo 'Unexpected release path.' >&2; exit 1;; esac
test -L /srv/dari/current
old_release="$(readlink -e /srv/dari/current)"
case "$old_release" in /srv/dari/releases/*) ;; *) echo 'Unexpected current release.' >&2; exit 1;; esac
test "$release_path" != "$old_release"
test -f "$release_path/manage.py"
test -x "$old_release/.venv/bin/python"
test -r /etc/dari/dari.env
test -x /usr/bin/python3.12
test "$(node -p 'Number(process.versions.node.split(".")[0])')" -eq 22
systemctl is-active --quiet dari.service

stage=preparation
trap 'printf "\nUPDATE STOPPED during %s. Current release: %s\nPrevious application: %s\nInspect the error before retrying; database migrations may already be applied.\n" "$stage" "$(readlink -f /srv/dari/current)" "$old_release" >&2' ERR

run_app() {
    systemd-run --quiet --wait --pipe --collect \
        --uid=dari --gid=www-data -p SupplementaryGroups=dari \
        --working-directory="$release_path" -p EnvironmentFile=/etc/dari/dari.env \
        "$release_path/.venv/bin/python" "$@"
}

cd "$release_path"
python3.12 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
npm ci
npm run build
chown -R dari:www-data "$release_path"

stage=configuration-check
# Check the same environment used by Gunicorn, without sourcing or printing it.
run_app -c 'import os; assert os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings", "Expected production DJANGO_SETTINGS_MODULE=config.settings"'
run_app manage.py check --deploy --fail-level ERROR

stage=backup
systemctl start dari-backup.service
test "$(systemctl show dari-backup.service -p Result --value)" = success
test "$(systemctl show dari-backup.service -p ExecMainStatus --value)" = 0

stage=migrations
run_app manage.py migrate --noinput
run_app manage.py setup_roles
run_app manage.py collectstatic --noinput

stage=switch
ln -sfn "$old_release" /srv/dari/previous
ln -sfn "$release_path" /srv/dari/current.next
mv -Tf /srv/dari/current.next /srv/dari/current
systemctl restart dari.service
systemctl is-active --quiet dari.service

stage=http-verification
for host in dari-sinergii.ru shop.dari-sinergii.ru; do
    curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 2 \
        --connect-timeout 5 --max-time 15 --retry-max-time 45 "https://$host/health/"
    printf '\n'
    curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 2 \
        --connect-timeout 5 --max-time 15 --retry-max-time 45 \
        --output /dev/null "https://$host/static/admin/css/base.css"
done
trap - ERR
printf '\nUPDATE_OK\nCurrent: %s\nPrevious: %s\n' "$release_path" "$old_release"
