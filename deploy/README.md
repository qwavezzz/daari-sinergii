# Эксплуатация магазина: Альфа-Банк и СДЭК

Уточнённый пункт отправления магазина: `CDEK_FROM_CITY_CODE=431`, `CDEK_FROM_PVZ_CODE=TLT3` (Тольятти, ул. 70 лет Октября, 31а, 105). Эти параметры задаются в `/etc/dari/dari.env` после установки выпуска с поддержкой `CDEK_FROM_PVZ_CODE`; затем нужен перезапуск `dari.service`. Для настоящих запросов калькулятора установите `CDEK_DEMO_QUOTES_ENABLED=false`. Проверка: `manage.py check_cdek_connection --pvz MOS4` с тем же EnvironmentFile, что у приложения. [Результаты проверки и правила упаковки](../docs/PACKING-AND-CDEK.md).

Изменения подготовлены локально. Договоры/API ещё подключаются; продавец и касса пока не определены. Демо-товары сохранены, реальные операции по умолчанию выключены. Список оставшихся данных: [подготовка к запуску](../docs/ALFA-CDEK-READINESS.md).

## Окружение и установка

Рабочая среда: PostgreSQL, Django/Gunicorn за Nginx и HTTPS. Node нужен для сборки. Настройки берутся из окружения; `.env` автоматически не загружается. Заполненный EnvironmentFile хранится вне кода/статики с ограниченными правами, значения секретов не публикуются.

1. Prepare a VPS with SSH, a restricted deployment account, backups, monitoring and DNS for the main and shop hosts. Run `sudo bash deploy/bootstrap.sh`. Install a verified Node.js 22 distribution. Create a dedicated PostgreSQL role/database with no superuser or database-creation rights. Bind PostgreSQL to loopback; close external port 5432.
2. Fill `/etc/dari/dari.env` from `.env.example`. Keep `DJANGO_SETTINGS_MODULE=config.settings` explicit: management commands without a settings selection default to local development. Generate a random Django secret. Keep the file `root:dari`, mode `0640`, outside releases and static directories. `EnvironmentFile` does not execute shell substitutions; use proper systemd quoting for JSON. Never commit the completed file.
3. Configure PostgreSQL backup access through `PGSERVICE`, `PGSERVICEFILE` and a private `PGPASSFILE` (mode `0600`). The service file identifies the same database as `DATABASE_URL`. Set these environment variables for `dari-backup.service` in the env file. Credentials are not passed as shell command arguments.
   All application units and transient management commands use `SupplementaryGroups=dari` in addition to `Group=www-data`. This grants traversal of `/etc/dari` (`root:dari`, `0750`) and access to its service file (`root:dari`, `0640`), while preserving Nginx access to the Gunicorn socket. The password file must belong to `dari` with mode `0600`. For manual `systemd-run --uid=dari --gid=www-data` commands, include `-p SupplementaryGroups=dari` as well.
4. Obtain a Let's Encrypt certificate for all three configured names (main, www, shop). Use a temporary HTTP-only ACME virtual host before installing the final TLS config. Disable Ubuntu's example default server so there is exactly one `default_server` per listening address/port. The supplied configuration uses `listen 443 ssl http2`, compatible with Ubuntu's Nginx 1.24.
5. Prepare an immutable checkout in `/srv/dari/releases/<release-id>`, then run `sudo bash deploy/release.sh /srv/dari/releases/<release-id>`. The script creates the venv, installs locked dependencies, builds assets, checks production settings, backs up an existing installation, migrates, installs roles, collects static files, switches the release and verifies both hosts. Do not run migration procedures concurrently.
6. On the initial release run `manage.py import_legacy_content` with the production environment to import original content and protected documents, then create a superuser. Both commands must run under the `dari` account and the same environment (`systemd-run` pattern in `release.sh`). Do not place admin/session cookies on a shared parent domain.

Перед выпуском проверьте резервную копию и возможность восстановления в отдельную БД. Выполните сборку `npm run build`, `manage.py check`, миграции и `collectstatic` под рабочим окружением, затем проверьте оба домена. Не запускайте `scripts/browser_server.py` на рабочей базе: это отдельный стенд, который очищает только свою тестовую базу. Сохраняйте существующие файлы окружения и пользовательские загрузки.

В репозитории остались конфигурации `nginx.conf`, `dari-proxy.conf` и systemd units. Старые bootstrap/release/backup shell-скрипты отсутствуют; перед эксплуатацией проверьте пути ExecStart у установленных служб, в частности резервного копирования. Этот раздел не запускает публикацию или изменение сервера.

## Подключение оплаты

1. Получите тестовые реквизиты прямого REST-эквайринга Альфа-Банка. Укажите `ALFABANK_USERNAME`, `ALFABANK_PASSWORD`; оставьте `ALFABANK_TEST_MODE=true`, включите `ALFABANK_ENABLED` только на тестовом стенде.
2. Согласуйте callback `https://shop.dari-sinergii.ru/payments/alfabank/webhook/`. Уведомление лишь запускает авторизованную сверку. Возврат браузера сам по себе не доказывает оплату.
3. Банк получает сохранённый итог заказа в копейках: товары плюс доставка. Стабильный `orderNumber` соответствует сохранённой попытке. После таймаута статус запрашивается по номеру, новая независимая операция не создаётся.
4. Проверьте успешную/отменённую оплату, потерю ответа, повтор нажатия, поздний callback, частичный и полный возврат. `getOrderStatusExtended.do` должен возвращать версию ответа 03 с `paymentAmountInfo`, включая списанную и возвращённую сумму.
5. Настройте и проверьте кассовые чеки. `ALFABANK_RECEIPT_MODE=bank` формирует банковскую корзину с товарами и доставкой; нужны согласованные ставки и `ALFABANK_TAX_SYSTEM`. `external` означает отдельно работающую и согласованную кассу, этот проект её не подключает. Факт включения флага не подтверждает отправку чека.
6. После приёмки переключите учётные данные и режим, подтвердите `ALFABANK_LIVE_APPROVED`. Нельзя проводить реальные платежи за демо-товары. Старые платёжные попытки сохраняются как `legacy` и не направляются в новый банк.

Возвраты выполняются в кабинете Альфа-Банка. Сверка импортирует подтверждённую накопленную сумму возвратов. Администратор не может вручную объявить заказ оплаченным. Физический возврат товара на склад — отдельное действие.

## Подключение СДЭК

Отправка — Тольятти. Укажите `CDEK_CLIENT_ID`, `CDEK_CLIENT_SECRET`, `CDEK_FROM_CITY_CODE` из справочника СДЭК. Карта использует OpenStreetMap; ключ Яндекс Карт не нужен. Для рабочего договора нужен `CDEK_TEST_MODE=false`; до проверки оставьте `CDEK_ENABLED=false`.

В Admin добавьте способ типа `cdek_pvz`, выберите тариф для фактической передачи перевозчику (сдача в ПВЗ или забор курьером) и налоговую ставку доставки. Подтвердите замеры товаров, коробок и проверенных комбинаций упаковки. Расчёт сравнивает допустимые варианты грузовых мест с учётом ограничений ПВЗ. Правила подготовки данных — в [PACKING-AND-CDEK.md](../docs/PACKING-AND-CDEK.md).

Карта Leaflet/OpenStreetMap выбирает ПВЗ; собственный сервер получает данные пункта и рассчитывает цену. Клиентская цена не принимается. Цена и срок действуют ограниченное время (`CDEK_QUOTE_TTL_SECONDS`, по умолчанию 900 секунд) и связаны с составом корзины, упаковками, тарифом и ПВЗ. При ошибке нельзя подставлять бесплатную доставку.

Накладная оформляется **вручную после подтверждённой оплаты** по снимку доставки в заказе. Проверьте вес/места, тариф, получателя и код ПВЗ. Если доставка оплачена в составе заказа, не назначайте повторную оплату доставки или наложенный платёж покупателю. Передайте трек-номер покупателю, затем переведите заказ в передачу в доставку.

## Документы и проверка готовности

`manage.py setup_customer_pages --dry-run --refresh-defaults` показывает безопасное обновление стандартных текстов. Уберите `--dry-run` после просмотра; редакторские правки требуют ручной актуализации. Существующие реквизиты нужно подтвердить: заполненное поле не доказывает актуальность продавца.

`manage.py check_store_readiness` — проверка заполнения, без сети и изменений. `--strict` даёт ненулевой код при пробелах. Она не заменяет проверку юридических текстов, договоров, налогов, чеков и решение банка.

Для заказов требуются `CHECKOUT_ENABLED=true` и включение в Admin. До повторной заявки нужны реальные описания и ассортимент, реквизиты продавца, доставка со сроком передачи перевозчику и сроком в пути, порядок оплаты/возвратов, политика и применимые документы продукции. Демо-каталог подходит для тренировки.

## Регулярные задачи

`dari-reconcile.timer` запускает `reconcile_payments`: авторизованная сверка платежей/возвратов и освобождение резервов без неопределённых платежей. Сверка не создаёт платёж за покупателя. Неопределённая попытка удерживает резерв и требует выяснения результата; не создавайте замену до проверки.

`dari-notifications.timer` отправляет устойчивую очередь уведомлений. Настройте SMTP/адрес отправителя в окружении; менеджера и Reply-To можно задать в Admin. `manage.py send_notifications --check` проверяет заполнение без отправки. Обычный SMTP не гарантирует отсутствие дубликата при потере ответа.

Проверяйте HTTPS и продление сертификата, состояние служб/timers, дисковое место, резервные копии, заказы «требует внимания» и неотправленные уведомления. В логах не должны появляться реквизиты карт, секреты API или полные тела запросов с персональными данными. Обработка и хранение данных должны соответствовать опубликованным условиям.

Источники: [подключение и требования Альфа-Банка](https://alfabank.ru/sme/payservice/internet-acquiring/docs/process/), [REST API](https://alfabank.ru/sme/payservice/internet-acquiring/docs/connection-options/api/rest/), [официальный виджет СДЭК](https://github.com/cdek-it/widget), [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
