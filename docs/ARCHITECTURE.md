# Архитектура проекта

## Сервер

Один Django-процесс обслуживает основной домен и домен магазина. `config/settings*.py`
задаёт окружение; `apps/core/middleware.py` выбирает `config/main_urls.py` либо
`config/shop_urls.py` по проверенному Host. Админка и корзина доступны на домене магазина.

| Приложение | Ответственность |
| --- | --- |
| `apps/core` | Маршрутизация, политики ответа, права, аудит, общие template tags |
| `apps/content` | Тексты, материалы, документы, видео, импорт, закрытое хранилище |
| `apps/reviews` | Публикация отзывов и связи с товарами и направлениями |
| `apps/catalog` | Категории, товары, цены, остатки, характеристики и изображения |
| `apps/cart` | Корзина сессии, изменение количества и вычисление итогов |
| `apps/orders` | Оформление, резервирование, исполнение заказов и очередь писем |
| `apps/payments` | ЮKassa, проверка платежей, возвраты и периодическая сверка |

В каждом приложении `models.py` описывает данные, `views.py` — HTTP-обработчики,
`services.py` при наличии — операции предметной области, `admin.py` — управление,
`tests.py` — серверные проверки. Миграции и management-команды остаются рядом со своим приложением.
Новые модули добавляются по конкретной ответственности.

Импорты используют полный пакет, например `from apps.catalog.models import Product`.
Идентификаторы Django остаются прежними: `catalog`, `orders`, `content` и т. д.
Они явно закреплены через `AppConfig.label`; ссылки моделей `catalog.Product`, права,
таблицы, зависимости и имена миграций не переименованы. В старых миграциях изменены
только пути импортируемых Python-функций и классов. Перенос пакетов не требует миграции данных.

Локально используется `var/db.sqlite3`; production требует PostgreSQL.
`.env` не загружается автоматически. Локально поддерживаются переменные окружения и
`var/local-settings.json` (только для `config.settings_dev`, с приоритетом окружения).
На сервере используется systemd EnvironmentFile вне каталога релиза.

Все команды `python manage.py ...` по умолчанию выбирают локальные настройки `config.settings_dev`
и проектную `.venv`, если запущены системным Python. Активированное окружение не заменяется.
Так `createsuperuser`, `migrate` и `runserver` работают с одной локальной базой.
Явные настройки окружения и `--settings` имеют приоритет. На сервере EnvironmentFile задаёт
`DJANGO_SETTINGS_MODULE=config.settings`; WSGI также запускается с production-настройками.

## Интерфейс

- `frontend/site.js` — лендинг и библиотека материалов.
- `frontend/shop.js` — каталог, корзина и оформление заказа.
- `frontend/landing/` — загрузчик, видео, меню и сцены GSAP/Lenis.
- `frontend/shared/` — навигация, компоненты контента, количество в корзине и определение браузера.
- `frontend/demo/` — корзина и транспорт только для статической демонстрации.
- `frontend/styles/` — стили лендинга, материалов, магазина и CMS-блоков.

HTML расположен в `templates/site/`, `templates/shop/` и `templates/shared/`.
Шаблон специального поля админки принадлежит `apps/content/templates/content/`.
HTMX меняет страницы и фрагменты; Alpine управляет локальным состоянием компонентов.
Магазин не импортирует GSAP/Lenis. Геометрия и поведение анимаций при рефакторинге сохранены.

## Ресурсы и сборка

```text
public/ ── npm run build ──> var/build/static/ ── collectstatic ──> STATIC_ROOT
frontend/ ───── Vite ──────> var/build/static/dist/
assets/documents/ ── import_legacy_content ──> PRIVATE_MEDIA_ROOT + записи CMS
```

`public/` содержит только готовые публичные файлы. Оригиналы изображений хранятся
в `assets/source/`, PDF для первого импорта — в `assets/documents/`.
Публикация загруженных документов и изображений проверяется Django; исходники не копируются в статику.
URL `/static/dist/` сохранён, хотя каталог сборки теперь находится внутри `var/build/`.
Манифест Vite читает `apps/core/templatetags/vite.py`; повторного хеширования Django нет.

Сборка очищает только свой каталог `var/build/static/`. `STATIC_ROOT`, база и загрузки
не являются промежуточными файлами сборки. В production хранилища задаются через
окружение и находятся вне каталога сменяемого релиза; пример — `.env.example`.

Pages собирается отдельно в `var/build/pages/`, затем экспортируется в `var/pages-site/`.
Экспорт использует базу в памяти и временное хранилище. Данные рабочей базы в Pages не попадают.

## Проверки и локальные данные

Серверные тесты находятся рядом с Django-приложениями; JavaScript-тесты — в `tests/unit/`,
браузерные — в `tests/browser/`. `tests/browser/server.py` наполняет только отдельную
базу `var/browser-tests.sqlite3`. Для проверки PostgreSQL используется CI.

Снимки и отчёты записываются в `var/artifacts/`, Playwright traces — в `var/test-results/`,
кеш Ruff — в `var/cache/ruff/`. Старые локальные разовые инструменты переноса сохранены
в `var/archive/migration-tools/`; они не входят в репозиторий и не нужны для сборки.
Папку `var/` нельзя удалять целиком: вместе с результатами проверок в ней находятся база и загрузки.

## Карта прежних путей

| Прежний путь | Текущий путь |
| --- | --- |
| `core/`, `catalog/`, `orders/` и остальные Django-приложения | `apps/<имя>/` |
| `src/styles.css`, `src/materials.css` | `frontend/styles/landing.css`, `frontend/styles/materials.css` |
| `src/platform.js` | `frontend/shared/platform.js` |
| `src/platform.test.js` | `tests/unit/platform.test.js` |
| `src/*.jsx`, `src/motion.js`, `src/materials.js`, `index.html` | Удалены из рабочей версии; доступны в Git, эталон `8fa57e8` |
| `content/extract_legacy_data.mjs` | Разовый извлекатель удалён; проверенные JSON сохранены в `apps/content/data/` |
| `public/documents/`, `Official Docs/` | `assets/documents/`; побайтовые дубликаты объединены |
| `public/assets/photos/source/`, исходный логотип в корне | `assets/source/photos/`, `assets/source/brand/` |
| `static/` | `var/build/static/` |
| `artifacts/`, `test-results/` | `var/artifacts/`, `var/test-results/` |
| Отчёты и инструкции в корне и приложениях | `docs/`; инструкция эксплуатации остаётся в `deploy/` |

`DESIGN.md`, `DESIGN-SHOP.md` и `TECHNICAL_SPECIFICATION.md` остаются в корне без изменений.
`PRODUCT.md` остаётся продуктовым контекстом; `.agents/` и `.impeccable/` — конфигурацией инструментов дизайна.
