#!/usr/bin/env bash
# Enable demo-only checkout on the existing VPS; keep HTTPS and DEBUG=false.
set -euo pipefail
umask 0022
test "$(id -u)" -eq 0
exec 9>/run/lock/dari-release.lock
flock -n 9
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
sha256sum --check rehearsal-setup.sha256
release_dir="$(readlink -e /srv/dari/current)"
case "$release_dir" in /srv/dari/releases/*) ;; *) echo 'Unexpected release path' >&2; exit 1;; esac
test -f "$release_dir/frontend/cdek-map.js"
test -f "$release_dir/apps/payments/trial.py"
test -f "$release_dir/config/cdek_sandbox.py"
test -x "$release_dir/.venv/bin/python"
test -f /etc/dari/dari.env
test ! -L /etc/dari/dari.env
systemctl is-active dari.service
systemctl start dari-backup.service
test "$(systemctl show dari-backup.service -p Result --value)" = success
backup_dir="$(mktemp -d /root/dari-before-rehearsal-XXXXXXXX)"
chmod 0700 "$backup_dir"
cp -p /etc/dari/dari.env "$backup_dir/dari.env"
runtime_dir="$(mktemp -d /srv/dari/shared/rehearsal-setup-XXXXXXXX)"
chown root:www-data "$runtime_dir"
chmod 0750 "$runtime_dir"
install -m 0640 -o root -g www-data configure_rehearsal.py "$runtime_dir/configure_rehearsal.py"
restore_environment() {
    trap - ERR
    cp -p "$backup_dir/dari.env" /etc/dari/dari.env
    systemctl restart dari.service || true
    printf '\nREHEARSAL_STOPPED. Previous environment restored. Demo database setup may already be committed; do not restore the whole database blindly. Backup: %s\n' "$backup_dir" >&2
    exit 1
}
trap restore_environment ERR
python3 "$runtime_dir/configure_rehearsal.py" environment --release "$release_dir"
run_app() {
    systemd-run --quiet --wait --pipe --collect --uid=dari --gid=www-data -p SupplementaryGroups=dari --working-directory="$release_dir" -p EnvironmentFile=/etc/dari/dari.env "$release_dir/.venv/bin/python" "$@"
}
run_app "$runtime_dir/configure_rehearsal.py" check --release "$release_dir"
run_app manage.py check --deploy --fail-level ERROR
run_app manage.py check_cdek_connection --pvz TLT8 --tariff 136
run_app "$runtime_dir/configure_rehearsal.py" database --release "$release_dir"
systemctl restart dari.service
curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 5 --max-time 15 https://shop.dari-sinergii.ru/health/
curl --fail --silent --show-error --retry 3 --connect-timeout 5 --max-time 15 --output "$runtime_dir/shop.html" https://shop.dari-sinergii.ru/
grep -q 'Пробная оплата без списания денег' "$runtime_dir/shop.html"
trap - ERR
printf '\nREHEARSAL_READY\nPrevious environment: %s/dari.env\n' "$backup_dir"
