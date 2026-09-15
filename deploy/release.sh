#!/usr/bin/env bash
set -euo pipefail
# Run as root: release.sh <absolute checked-out release directory>.
# Source must be prepared in /srv/dari/releases by the deployment operator.
release_path="$(realpath "${1:?Supply the prepared release directory}")"
case "$release_path" in /srv/dari/releases/*) ;; *) echo 'Release must be under /srv/dari/releases' >&2; exit 1;; esac
test -f "$release_path/manage.py"
test -r /etc/dari/dari.env
test -x /usr/bin/python3.12
# Existing installations may have a useradd-created home with group dari.
# Nginx needs traversal through this parent to reach shared static files.
chgrp www-data /srv/dari
chmod 0750 /srv/dari
cd "$release_path"
test "$(node -p 'Number(process.versions.node.split(".")[0])')" -eq 22
python3.12 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
npm ci
npm run build
chown -R dari:www-data "$release_path"
# systemd parses EnvironmentFile directly, avoiding shell interpretation of secrets.
systemd-run --quiet --wait --pipe --collect --uid=dari --gid=www-data -p SupplementaryGroups=dari --working-directory="$release_path" -p EnvironmentFile=/etc/dari/dari.env "$release_path/.venv/bin/python" manage.py check --deploy
if [ -L /srv/dari/current ]; then
    systemctl start dari-backup.service
    ln -sfn "$(readlink -f /srv/dari/current)" /srv/dari/previous
fi
systemd-run --quiet --wait --pipe --collect --uid=dari --gid=www-data -p SupplementaryGroups=dari --working-directory="$release_path" -p EnvironmentFile=/etc/dari/dari.env "$release_path/.venv/bin/python" manage.py migrate --noinput
systemd-run --quiet --wait --pipe --collect --uid=dari --gid=www-data -p SupplementaryGroups=dari --working-directory="$release_path" -p EnvironmentFile=/etc/dari/dari.env "$release_path/.venv/bin/python" manage.py setup_roles
systemd-run --quiet --wait --pipe --collect --uid=dari --gid=www-data -p SupplementaryGroups=dari --working-directory="$release_path" -p EnvironmentFile=/etc/dari/dari.env "$release_path/.venv/bin/python" manage.py collectstatic --noinput
ln -sfn "$release_path" /srv/dari/current.next
mv -Tf /srv/dari/current.next /srv/dari/current
install -m 0644 deploy/systemd/* /etc/systemd/system/
install -m 0644 deploy/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/dari
ln -sfn /etc/nginx/sites-available/dari /etc/nginx/sites-enabled/dari
nginx -t
systemctl daemon-reload
systemctl enable --now dari.service dari-reconcile.timer dari-notifications.timer dari-backup.timer
systemctl restart dari.service
systemctl reload nginx
curl --fail --retry 5 --retry-delay 2 https://dari-sinergii.ru/health/
curl --fail --retry 5 --retry-delay 2 https://shop.dari-sinergii.ru/health/
# A healthy Django response does not prove Nginx can read collected assets.
for host in dari-sinergii.ru shop.dari-sinergii.ru; do
    curl --fail --silent --show-error --max-time 30 "https://$host/static/admin/css/base.css" >/dev/null
done
