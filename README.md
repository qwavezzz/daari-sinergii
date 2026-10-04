# Дары Синергии

Лендинг, материалы и интернет-магазин в одном Django-проекте.
Сервер: Django / PostgreSQL / Gunicorn / Nginx. Интерфейс: Django Templates, HTMX и Alpine.js.
Vite собирает JavaScript/CSS; GSAP и Lenis управляют анимациями лендинга.

## Структура

| Каталог | Назначение |
| --- | --- |
| `apps/` | Django-приложения, их миграции и серверные тесты |
| `config/` | Настройки окружений, маршрутизация доменов и WSGI |
| `frontend/` | Точки входа `site.js` и `shop.js`, стили, анимации, общие компоненты и деморежим |
| `templates/` | Шаблоны лендинга, магазина и общие фрагменты |
| `public/` | Готовые публичные изображения, видео и иконки |
| `assets/` | Исходники изображений и PDF для первоначального наполнения CMS |
| `scripts/` | Сборка, экспорт Pages, проверка качества и подготовка ресурсов |
| `tests/` | Браузерные сценарии и модульные JavaScript-тесты |
| `deploy/` | Установка на VPS, Nginx, systemd, выпуск и резервные копии |
| `docs/` | Руководства, архитектура, статус запуска и отчёты |
| `var/` | Локальная база, загрузки, сборки, кеши и результаты проверок; исключён из Git |

`node_modules/` и `.venv/` — локальные зависимости. `.agents/` и `.impeccable/` содержат
инструменты и настройки работы с дизайном, в приложение не включаются.

Один Django-проект: лендинг, библиотека материалов и магазин на `shop.dari-sinergii.ru`.
Требования: [TECHNICAL_SPECIFICATION.md](TECHNICAL_SPECIFICATION.md).
Оформление: [DESIGN.md](DESIGN.md) для лендинга, [DESIGN-SHOP.md](DESIGN-SHOP.md) для магазина.

Подготовка к эквайрингу: [Альфа-Банк, СДЭК и оставшиеся данные](docs/STORE-LAUNCH.md).
Эксплуатация: [настройки и порядок подключения](deploy/README.md).
Используемые токены и компоненты магазина описаны в [templates/shop/DESIGN.md](templates/shop/DESIGN.md).
Выбор ПВЗ и настройки бесплатной карты: [СДЭК на OpenStreetMap](docs/CDEK-OSM.md).

Лендинг сохраняет исходный CSS, DOM сцен, GSAP, SplitText и Lenis. Django выдаёт опубликованный HTML,
HTMX меняет страницы и фрагменты, CSP-сборка Alpine управляет меню, галереей и корзиной.
React в новой сборке отсутствует. Исходный JSX доступен в истории, в коммите `8fa57e8`.

## Локальный запуск

Нужны Python 3.12–3.14 и Node.js 22 или 24. Команды PowerShell из корня проекта:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
npm.cmd ci
npm.cmd run build
python manage.py migrate
python manage.py import_legacy_content
python manage.py setup_roles
python manage.py createsuperuser
python manage.py runserver
```

- Лендинг: <http://localhost:8000/>.
- Материалы: <http://localhost:8000/materials/>.
- Магазин: <http://shop.localhost:8000/>.
- Админка: <http://shop.localhost:8000/admin/> — только на домене магазина.

Готовых логина и пароля нет: их задаёт команда `createsuperuser`. Если браузер не распознаёт
`shop.localhost`, добавьте локальное сопоставление `127.0.0.1 shop.localhost` в hosts.
На Linux/macOS используйте `.venv/bin/python` и `npm` вместо Windows-команд.

Все команды `python manage.py ...` по умолчанию используют локальные настройки и одну базу
`var/db.sqlite3`. При запуске системным Python `manage.py` сам использует установленное окружение
`.venv`; активация не требуется. Явные `--settings` и `DJANGO_SETTINGS_MODULE` сохраняют приоритет.
На сервере задаётся `DJANGO_SETTINGS_MODULE=config.settings` в EnvironmentFile; WSGI также
использует production-настройки. Установку зависимостей нужно выполнить один раз по инструкции
выше. Остановка сервера — `Ctrl+C`.

Для тестового Альфа-Банка и реальных писем локально используется закрытый файл `var/local-settings.json`.
Получение доступов, настройка и проверка описаны в [инструкции по интеграциям](docs/STORE-LAUNCH.md).
При локальном `runserver` настроенные платежи и письма обрабатываются в фоне каждые 15 секунд.

После изменения фронтенда выполните `npm.cmd run build`; для непрерывной пересборки —
`npm.cmd run dev` в отдельном терминале. Node.js нужен для сборки; страницы обслуживает Django.

Для локальной проверки ПВЗ СДЭК и пробного заказа после миграций выполните
`python manage.py setup_working_checkout`: команда добавит способ СДЭК и учебные упаковки демотоваров.
Условия запуска и настройки описаны в [CDEK-OSM.md](docs/CDEK-OSM.md).

## Наполнение и демонстрация

`import_legacy_content` читает проверенные JSON из `apps/content/data/` и 15 PDF из
`assets/documents/`. Повторный импорт сохраняет правки редактора.

Для просмотра магазина можно добавить 16 вымышленных товаров:

```powershell
python manage.py seed_demo_catalog
```

Команда доступна только локально, при выключенных оформлении и оплате. Перед реальными продажами
демотовары `DEMO-*` и категории `demo-*` нужно снять с публикации и заполнить настоящий ассортимент.

Отдельная статическая демонстрация для GitHub Pages:

```powershell
npm.cmd run build:pages
npm.cmd run check:pages
```

Результат — `var/pages-site/`. Экспорт использует временную базу, не читает базу редактора,
не публикует админку и не принимает заказы. Корзина демонстрации хранится в браузере.
GitHub Actions проверяет проект и публикует только эту демонстрацию.

Первый перевозчик — СДЭК, отправка из Тольятти. На оформлении покупатель выбирает ПВЗ,
сервер проверяет его и рассчитывает тариф по весу и размерам упаковок. Итог товаров и доставки
сохраняется в заказе и передаётся Альфа-Банку в копейках. Изменение корзины, пункта или тарифа
требует нового расчёта. Накладную менеджер оформляет вручную после подтверждения оплаты.

Оба сервиса ещё подключаются; реальные платежи по умолчанию выключены. Демо-товары остаются.
Перед запуском нужно определить продавца и схему чеков, заполнить реквизиты, реальные товары,
упаковки и документы, получить доступы сервисов и проверить тестовую оплату с доставкой.
Секреты задаются в окружении по именам из `.env.example`, а не в коде и не в чате.

```powershell
.venv/Scripts/python.exe manage.py migrate --settings=config.settings_dev
.venv/Scripts/python.exe manage.py setup_customer_pages --dry-run --refresh-defaults --settings=config.settings_dev
.venv/Scripts/python.exe manage.py check_store_readiness --settings=config.settings_dev
```

`setup_customer_pages --refresh-defaults` обновляет только распознанные стандартные тексты;
сначала просмотрите `--dry-run`. Редакторские правки сохраняются. Проверка готовности ничего
не отправляет во внешние сервисы; `--strict` возвращает ошибку при незаполненных пунктах.
Оформление включается двумя переключателями: настройкой магазина и `CHECKOUT_ENABLED=true`.
Альфа-Банк подключается отдельно, сначала в тестовой среде; приложение не принимает реквизиты карт.

- [Подготовка и приёмка магазина](docs/STORE-LAUNCH.md): реальные товары, доставка, оплата и письма.
- [Эксплуатация и платежи](deploy/README.md): Linux, HTTPS, SMTP, Альфа-Банк, timers, резервные копии и откат.
- [Спецификация интеграций](.scratch/store-launch-20261004/spec.md) и [ход работы](PROGRESS.md).

## Проверки

```powershell
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
.venv/Scripts/python.exe manage.py test --settings=config.settings_test
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test
npm.cmd run check:js
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
```

Для браузерных проверок нужен Chromium: `npx.cmd playwright install chromium`.
Уже установленный Chromium можно указать через `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.
Сценарии используют отдельные базу, загрузки и порт (`BROWSER_TEST_PORT`, по умолчанию 8001).
Занятый порт вызывает ошибку вместо подключения к чужому серверу. В браузерном
стенде магазин использует 127.0.0.1, лендинг — localhost.
Банковский переход с подменой API: `BROWSER_TEST_BANK=1 npm run test:browser`;
учебная доставка: `BROWSER_TEST_DEMO_QUOTES=1 npm run test:browser`.
В PowerShell задайте флаг через `$env:BROWSER_TEST_BANK="1"`, затем удалите после прогона. Проверка конкурентной покупки последней единицы
требует PostgreSQL и пропускается на SQLite; CI настроен на PostgreSQL 16.

## Документация

- [Подготовка магазина, приёмка и оставшиеся внешние условия](docs/STORE-LAUNCH.md).
- [Установка, обновление, таймеры, резервные копии и восстановление](deploy/README.md).
- [Упаковки и СДЭК](docs/PACKING-AND-CDEK.md), [карта ПВЗ](docs/CDEK-OSM.md).
- [Данные от владельца](CLIENT_QUESTIONS.txt).
- [Продукт](PRODUCT.md), [дизайн магазина](templates/shop/DESIGN.md), [техническое задание](TECHNICAL_SPECIFICATION.md).
- [Исторические отчёты и референсы вне поставки приложения](archive/README.md).

Миграции, `assets/documents/`, защищённые учебные режимы и экспорт Pages сохраняются.
Данные, загрузки и приватные настройки в `var/` не являются материалом для общей очистки.
