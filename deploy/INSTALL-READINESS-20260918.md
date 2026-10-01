# Установка подготовленного выпуска 18.09.2026

**Историческая инструкция.** После выпуска HTTPS-релиза и очистки 21 сентября
старые `email-76d6352` и `readiness-20260918` удалены. Команды ниже не предназначены
для повторного запуска. Актуальная пара релизов и откат описаны в
[INSTALL-HTTPS-20260921.md](INSTALL-HTTPS-20260921.md).

Разработчик подтвердил новый SSH-вход, успешный запуск резервного копирования
(`Result=success`, `ExecMainStatus=0`), загрузку архива в `/root` и проверку его
контрольной суммы. Исходный релиз — `/srv/dari/releases/email-76d6352`, Node.js 22.23.2.
Обновление уже выполнено: `/srv/dari/current` указывает на `readiness-20260918`,
обе службы active. Исходный скрипт остановился на первом HTTP-запросе после
перезапуска с `curl: (7)`; последующие локальная и внешняя проверки дали HTTP 200.
Публичные страницы, SEO-заголовки и статические файлы проверены отдельно.
Ниже сохранены команды выполненного выпуска. Повторно запускать блок не нужно.

Повторный запрос к публичному домену с VPS снова дал curl 7 / HTTP 000. Диагностика
показала старый адрес 31.31.197.73 в локальном DNS-кэше (Data from: cache), при этом
HTTPS с принудительным IP 134.0.113.203 успешен. Локальной записи домена в /etc/hosts
не найдено. После очистки кэша старый IP снова пришёл с Data from: network.
Исходный DNS ens3 — 194.58.125.120, второй настроенный — 194.67.94.40.
Google и Cloudflare дают A=134.0.113.203 для обоих доменов; расхождение на стороне
используемого VPS DNS-пути подтверждено. После предложенной временной замены DNS
обычный запрос без --resolve вернул `status=ok`, HTTP 200 и IP 134.0.113.203.
Доступ с VPS по домену восстановлен временной настройкой. Постоянный DNS drop-in
затем установлен, но сразу после reload DNS-проверки попали на `configuring` без IPv4.
Снаружи оба сайта после этого ответили HTTP 200. Разработчик подтвердил восстановление
прежних адреса/маршрута и `routable (configured)` с публичными DNS. Повтор с VPS
также прошёл: оба A-запроса дали 134.0.113.203 с `Data from: network`, оба `/health/`
без `--resolve` — `status=ok`, HTTP 200 и актуальный IP. Проверка после перезагрузки
ещё не проводилась. См. [текущее состояние DNS](DNS-PERSISTENCE.md).
VPN не отключать; переустановка приложения не требуется.

## Проверка временной замены DNS на VPS

Следующий блок меняет только список DNS-серверов ens3 в работающем systemd-resolved,
очищает кэш и проверяет оба сайта. Он не перезапускает сетевой интерфейс и не
изменяет публичную зону REG.RU. Домены маршрутизации DNS сохраняются. Настройка
временная: после DHCP-обновления, перенастройки интерфейса или перезагрузки исходные
параметры могут вернуться; для постоянного исправления нужно проверить источник
сетевой конфигурации. Успех обычного HTTPS основного сайта после этого шага подтверждён;
вывод проверки shop отдельно не прислан. Повторять временную смену сейчас не требуется.

```bash
sudo resolvectl dns ens3 1.1.1.1 8.8.8.8
sudo resolvectl flush-caches
resolvectl query -t A dari-sinergii.ru shop.dari-sinergii.ru
curl --noproxy '*' --connect-timeout 5 --max-time 15 -sS -w '\nMain HTTP %{http_code}; IP %{remote_ip}\n' https://dari-sinergii.ru/health/
curl --noproxy '*' --connect-timeout 5 --max-time 15 -sS -w '\nShop HTTP %{http_code}; IP %{remote_ip}\n' https://shop.dari-sinergii.ru/health/
```

Ожидаются A=134.0.113.203 и HTTP 200 для обоих доменов. Если новый DNS недоступен
или перестали разрешаться другие необходимые имена, вернуть известные исходные
адреса, не меняя домены маршрутизации:

```bash
sudo resolvectl dns ens3 194.58.125.120 194.67.94.40
sudo resolvectl flush-caches
```

После проверки определить постоянную конфигурацию интерфейса; не заменять вслепую
netplan/cloud-init и не использовать netplan apply до разбора действующей схемы.
Полученный networkctl подтвердил Netplan/networkd, DHCP4 и рабочие DNS; найден
`/etc/netplan/50-cloud-init.yaml`. Подготовлена
[инструкция постоянного DNS](DNS-PERSISTENCE.md) через отдельный networkd drop-in.
Её выполнение ещё не подтверждено.
Для определения источника настроек запрошены только сведения об интерфейсе и имена
файлов, без содержимого VPN-конфигураций:

```bash
networkctl status ens3 --no-pager
sudo find /etc/netplan /etc/systemd/network /etc/systemd/resolved.conf.d -maxdepth 1 -type f -printf '%p\n' 2>/dev/null
```

Поведение команд: [resolvectl](https://man7.org/linux/man-pages/man1/resolvectl.1.html).

## Выпуск

Выполнить блок целиком в **терминале VPS под root**. Сборка занимает несколько минут;
при переключении приложения возможна краткая недоступность. Не закрывать SSH до
завершения. Блок намеренно завершается при первой ошибке, включая отличия действующих
Nginx/systemd-файлов: в этом случае передать вывод, не повторять блок автоматически.
Новый каталог создаётся без перезаписи существующего релиза.

```bash
bash <<'BASH'
set -euo pipefail
umask 0022
trap 'printf "\nDEPLOY_STOPPED (line %s)\n" "$LINENO" >&2' ERR
release_dir=/srv/dari/releases/readiness-20260918
test "$(id -u)" -eq 0
test "$(readlink -f /srv/dari/current)" = /srv/dari/releases/email-76d6352
cd /root
sha256sum -c dari-readiness-20260918.tar.gz.sha256
mkdir -m 0755 "$release_dir"
tar --no-same-owner -xzf dari-readiness-20260918.tar.gz -C "$release_dir"
cd "$release_dir"
sha256sum --check --quiet SHA256SUMS
diff --strip-trailing-cr --brief deploy/nginx.conf /etc/nginx/sites-available/dari
diff --strip-trailing-cr --brief deploy/dari-proxy.conf /etc/nginx/snippets/dari-proxy.conf
for unit in dari.service dari-backup.service dari-backup.timer dari-notifications.service dari-notifications.timer; do
    diff --strip-trailing-cr --brief "deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
nginx -t
bash deploy/release.sh "$release_dir"
test "$(readlink -f /srv/dari/current)" = "$release_dir"
systemctl is-active dari.service nginx.service
.venv/bin/python -c 'import PIL; print("Pillow:", PIL.__version__)'
printf '\nRELEASE_OK\n'
BASH
```

`RELEASE_OK` означает завершение скрипта, работающие службы и успешные HTTP-проверки
обоих `/health/` и admin CSS, встроенные в `release.sh`. Затем нужны проверки
индексации, заголовков PDF, входа в админку и деморежима по инструкции аудита.
Предупреждение Django `security.W004` о выключенном HSTS ожидается на этом этапе;
его включение требует отдельной проверки используемых поддоменов.

Файл `/etc/dari/dari.env` остаётся действующим. При отсутствии новых переменных код
использует `SITE_INDEXING_ENABLED=true`, `SHOP_INDEXING_ENABLED=false`; такие значения
соответствуют согласованной индексации. Явно записать их в env можно отдельно, без
замены файла шаблоном. Параметры SMTP, SSH, платежей и доставки этот блок не меняет.
Состояние платёжного таймера обычный выпуск сохраняет. Новых миграций БД в этом
выпуске нет; штатный скрипт всё равно проверяет и применяет ожидающие миграции.

Сравнение файлов перед выпуском не является полной проверкой Nginx includes или
systemd drop-ins. Оно предотвращает перезапись отличающихся основных файлов
действующей установки без разбора этих отличий.

## Если скрипт завершился ошибкой

Сохранить последние строки вывода и проверить, успела ли переключиться ссылка:

```bash
readlink -f /srv/dari/current
systemctl is-active dari.service nginx.service
```

Если ссылка всё ещё указывает на `email-76d6352`, новый код ещё не активирован.
Не менять env, не удалять каталоги и не повторять установку до разбора ошибки.

Если новый код уже активирован и сайт не работает, для этого выпуска без новых
миграций возможен откат к известному предыдущему коду:

```bash
bash <<'BASH'
set -euo pipefail
test "$(readlink -f /srv/dari/current)" = /srv/dari/releases/readiness-20260918
test -x /srv/dari/releases/email-76d6352/.venv/bin/python
ln -sfn /srv/dari/releases/email-76d6352 /srv/dari/current.rollback
mv -Tf /srv/dari/current.rollback /srv/dari/current
systemctl restart dari.service
curl --fail --retry 5 --retry-delay 2 --max-time 30 https://dari-sinergii.ru/health/
curl --fail --retry 5 --retry-delay 2 --max-time 30 https://shop.dari-sinergii.ru/health/
BASH
```

Это откат кода. Он не восстанавливает и не перезаписывает рабочую БД или загруженные
файлы. Целостность backup, копия вне VPS и пробное восстановление остаются отдельными
задачами приёмки.
