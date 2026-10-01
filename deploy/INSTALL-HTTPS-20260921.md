# Включение короткой политики HSTS

Релиз `https-20260921` добавляет управление областью HSTS. Его установка сама
по себе не включает HSTS: `HSTS_SECONDS` остаётся прежним.

Установка подтверждена разработчиком. На 21 сентября, 11:21:56 UTC, публично
проверены HTTP 200 у главной, магазина и обоих health; HSTS включён со сроком
300 секунд без includeSubDomains/preload. Первоначальный срок 30 секунд исправлен;
включение завершено. Блок установки ниже повторять не нужно. GitHub CI коммита `53940bf`
завершился успешно; архив собран из того же кода, последующие изменения — документы.

## 1. Установить обновление

Скопировать через Remote Explorer два локальных файла из `artifacts/releases/`
в `/root/` на VPS:

- `dari-https-20260921.tar.gz`;
- `dari-https-20260921.tar.gz.sha256`.

Выполнить блок в терминале VPS под root. Он рассчитан на установленный
`seo-20260921`, сохранит конфигурацию и окружение в закрытую папку, сделает
штатный бэкап и обновит приложение. Перезапуск даёт краткий перерыв в работе.

```bash
bash <<'BASH'
set -euo pipefail
umask 0022
trap 'printf "\nHTTPS_DEPLOY_STOPPED (line %s)\n" "$LINENO" >&2' ERR
release_dir=/srv/dari/releases/https-20260921
old_release=/srv/dari/releases/seo-20260921
config_backup=/root/dari-https-config-20260921
test "$(id -u)" -eq 0
test "$(readlink -f /srv/dari/current)" = "$old_release"
cd /root
sha256sum -c dari-https-20260921.tar.gz.sha256
mkdir -m 0755 "$release_dir"
tar --no-same-owner -xzf dari-https-20260921.tar.gz -C "$release_dir"
cd "$release_dir"
sha256sum --check --quiet SHA256SUMS
diff --strip-trailing-cr --brief deploy/nginx.conf /etc/nginx/sites-available/dari
diff --strip-trailing-cr --brief deploy/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
for unit in dari.service dari-backup.service dari-backup.timer dari-notifications.service dari-notifications.timer dari-reconcile.service dari-reconcile.timer; do
    diff --strip-trailing-cr --brief "deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
nginx -t
mkdir -m 0700 "$config_backup"
cp -p /etc/dari/dari.env "$config_backup/dari.env"
cp -p /etc/nginx/sites-available/dari "$config_backup/nginx.conf"
cp -p /etc/nginx/snippets/dari-proxy.conf "$config_backup/dari-proxy.conf"
bash deploy/release.sh "$release_dir"
test "$(readlink -f /srv/dari/current)" = "$release_dir"
printf '\nHTTPS_RELEASE_OK\n'
BASH
```

Если блок остановился, сохранить последние строки ошибки и проверить
`readlink -f /srv/dari/current` и `systemctl is-active dari.service nginx.service`.
Повторять установку в уже созданный каталог не нужно.

## 2. Включить HSTS после успешного теста Certbot

Результат `certbot renew --cert-name dari-sinergii.ru --dry-run --run-deploy-hooks
--non-interactive` должен подтверждать успешное продление. Активный таймер
сам по себе не заменяет этот тест. Подробнее: [HTTPS и мониторинг](HTTPS-AND-MONITORING.md).

Открыть существующий файл окружения на VPS:

```bash
sudo nano /etc/dari/dari.env
```

Найти существующие строки HSTS и заменить их значениями ниже; отсутствующую
строку добавить. Для каждого имени оставить одну строку. Остальной файл
сохранить. Содержимое с паролями не присылать в чат.

```dotenv
HSTS_SECONDS=300
HSTS_INCLUDE_SUBDOMAINS=false
```

В nano: `Ctrl+O`, `Enter`, `Ctrl+X`. Затем выполнить:

У `check --deploy` при этой политике ожидаются предупреждения `security.W005`
и `security.W021`: охват всех поддоменов и preload сознательно выключены.
Они не останавливают блок. Не включать эти параметры только ради удаления
предупреждений; другие ошибки разбирать отдельно.

```bash
bash <<'BASH'
set -euo pipefail
test "$(readlink -f /srv/dari/current)" = /srv/dari/releases/https-20260921
systemd-run --quiet --wait --pipe --collect \
    --uid=dari --gid=www-data -p SupplementaryGroups=dari \
    --working-directory=/srv/dari/current -p EnvironmentFile=/etc/dari/dari.env \
    /srv/dari/current/.venv/bin/python manage.py check --deploy
systemctl restart dari.service
for host in dari-sinergii.ru shop.dari-sinergii.ru; do
    printf '\n%s\n' "$host"
    curl --noproxy '*' --fail --silent --show-error --retry 5 --retry-connrefused \
        --retry-delay 2 --connect-timeout 5 --max-time 15 --retry-max-time 45 \
        -D - "https://$host/health/"
done
BASH
```

У обоих доменов ожидаются HTTP 200, `{"status": "ok"}` и заголовок
`Strict-Transport-Security: max-age=300` без `includeSubDomains` и `preload`.
Проверку повторно выполнит агент снаружи после сообщения об установке.

Локально прошли 15 тестов `core`, Ruff и проверка синтаксиса четырёх блоков Bash.
Архив собран из коммита `fa894a4`, содержит 349 файлов, размер 37,16 МиБ.
SHA256: `5ff40ccb8b45decc526ab6c9da344e0cc2a1773818aa03a401dcf2bb9dbb0fcb`.
После сборки уточнён только этот локальный документ; архив не пересоздавался.

## Если после изменения сайт перестал отвечать

Для возврата окружения и кода к состоянию перед этим выпуском выполнить:

```bash
bash <<'BASH'
set -euo pipefail
test "$(readlink -f /srv/dari/current)" = /srv/dari/releases/https-20260921
test -x /srv/dari/releases/seo-20260921/.venv/bin/python
test -f /root/dari-https-config-20260921/dari.env
cp -p /root/dari-https-config-20260921/dari.env /etc/dari/dari.env
cp -p /root/dari-https-config-20260921/nginx.conf /etc/nginx/sites-available/dari
cp -p /root/dari-https-config-20260921/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
nginx -t
ln -sfn /srv/dari/releases/seo-20260921 /srv/dari/current.rollback
mv -Tf /srv/dari/current.rollback /srv/dari/current
systemctl restart dari.service
systemctl reload nginx
curl --noproxy '*' --fail --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 5 --max-time 15 --retry-max-time 45 https://dari-sinergii.ru/health/
curl --noproxy '*' --fail --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 5 --max-time 15 --retry-max-time 45 https://shop.dari-sinergii.ru/health/
BASH
```

Откат не стирает заказы и не восстанавливает БД. Возврат старого env рассчитан
на немедленный откат этого выпуска; если позже в нём менялись другие настройки,
сначала сохранить эти изменения. Короткая политика в уже посетившем сайт браузере
может сохраняться до пяти минут после последнего заголовка HSTS.
