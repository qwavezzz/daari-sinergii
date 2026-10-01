# Установка SEO-обновления от 21 сентября 2026

**Историческая инструкция.** После установки HTTPS-релиза и очистки VPS старый
`readiness-20260918` удалён. Повторять установку или откат ниже сейчас нельзя;
актуальная пара — `https-20260921` / `seo-20260921`. Порядок отката этой пары —
в [INSTALL-HTTPS-20260921.md](INSTALL-HTTPS-20260921.md).

Подготовлен отдельный релиз `seo-20260921`. GitHub push обновляет репозиторий
и демонстрацию Pages, но не Django на VPS. Команды ниже рассчитаны на переход
с `readiness-20260918`.

После сообщения разработчика об установке публичная проверка подтвердила новые
страницы, микроразметку, canonical PDF, sitemap и noindex магазина. Повторять
установку для этой проверки не нужно. Результаты — в отчёте об исправлениях.

## 1. Загрузить два файла

Через Remote Explorer скопировать из локальной папки `artifacts/releases/`
в `/root/` на VPS:

- `dari-seo-20260921.tar.gz`;
- `dari-seo-20260921.tar.gz.sha256`.

## 2. Установить одним блоком

Выполнить в терминале **VPS под root**. Сборка занимает несколько минут;
перезапуск приложения может дать краткий перерыв. SSH оставить открытым.
Скрипт проверяет целостность архива, сохраняет конфигурацию Nginx, делает
штатный бэкап и устанавливает обновление. При ошибке остановится.

```bash
bash <<'BASH'
set -euo pipefail
umask 0022
trap 'printf "\nSEO_DEPLOY_STOPPED (line %s)\n" "$LINENO" >&2' ERR
release_dir=/srv/dari/releases/seo-20260921
old_release=/srv/dari/releases/readiness-20260918
config_backup=/root/dari-seo-config-20260921
test "$(id -u)" -eq 0
test "$(readlink -f /srv/dari/current)" = "$old_release"
cd /root
sha256sum -c dari-seo-20260921.tar.gz.sha256
mkdir -m 0755 "$release_dir"
tar --no-same-owner -xzf dari-seo-20260921.tar.gz -C "$release_dir"
cd "$release_dir"
sha256sum --check --quiet SHA256SUMS
# Do not silently overwrite configuration edited directly on the VPS.
diff --strip-trailing-cr --brief "$old_release/deploy/nginx.conf" /etc/nginx/sites-available/dari
diff --strip-trailing-cr --brief deploy/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
for unit in dari.service dari-backup.service dari-backup.timer dari-notifications.service dari-notifications.timer dari-reconcile.service dari-reconcile.timer; do
    diff --strip-trailing-cr --brief "deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
nginx -t
mkdir -m 0700 "$config_backup"
cp -p /etc/nginx/sites-available/dari "$config_backup/nginx.conf"
cp -p /etc/nginx/snippets/dari-proxy.conf "$config_backup/dari-proxy.conf"
bash deploy/release.sh "$release_dir"
test "$(readlink -f /srv/dari/current)" = "$release_dir"
printf '\nSEO_RELEASE_OK\n'
BASH
```

При `SEO_RELEASE_OK` уже проверены оба `/health/` и доступность статических
файлов. Предупреждение Django о HSTS ожидаемо при прежнем `HSTS_SECONDS=0`.
Платёжные настройки, SMTP, SSH и VPN этот выпуск не меняет.

Команда обновления контента выводит, что создано, обновлено или пропущено.
`ПРОПУСК — редакторские изменения` означает, что собственный текст клиента
сохранён. Не нужно запускать старый импорт с перезаписью или сбрасывать базу.
Новых миграций схемы в выпуске нет; изменяются только совпадающие с исходным
импортом тексты и ссылки. Новая страница создаётся, если её адрес свободен.

## 3. Проверить результат

Открыть основной сайт и `/materials/water-systems/`. В материалах должны
появиться хлебные крошки. Если адрес был занят или страница ранее переименована,
уточнить её URL в разделе «Подборки» админки по выводу установки.

В терминале проверить два заголовка:

```bash
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -D - -o /dev/null 'https://dari-sinergii.ru/documents/oil-guide/?download=1'
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sSI https://shop.dari-sinergii.ru/
```

У PDF ожидается `Link: <https://dari-sinergii.ru/documents/oil-guide/>; rel="canonical"`.
Для PDF нужен GET: обработчик не поддерживает HEAD (`curl -I` вернёт 405).
У магазина — `X-Robots-Tag: noindex, nofollow`. Проверить вход в админку и
содержание новых текстов. Sitemap основного сайта обновляется из опубликованных
подборок автоматически; адрес карты остаётся `/sitemap.xml`.

## Если установка остановилась

Сохранить последние строки ошибки и выполнить:

```bash
readlink -f /srv/dari/current
systemctl is-active dari.service nginx.service
```

Не повторять весь блок вслепую: каталог релиза уже мог быть создан, а ссылка —
переключена. Если остановка произошла на сравнении конфигурации, сначала сравнить
эти изменения; новые настройки VPS не заменять автоматически.

Если ссылка уже указывает на новый релиз и сайт перестал работать, откат кода
и сохранённого Nginx для этого выпуска:

```bash
bash <<'BASH'
set -euo pipefail
test "$(readlink -f /srv/dari/current)" = /srv/dari/releases/seo-20260921
test -x /srv/dari/releases/readiness-20260918/.venv/bin/python
test -f /root/dari-seo-config-20260921/nginx.conf
test -f /root/dari-seo-config-20260921/dari-proxy.conf
cp -p /root/dari-seo-config-20260921/nginx.conf /etc/nginx/sites-available/dari
cp -p /root/dari-seo-config-20260921/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
nginx -t
ln -sfn /srv/dari/releases/readiness-20260918 /srv/dari/current.rollback
mv -Tf /srv/dari/current.rollback /srv/dari/current
systemctl restart dari.service
systemctl reload nginx
curl --noproxy '*' --fail --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 5 --max-time 15 --retry-max-time 45 https://dari-sinergii.ru/health/
curl --noproxy '*' --fail --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 5 --max-time 15 --retry-max-time 45 https://shop.dari-sinergii.ru/health/
BASH
```

Откат не восстанавливает БД: новые тексты совместимы с прежним кодом. Заказы и
редакторские изменения после установки не стираются. Восстановление БД из
резервной копии — отдельная операция, без необходимости её не выполнять.

Полный состав изменений: [SEO-FIXES-2026-09-21.md](../docs/SEO-FIXES-2026-09-21.md).
