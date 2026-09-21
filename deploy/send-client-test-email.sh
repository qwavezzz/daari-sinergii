#!/usr/bin/env bash
# One explicit recipient; production SMTP, no order creation or queue processing.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    printf 'Run with sudo bash %s\n' "$0" >&2
    exit 1
fi
test -x /srv/dari/current/.venv/bin/python
test -f /srv/dari/current/manage.py

recipient=${1:-}
if [ -z "$recipient" ]; then
    read -r -p 'Email for the test message: ' recipient
fi
test -n "$recipient"

mail_code=$(cat <<'PY'
from uuid import uuid4
from email.utils import parseaddr
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils import timezone
import os

recipient = os.environ["DARI_TEST_EMAIL_TO"].strip()
try:
    validate_email(recipient)
    validate_email(parseaddr(settings.DEFAULT_FROM_EMAIL)[1])
except ValidationError:
    raise SystemExit("EMAIL_TEST_STOPPED: invalid recipient or sender address.")
if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
    raise SystemExit("EMAIL_TEST_STOPPED: SMTP backend is required.")

code = uuid4().hex[:8].upper()
stamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
subject = f"Проверка почты — Дары Синергии — {code}"
body = (
    "Здравствуйте!\n\n"
    "Это контрольное письмо с сайта «Дары Синергии».\n"
    "Оно отправлено из рабочего приложения через SMTP REG.RU.\n\n"
    f"Время проверки: {stamp}\nКонтрольный код: {code}\n\n"
    "Письмо предназначено для проверки доставки уведомлений сайта.\n"
)
try:
    sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
except Exception as error:
    # Report the failure class without leaking credentials or SMTP conversation.
    raise SystemExit(f"EMAIL_TEST_FAILED: {type(error).__name__}") from None
if sent != 1:
    raise SystemExit("EMAIL_TEST_FAILED: SMTP did not accept one message.")
print("MAIL_ACCEPTED:", sent)
print("TEST_CODE:", code)
print("Confirm receipt in the selected mailbox using this code.")
PY
)

systemd-run --quiet --wait --pipe --collect \
    --uid=dari --gid=www-data -p SupplementaryGroups=dari \
    --working-directory=/srv/dari/current \
    -p EnvironmentFile=/etc/dari/dari.env \
    --setenv="DARI_TEST_EMAIL_TO=$recipient" \
    /srv/dari/current/.venv/bin/python manage.py shell -c "$mail_code"
