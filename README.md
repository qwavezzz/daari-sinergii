# Дары Синергии

Один Django-проект: лендинг, библиотека материалов и магазин на `shop.dari-sinergii.ru`.
Требования: [TECHNICAL_SPECIFICATION.md](TECHNICAL_SPECIFICATION.md).
Оформление: [DESIGN.md](DESIGN.md) для лендинга, [DESIGN-SHOP.md](DESIGN-SHOP.md) для магазина.

Подготовка к передаче клиенту: [аудит 18.09.2026](docs/READINESS-AUDIT-2026-09-18.md),
[паспорт доступов](docs/CLIENT-ACCESS.template.md), [руководство владельца](docs/OWNER-GUIDE.md),
[настройка SEO](docs/SEO-SETUP.md), [диагностика VPS и выпуск исправлений](deploy/RELEASE-READINESS.md).
Используемые токены и компоненты магазина описаны в [templates/shop/DESIGN.md](templates/shop/DESIGN.md).

Лендинг сохраняет исходный CSS, DOM сцен, GSAP, SplitText и Lenis. Django выдаёт опубликованный HTML,
HTMX меняет страницы и фрагменты, CSP-сборка Alpine управляет меню, галереей и корзиной.
React в новой сборке отсутствует. JSX в `src/` оставлен только как эталон коммита `8fa57e8`.

## Локальный запуск

Нужны Python 3.12–3.14, Node.js 22 LTS или 24. Проверено на Windows / Python 3.14.6 / Node 24.18.0.
PowerShell, без активации venv и изменения execution policy:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
npm.cmd ci
npm.cmd run build
$env:DJANGO_SETTINGS_MODULE = 'config.settings_dev'
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py import_legacy_content
.venv/Scripts/python.exe manage.py setup_roles
.venv/Scripts/python.exe manage.py createsuperuser
.venv/Scripts/python.exe manage.py runserver 0.0.0.0:8000
```

- [Лендинг](http://localhost:8000/).
- [Материалы](http://localhost:8000/materials/).
- [Магазин](http://shop.localhost:8000/).
- [Админка](http://shop.localhost:8000/admin/).

Chromium распознаёт `shop.localhost` как loopback. Для браузера без такой поддержки потребуется локальное DNS/hosts-сопоставление `127.0.0.1 shop.localhost`.
Один сервер маршрутизирует проверенный Host. Админка доступна только на магазине; cookies не распространяются на родительский домен.

`config.settings_dev` явно включает SQLite в `var/db.sqlite3`; production требует PostgreSQL.
`.env` автоматически не исполняется: задавайте окружение, на сервере используется systemd EnvironmentFile.
Linux/macOS: `.venv/bin/python`, `npm`, `export DJANGO_SETTINGS_MODULE=config.settings_dev`.

После изменения JS/CSS: `npm.cmd run build`. Наблюдение за файлами: `npm.cmd run dev` в отдельном терминале.
Node работает только как сборщик, Django обслуживает готовую сборку.

## Демонстрация на GitHub Pages

Публикуется отдельная статическая версия: лендинг с анимациями, материалы/PDF и 16 вымышленных товаров.
Адреса: `https://qwavezzz.github.io/daari-sinergii/` и каталог `/daari-sinergii/shop/`.
Поддомен `shop.dari-sinergii.ru` относится к будущему серверному запуску.
Pages не запускает Django/PostgreSQL и не используется для настоящих онлайн-продаж.

```powershell
npm.cmd run build:pages
node scripts/verify-pages.mjs
```

Результат: `var/pages-site/`, около 21 МБ. Проверка временно запускает статический сервер на 4173.
`node scripts/verify-pages.mjs` проверяет desktop/mobile, глубокие ссылки, категории, пагинацию,
PDF, анимации, пробную корзину, перезагрузку и режим без JavaScript; запросов записи нет.
`PAGES_BASE_PATH` задаёт путь публикации (по умолчанию `/daari-sinergii/`), `PAGES_ORIGIN` — домен.
Для проверки уже опубликованной версии можно задать `PAGES_TEST_ORIGIN=https://qwavezzz.github.io`.

Сборка создаёт отдельную базу в памяти и временное хранилище; локальная база редактора не читается и не меняется.
В статическую публикацию попадают только исходный опубликованный контент и демонстрационный ассортимент.
CSRF-токены, заказы, админка, база и ключи не экспортируются. Навигация работает обычными страницами;
корзина хранится в localStorage данного браузера, не отправляет заказы и ничего не списывает.
Это отдельный модуль только для Pages; обычная Django-сборка использует серверную корзину.

Workflow `.github/workflows/deploy.yml` сначала проверяет Django/PostgreSQL и frontend,
затем собирает и проверяет демонстрацию и публикует её через GitHub Actions на Pages.

## Наполнение

Импорт переносит 64 текстовых поля, 4 этапа системы, 5 отраслевых сценариев, 8 подборок и 15 PDF.
Повторный импорт не перезаписывает правки редактора. Публикация не требует пересборки.

Пока нет реального ассортимента и доставки, оформление и оплата выключены.
Для локального просмотра добавлены 16 вымышленных товаров: 6 масел, 6 гидролатов, 2 системы для воды и 2 набора.
У каждой позиции есть цена, остаток, описание, характеристики и предметная иллюстрация.
Категории, две страницы каталога и корзина работают на обычных моделях магазина.

```powershell
.venv/Scripts/python.exe manage.py seed_demo_catalog --settings=config.settings_dev
```

Команда работает только при `DEBUG=true`, выключенных `CHECKOUT_ENABLED` и `YOOKASSA_ENABLED`.
Повторный запуск пропускает существующие артикулы `DEMO-001`–`DEMO-016` и сохраняет правки редактора.
Данные находятся в `catalog/demo_data.py`, шесть оптимизированных иллюстраций — в `catalog/demo_assets/`.
Это условная упаковка для визуализации, одинаковая у позиций одного формата; она не подтверждает внешний вид продукции.
Перед наполнением реального каталога демонстрационные позиции следует снять с публикации через Admin
(поиск по `DEMO-`), а категории с адресами `demo-*` деактивировать. Производственный деплой эту команду не вызывает.
В локальном магазине показывается сообщение о демонстрационных данных.

Отзывы появятся после трёх продуктовых направлений при наличии подлинных опубликованных записей.

Перед запуском администратор заполняет товары, артикулы, цены, изображения, остатки, способы получения с явной стоимостью,
условия продажи и политику. Оформление включается в настройках магазина и через `CHECKOUT_ENABLED=true`.
ЮKassa подключается отдельно, сначала с тестовыми ключами; приложение не принимает реквизиты карт.

- [Руководство редактора](content/README.md): контент, документы, видео, отзывы и предпросмотр.
- [Руководство менеджера](orders/README.md): товары, получение, обработка заказов и возвраты.
- [Эксплуатация и платежи](deploy/README.md): Linux, HTTPS, SMTP, ЮKassa, timers, резервные копии и откат.
- [Статус реализации и приёмки](IMPLEMENTATION_STATUS.md).
- [Производительность: до/после и качество изображения](PERFORMANCE_REVIEW.md).

## Проверки

```powershell
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
.venv/Scripts/python.exe manage.py test --settings=config.settings_test
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test
npm.cmd test
npm.cmd run build
npx.cmd playwright install chromium
npm.cmd run test:browser
```

Браузерные тесты используют отдельную базу `var/browser-tests.sqlite3`, которую очищают перед запуском.
Тестовые товары маркированы, в рабочую БД не попадают. Платежи и отправка писем отключены.
Для установленного Chromium можно задать `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.

Конкурентный тест последней единицы требует PostgreSQL и пропускается на SQLite.
CI запускает Python-тесты с PostgreSQL 16, проверяет миграции, сборку, статику и браузерные сценарии.

Для повторного сравнения лендинга соберите отдельную копию коммита `8fa57e8` с его зависимостями
и запустите её на `http://127.0.0.1:5173/daari-sinergii/`. При работающем Django выполните
`node scripts/verify-landing.mjs`; другие адреса задаются через `QA_BASELINE_ORIGIN` и `QA_SITE_ORIGIN`.
Скрипт сохраняет снимки и отчёт в `artifacts/landing-migration/`.

Производительность: `node scripts/measure-performance.mjs` при работающем Django на 8000.
Замеры сохраняются в `artifacts/performance-after/`; другой каталог задаётся через `PERF_OUTPUT`.
`scripts/encode-brand-assets.py` воспроизводит lossless WebP и варианты логотипа из исходных PNG.

## Код и ресурсы

- `content/`, `reviews/` — CMS, импорт и защищённые файлы.
- `catalog/`, `cart/`, `orders/`, `payments/` — магазин и платёжные операции.
- `core/`, `config/` — маршрутизация, права, настройки и политики ответа.
- `templates/site/`, `templates/shop/` — независимые layouts и HTML-фрагменты.
- `frontend/site.js`, `frontend/shop.js` — отдельные сборки; магазин не загружает GSAP/Lenis.
- `static/dist/.vite/manifest.json` — Vite manifest, без повторного хеширования Django.

`scripts/build-assets.mjs` исключает PDF и тяжёлые исходники фотографий из публичной статики.
Документы, изображения контента и товара выдаются после проверки публикации, приватные файлы закрыты Nginx.
Старые `/#/materials/*` переводятся в обычные URL; прежние PDF-адреса сохраняются через таблицу соответствия.

HTMX восстанавливает страницы с сервера без сохранения персональных данных и анимационных обёрток в истории HTML.
Лендинг освобождает сцены перед заменой, затем запускает их и восстанавливает прокрутку.
Метаданные обновляются через `shared/meta.html`.

Production: Ubuntu 24.04 LTS, Python 3.12, PostgreSQL 16, Gunicorn, Nginx, systemd.
Инструкция — [deploy/README.md](deploy/README.md). GitHub Pages публикует только демонстрацию после проверок.
Промышленный деплой Django, DNS и реальные платежи требуют отдельной приёмки.

Документация: [HTMX](https://htmx.org/docs/), [Alpine CSP](https://alpinejs.dev/advanced/csp),
[Vite](https://vite.dev/guide/backend-integration), [Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
