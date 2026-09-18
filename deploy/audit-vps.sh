#!/usr/bin/env bash
# Read-only diagnosis. No package updates, restarts, mail, firewall changes or env dumps.
set -uo pipefail
# Remote Explorer terminals are interactive: never pause the audit in a pager.
export SYSTEMD_PAGER=cat SYSTEMD_COLORS=0
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run with sudo bash deploy/audit-vps.sh'; exit 1
fi

echo '== OS and capacity =='
lsb_release -ds
df -h / /srv/dari
free -h
echo '== Listening TCP sockets =='
ss -lnt
echo '== Firewall =='
ufw status verbose
echo '== Effective SSH policy (no keys) =='
/usr/sbin/sshd -T | awk '$1 ~ /^(permitrootlogin|passwordauthentication|pubkeyauthentication|maxauthtries|port)$/ {print}'
echo '== Services (no journal / environment) =='
systemctl --no-pager show dari.service nginx.service postgresql.service \
    -p Id -p ActiveState -p SubState -p User -p Group -p NoNewPrivileges -p ProtectSystem
systemctl list-timers --all --full dari-backup.timer dari-notifications.timer dari-reconcile.timer certbot.timer --no-pager
echo '== Configuration permissions (not content) =='
stat -c '%a %U:%G %n' /etc/dari /etc/dari/dari.env /etc/dari/pgpass /etc/dari/pg_service.conf
echo '== Nginx syntax =='
nginx -t
echo '== Certificate dates =='
openssl x509 -in /etc/letsencrypt/live/dari-sinergii.ru/fullchain.pem -noout -dates
echo '== Backup dates and sizes (not content) =='
find /srv/dari/backups -maxdepth 2 -type f -name database.dump -printf '%TY-%Tm-%Td %TH:%TM %s bytes\n' | sort | tail -n 7
echo '== Package versions =='
/srv/dari/current/.venv/bin/python -m pip list --format=columns --disable-pip-version-check
echo '== Django deployment checks =='
systemd-run --quiet --wait --pipe --collect \
    --uid=dari --gid=www-data -p SupplementaryGroups=dari \
    --working-directory=/srv/dari/current -p EnvironmentFile=/etc/dari/dari.env \
    /srv/dari/current/.venv/bin/python manage.py check --deploy
echo '== SMTP configuration validation (does not connect or send) =='
systemd-run --quiet --wait --pipe --collect \
    --uid=dari --gid=www-data -p SupplementaryGroups=dari \
    --working-directory=/srv/dari/current -p EnvironmentFile=/etc/dari/dari.env \
    /srv/dari/current/.venv/bin/python manage.py send_notifications --check
echo '== Read-only application inventory; no customer data or secret values =='
systemd-run --quiet --wait --pipe --collect \
    --uid=dari --gid=www-data -p SupplementaryGroups=dari \
    --working-directory=/srv/dari/current -p EnvironmentFile=/etc/dari/dari.env \
    /srv/dari/current/.venv/bin/python manage.py shell -c '
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from catalog.models import Product
from orders.models import Notification, StoreSettings
from orders.services import checkout_is_enabled
from django.utils import timezone
store = StoreSettings.objects.first()
data = {
    "debug": settings.DEBUG,
    "checkout_enabled": checkout_is_enabled(),
    "payment_enabled": settings.YOOKASSA_ENABLED,
    "hsts_seconds": settings.SECURE_HSTS_SECONDS,
    "site_indexing_gate": getattr(settings, "SITE_INDEXING_ENABLED", "not deployed"),
    "shop_indexing_gate": getattr(settings, "SHOP_INDEXING_ENABLED", "not deployed"),
    "smtp_host": settings.EMAIL_HOST,
    "smtp_port": settings.EMAIL_PORT,
    "smtp_tls": settings.EMAIL_USE_TLS,
    "smtp_ssl": settings.EMAIL_USE_SSL,
    "smtp_user_set": bool(settings.EMAIL_HOST_USER),
    "smtp_password_set": bool(settings.EMAIL_HOST_PASSWORD),
    "from_set": bool(settings.DEFAULT_FROM_EMAIL),
    "demo_products_published": Product.objects.filter(status="published", sku__startswith="DEMO-").count(),
    "privacy_text_present": bool(store and store.privacy_text.strip()),
    "terms_text_present": bool(store and store.terms_text.strip()),
    "pending_mail": Notification.objects.filter(sent_at__isnull=True, skipped_at__isnull=True).count(),
    "mail_with_errors": Notification.objects.filter(sent_at__isnull=True, skipped_at__isnull=True).exclude(last_error="").count(),
    "active_superusers": get_user_model().objects.filter(is_active=True, is_superuser=True).count(),
    "checked_at": timezone.now().isoformat(),
}
print(json.dumps(data, ensure_ascii=False, indent=2))
'
echo '== Finished. Errors above mean a check is incomplete, not that the server passed. =='
