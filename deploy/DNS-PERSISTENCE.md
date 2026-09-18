# Постоянные DNS для ens3 на VPS

Состояние: постоянный файл установлен и обнаружен networkd. Сразу после reload
интерфейс был `degraded (configuring)` без IPv4, поэтому немедленные DNS-проверки
завершились ошибкой. Последующая внешняя проверка обоих `/health/` дала HTTP 200
с 134.0.113.203. Разработчик затем подтвердил `routable (configured)`, прежний адрес
192.168.0.170/24, шлюз 192.168.0.1 и DNS 1.1.1.1 / 8.8.8.8. Ошибка пришлась на
переходное состояние интерфейса. Повторная проверка с VPS прошла: оба A-запроса
получили 134.0.113.203 с `Data from: network`, оба `/health/` вернули `status=ok`,
HTTP 200 и тот же IP без `--resolve`. После последующей перезагрузки с ядром
6.8.0-139-generic на ens3 сохранились DNS 1.1.1.1 / 8.8.8.8, оба A-запроса из сети
дали 134.0.113.203, оба health HTTP 200. Сохранение настройки после перезагрузки
подтверждено присланным пользователем выводом 18.09.2026.
До reload разработчик прислал networkctl: ens3, адрес 192.168.0.170 по DHCP4,
шлюз 192.168.0.1, DNS 1.1.1.1 / 8.8.8.8, домен поиска msk3.cloud.reg.ru.
Netplan получает конфигурацию из `/etc/netplan/50-cloud-init.yaml` и генерирует
`/run/systemd/network/10-netplan-ens3.network` (полный путь проверяется перед записью).

Исходный DNS 194.58.125.120 возвращал прежний адрес сайта 31.31.197.73 даже после
очистки кэша. После временной смены резолверов обычный curl без --resolve с VPS
получил HTTP 200 и 134.0.113.203. Публичные Google/Cloudflare независимо возвращают
этот актуальный IP для основного домена и магазина.

## Постоянный файл

Шаблон — [90-dari-dns.conf](systemd-networkd/90-dari-dns.conf). Он устанавливается
отдельно от приложения: `release.sh` не копирует каталог systemd-networkd.
Drop-in в `/etc/systemd/network/10-netplan-ens3.network.d/` дополняет генерируемую
конфигурацию. Пустой DNS= очищает её список, затем задаются рабочие адреса.
UseDNS=no запрещает получать другой список от DHCPv4/DHCPv6/IPv6 RA. IP, шлюз,
получение адреса по DHCP и домены поиска остаются в основной конфигурации.
`50-cloud-init.yaml` и файлы в `/run` вручную не изменяются; при переименовании
интерфейса/Netplan ID этот drop-in нужно пересмотреть.

Блок ниже сохранён для первоначальной установки; на этом VPS файл уже создан,
повторять установку не нужно. При первоначальной установке выполнить блок целиком
**на VPS под root**, сохранив открытое SSH-подключение.
При ошибке остановиться и передать вывод. Блок откажется перезаписывать уже
существующий файл. Reload применяет изменённую конфигурацию интерфейса и может
временно убрать DHCP-адрес и маршрут. Поэтому перед DNS-проверкой нужно дождаться
готовности ens3 с IPv4; одного завершения команды reload недостаточно.
При таймауте блок останавливается для диагностики, без повторного reload.

```bash
bash <<'BASH'
set -euo pipefail
test "$(id -u)" -eq 0
test -f /run/systemd/network/10-netplan-ens3.network
test -x /usr/lib/systemd/systemd-networkd-wait-online
dns_file=/etc/systemd/network/10-netplan-ens3.network.d/90-dari-dns.conf
if [ -e "$dns_file" ] || [ -L "$dns_file" ]; then
    printf 'DNS override already exists; stop and inspect it.\n' >&2
    exit 1
fi
install -d -m 0755 /etc/systemd/network/10-netplan-ens3.network.d
(umask 022; set -o noclobber; cat > "$dns_file" <<'DNS'
# Persistent DNS override for ens3; IP/gateway remain managed by Netplan.
[Network]
DNS=
DNS=1.1.1.1 8.8.8.8

[DHCPv4]
UseDNS=no

[DHCPv6]
UseDNS=no

[IPv6AcceptRA]
UseDNS=no
DNS
)
networkctl reload
if ! /usr/lib/systemd/systemd-networkd-wait-online --interface=ens3:routable --ipv4 --timeout=45; then
    networkctl status ens3 --no-pager --full --lines=0
    ip -4 address show dev ens3
    ip -4 route show default
    printf 'IPv4 readiness check failed; stop and inspect. Do not repeat reload.\n' >&2
    exit 1
fi
resolvectl flush-caches
networkctl status ens3 --no-pager --full --lines=0
ip -4 route show default dev ens3
resolvectl query -t A dari-sinergii.ru shop.dari-sinergii.ru
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nMain HTTP %{http_code}; IP %{remote_ip}\n' https://dari-sinergii.ru/health/
curl --noproxy '*' --fail --connect-timeout 5 --max-time 15 -sS -w '\nShop HTTP %{http_code}; IP %{remote_ip}\n' https://shop.dari-sinergii.ru/health/
BASH
```

Ожидаются DNS 1.1.1.1 / 8.8.8.8, прежние IP/шлюз, оба домена с 134.0.113.203 и
оба HTTP 200. `networkctl cat @ens3 --no-pager` показывает объединяемые файлы, если
нужно проверить обнаружение drop-in. Проверка сохранения DNS после перезагрузки
выполнена 18.09.2026 после обновления ОС; результаты приведены в начале документа.
Для приёмки DNS также нужно проверить разрешение mail.hosting.reg.ru при проверке SMTP.

Если установка остановилась сразу после reload, сначала выполнить только чтение:

```bash
networkctl status ens3 --no-pager --full --lines=0
ip -4 address show dev ens3
ip -4 route show default
```

Если IPv4 и маршрут вернулись, повторить только DNS/HTTPS-проверки из блока выше.
Если терминал перестал отвечать, использовать консоль VPS в REG.RU для диагностики.

## Откат только этого дополнения

Если новая постоянная настройка требует отмены, сохранить созданный файл с
расширением, которое networkd не читает, и перечитать настройки. Команды ниже
сохраняют временно работающие публичные DNS; после будущей перезагрузки вернутся
значения из основной конфигурации. Отмена файла не означает устранения старого
ответа DNS провайдера.

```bash
bash <<'BASH'
set -euo pipefail
test "$(id -u)" -eq 0
test -x /usr/lib/systemd/systemd-networkd-wait-online
dns_file=/etc/systemd/network/10-netplan-ens3.network.d/90-dari-dns.conf
test -f "$dns_file"
test ! -e "$dns_file.disabled"
test ! -L "$dns_file.disabled"
mv -- "$dns_file" "$dns_file.disabled"
networkctl reload
if ! /usr/lib/systemd/systemd-networkd-wait-online --interface=ens3:routable --ipv4 --timeout=45; then
    networkctl status ens3 --no-pager --full --lines=0
    ip -4 address show dev ens3
    ip -4 route show default
    printf 'IPv4 readiness check failed; stop and inspect. Do not repeat reload.\n' >&2
    exit 1
fi
resolvectl dns ens3 1.1.1.1 8.8.8.8
resolvectl flush-caches
BASH
```

Если требуется именно исходный список REG.RU, вместо публичных адресов в последнем
шаге задать `194.58.125.120 194.67.94.40`. Предыдущий неактуальный ответ может вернуться.
VPN не отключать, публичную DNS-зону и hosts этим способом не менять.

Источники: [systemd.network: drop-ins, DNS, UseDNS](https://man7.org/linux/man-pages/man5/systemd.network.5.html),
[networkctl: reload](https://man7.org/linux/man-pages/man1/networkctl.1.html),
[ожидание готовности IPv4](https://man7.org/linux/man-pages/man8/systemd-networkd-wait-online.service.8.html).
