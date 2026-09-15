#!/usr/bin/env bash
set -euo pipefail
# Run as root on Ubuntu 24.04 LTS; never resets an existing database or env file.
test "$(id -u)" -eq 0
apt-get update
apt-get install -y python3.12 python3.12-venv postgresql-16 postgresql-client-16 nginx certbot curl ca-certificates git
id dari >/dev/null 2>&1 || useradd --system --home /srv/dari --create-home --shell /bin/bash dari
usermod -a -G www-data dari
install -d -o dari -g www-data -m 0750 /srv/dari /srv/dari/releases /srv/dari/shared /srv/dari/shared/media /srv/dari/shared/private-media /srv/dari/shared/static /srv/dari/backups
install -d -o root -g dari -m 0750 /etc/dari
install -d -m 0755 /var/www/letsencrypt
if [ ! -e /etc/dari/dari.env ]; then
    install -o root -g dari -m 0640 .env.example /etc/dari/dari.env
fi
echo 'Install Node.js 22 LTS from a verified distribution. Configure PostgreSQL role/database, /etc/dari/dari.env, DNS and certificates before release.'
