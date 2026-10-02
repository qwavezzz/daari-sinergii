# Обновление упаковки и расчёта СДЭК на существующем VPS

GitHub и VPS обновляются отдельно. Эта инструкция рассчитана на уже установленный магазин: Ubuntu 24.04, Python 3.12, Node.js 22, PostgreSQL, `dari.service`, рабочий `dari-backup.service`, окружение `/etc/dari/dari.env`, текущий релиз `/srv/dari/current` и общие файлы `/srv/dari/shared`.

## Установка из GitHub

В терминале VPS перейдите в root (`sudo -i`, если вошли другим пользователем). Подставьте полный SHA опубликованного коммита вместо `COMMIT_SHA`; это фиксирует конкретную проверенную версию. Если репозиторий закрытый, используйте уже настроенный SSH URL или GitHub-аутентификацию, не вставляйте токены в URL команды.

```bash
bash <<'BASH'
set -euo pipefail
umask 0022
test "$(id -u)" -eq 0
commit=COMMIT_SHA
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
release_dir="/srv/dari/releases/packing-${commit:0:12}"
test ! -e "$release_dir"
git clone --branch main --single-branch \
  https://github.com/qwavezzz/daari-sinergii.git "$release_dir"
git -C "$release_dir" checkout --detach "$commit"
test "$(git -C "$release_dir" rev-parse HEAD)" = "$commit"
bash "$release_dir/deploy/update-app.sh" "$release_dir"
BASH
```

`update-app.sh` собирает приложение в новом каталоге, проверяет production-окружение, запускает штатный бэкап, применяет миграции и роли, собирает статику, переключает ссылку релиза и перезапускает Gunicorn. Затем проверяет оба health URL и доступность CSS. При перезапуске возможен короткий перерыв.

Скрипт не заменяет Nginx, EnvironmentFile или systemd units; не включает и не выключает таймеры, оплату и отправку писем; не запускает импорт каталога, обновление SEO или заполнение учебными данными. В успешном выводе будет `UPDATE_OK`. Новые миграции этой функции: `catalog/0004`, `orders/0007`, `orders/0008`; команда `migrate` сама применит недостающие зависимости.

## После установки

```bash
readlink -f /srv/dari/current
systemctl is-active dari.service nginx.service
curl -fsS https://dari-sinergii.ru/health/
curl -fsS https://shop.dari-sinergii.ru/health/
```

В админке появятся коробки, схемы упаковки и инструкции сборки заказа. SQLite с компьютера не переносится: локальные 569 учебных схем и замеры не попадут в PostgreSQL от одного обновления кода. `seed_demo_shipping` специально запрещён на VPS. Внесите данные по [инструкции упаковки](../docs/PACKING-AND-CDEK.md). Для рабочего СДЭК нужны реальные подтверждённые замеры; само обновление кода не делает их подтверждёнными и не переключает режим API.

Новая версия подписи потребует пересчёта доставки у покупателей с открытой старой страницей оформления. Сохранённые заказы сохраняют свои планы.

## Если установка остановилась

Не повторяйте весь блок клонирования в тот же каталог. Сначала проверьте стадию ошибки, текущую ссылку и журнал:

```bash
readlink -f /srv/dari/current
systemctl status dari.service --no-pager
journalctl -u dari.service -n 80 --no-pager
```

При ошибке после переключения можно вернуть предыдущее приложение следующей командой. Для этого выпуска миграции добавляют поля и таблицы; откат приложения не требует удаления этих данных. После будущих изменений схемы совместимость нужно оценить заново.

```bash
bash <<'BASH'
set -euo pipefail
test "$(id -u)" -eq 0
exec 9>/run/lock/dari-release.lock
flock -n 9
previous="$(readlink -e /srv/dari/previous)"
case "$previous" in /srv/dari/releases/*) ;; *) exit 1;; esac
test -x "$previous/.venv/bin/gunicorn"
ln -sfn "$previous" /srv/dari/current.rollback
mv -Tf /srv/dari/current.rollback /srv/dari/current
systemctl restart dari.service
systemctl is-active dari.service
curl -fsS https://shop.dari-sinergii.ru/health/
BASH
```

Базу автоматически назад не восстанавливать: после обновления в ней могли появиться заказы. Резервные копии находятся в `/srv/dari/backups`; восстановление БД требует отдельного решения.
