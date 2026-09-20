# Обновления ОС на VPS

Состояние на 2026-09-18: подключение `noble-security` подтверждено загрузкой индексов
с `security.ubuntu.com`. Симуляция `apt-get -s --with-new-pkgs upgrade`:
211 обновлений, 8 новых пакетов, 0 удалений и 0 оставленных без обновления.
Новое ядро — `6.8.0-139-generic`. Обновлены OpenSSH, systemd/resolved, Netplan,
cloud-init и общие библиотеки. Ошибок APT в присланном выводе нет.
Результат сохранён в `artifacts/readiness/apt-security-simulation.json`.
Пользователь прислал окончание установки с `UPGRADE_FINISHED` и сообщением
needrestart о старых процессах в сеансах root (VS Code, SSH, Screen, user manager).
Блок завершился без остановки по ошибке. Пользователь подтвердил наличие
`/boot/vmlinuz-6.8.0-139-generic` (15M) и `/boot/initrd.img-6.8.0-139-generic` (18M),
оба `/health/` вернули `status=ok`, HTTP 200; показано `System restart required`.
`dpkg --audit` не вывел проблем; повторная симуляция APT дала 0 обновлений,
0 новых пакетов, 0 удалений, 0 оставленных без обновления. Список failed units пуст.
Приложение, Nginx, PostgreSQL, networkd и resolved активны и включены в автозапуск.
`ssh.service` активен/disabled, `ssh.socket` активен/enabled — автозапуск SSH через
сокет настроен. **Перезагрузка и применение нового ядра подтверждены.**
После повторного входа пользователь прислал ядро 6.8.0-139-generic, failed units 0,
dari/nginx/postgresql/ssh.socket active. UFW сохранил правила 22/80/443 для IPv4/IPv6.
На ens3 сохранились DNS 1.1.1.1 и 8.8.8.8; оба A-запроса из сети вернули
134.0.113.203, оба health — status=ok/HTTP 200. Notifications, backup и Certbot
имеют следующие запуски. Это проверка таймеров, а не доставки/восстановления/продления.

Парольный вход root по SSH сохраняется по решению разработчика. VPN не отключать.
Рабочий DNS задан в `/etc/systemd/network/10-netplan-ens3.network.d/90-dari-dns.conf`.
Обновления выполняются в пределах Ubuntu 24.04, без `do-release-upgrade`.

## Установка по проверенному плану

Блок установки уже выполнен до `UPGRADE_FINISHED`; повторно его не запускать.
Ниже сохранён порядок проведённого обслуживания.

Выделить время на обслуживание: обновления могут перезапускать службы и временно
прервать работу сайта/соединение. Оставить действующее SSH-подключение открытым;
иметь доступ к консоли VPS в панели REG.RU для восстановления доступа при необходимости.
Запустить на VPS:

```bash
sudo screen -S dari-os-update
```

Если показана заставка Screen, закрыть её Enter. Затем внутри Screen выполнить
следующий блок. В отличие от `bash <<...`, `bash -c` оставляет терминал доступным
для интерактивных вопросов APT и установки пакетов.

```bash
sudo bash -c '
set -euo pipefail
umask 077
backup_dir=$(mktemp -d /root/dari-before-os-update.XXXXXX)
tar -czf "$backup_dir/config.tar.gz" -C / \
  etc/ssh etc/netplan etc/systemd/network etc/systemd/system \
  etc/ufw etc/apt etc/nginx etc/dari
dpkg-query -W > "$backup_dir/packages.tsv"
uname -r > "$backup_dir/kernel.txt"
systemctl start dari-backup.service
/usr/sbin/sshd -t
nginx -t
printf "Configuration backup: %s\n" "$backup_dir"
apt-get --with-new-pkgs --no-remove upgrade
printf "\nUPGRADE_FINISHED\n"
'
```

Блок останавливается при ошибке резервирования, проверок или установки. Каталог
резервной копии доступен только root; архив содержит секреты `/etc/dari` и SSH-ключи
сервера, его не отправлять в чат и не помещать в репозиторий. Это локальная копия
конфигурации, а не полный снимок ОС и не проверка восстановления данных.

При ожидаемом плане 211 обновлений/8 новых/0 удалений подтвердить APT ответом `Y`.
Если план отличается, сначала разобрать изменения. При вопросе о замене изменённого
конфигурационного файла выбрать сохранение установленной локальной версии:
`keep the local version currently installed` либо `N` для соответствующего
вопроса dpkg. Особенно важно сохранить SSH и сеть. Другие вопросы разбирать по тексту,
не отвечать `N` на любые запросы подряд. Автоматические перезапуски служб возможны
также из сценариев пакетов; не обещать отсутствие простоя.

Если соединение разорвалось, после повторного SSH-входа вернуть существующий сеанс:

```bash
sudo screen -D -r dari-os-update
```

Не запускать вторую установку параллельно первой и не удалять lock-файлы APT/dpkg.
При ошибке сохранить вывод. `autoremove` и перезагрузка в этот шаг не входят.

## Проверка после завершения установки

Команды ниже только проверяют состояние. Даже `UPGRADE_FINISHED` не заменяет их:
при отказе пользователя от подтверждения APT может завершиться с кодом 0.

```bash
sudo dpkg --audit
sudo apt-get check
sudo apt-get -s --with-new-pkgs upgrade
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T | awk '$1 ~ /^(permitrootlogin|passwordauthentication|pubkeyauthentication|port)$/ {print}'
sudo nginx -t
systemctl show dari.service nginx.service postgresql.service ssh.service ssh.socket systemd-networkd.service systemd-resolved.service --no-pager -p Id -p ActiveState -p SubState -p UnitFileState
systemctl --failed --no-pager
sudo ufw status verbose
networkctl status ens3 --no-pager --full --lines=0
resolvectl query -t A dari-sinergii.ru shop.dari-sinergii.ru
uname -r
ls -lh /boot/vmlinuz-6.8.0-139-generic /boot/initrd.img-6.8.0-139-generic
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nMain HTTP %{http_code}; IP %{remote_ip}\n' https://dari-sinergii.ru/health/
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nShop HTTP %{http_code}; IP %{remote_ip}\n' https://shop.dari-sinergii.ru/health/
if [ -f /run/reboot-required ]; then cat /run/reboot-required; fi
```

Проверить вход отдельным новым SSH-сеансом, сохранив старый. После анализа вывода
назначить перезагрузку для применения нового ядра; она потребует временной
недоступности сервера. До перезагрузки проверить отсутствие ошибок пакетов,
наличие ядра/initramfs, включение необходимых служб и доступ к консоли REG.RU.
После неё повторить DNS, SSH, firewall, health-проверки, проверить `uname -r`,
таймеры резервирования/уведомлений и очередь писем. Ядро, DNS, службы, firewall,
health и таймеры уже проверены после перезагрузки 18.09.2026; повторная проверка
очереди писем после неё отдельно не проводилась.

## Перезагрузка после полученных проверок

Перезагрузка выполнена, результаты приведены в начале документа. Команды ниже
сохранены как проведённая процедура; повторять перезагрузку сейчас не нужно.
Перед перезагрузкой проверяется новый парольный вход: из отдельного PowerShell на компьютере
выполнить `ssh root@134.0.113.203`, сохранив старый сеанс. Если вход не работает,
не переходить к перезагрузке, сначала разобрать ошибку через действующее подключение.
Подготовить доступ к консоли VPS в REG.RU.

Только после успешного нового входа, в новом серверном сеансе выполнить:

```bash
sudo reboot
```

SSH-соединения завершатся, сайт будет временно недоступен. Через 1–2 минуты
попробовать подключиться снова. Если сервер не вернулся, использовать консоль
REG.RU для диагностики, не запускать повторные принудительные перезагрузки.

После повторного SSH-входа проверить:

```bash
uname -r
systemctl --failed --no-pager
systemctl is-active dari.service nginx.service postgresql.service ssh.socket
sudo ufw status verbose
resolvectl status ens3 --no-pager
resolvectl query -t A dari-sinergii.ru shop.dari-sinergii.ru
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nMain HTTP %{http_code}\n' https://dari-sinergii.ru/health/
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nShop HTTP %{http_code}\n' https://shop.dari-sinergii.ru/health/
systemctl list-timers --all --full --no-pager dari-backup.timer dari-notifications.timer certbot.timer
```

Ожидаются ядро `6.8.0-139-generic`, пустой список failed units, active служб,
активный UFW с разрешёнными 22/80/443, DNS 1.1.1.1 и 8.8.8.8, A-записи обоих
доменов 134.0.113.203, два HTTP 200 с `status=ok`, следующие запуски трёх таймеров.
Все перечисленные результаты получены от пользователя после перезагрузки 18.09.2026.

Источники: [APT](https://manpages.debian.org/bookworm/apt/apt-get.8.en.html),
[перезапуски служб в Ubuntu 24.04](https://discourse.ubuntu.com/t/needrestart-changes-in-ubuntu-24-04-service-restarts/44671),
[активация SSH через сокет](https://discourse.ubuntu.com/t/sshd-now-uses-socket-based-activation-ubuntu-22-10-and-later/30189),
[GNU Screen](https://www.gnu.org/software/screen/manual/html_node/Overview.html).
