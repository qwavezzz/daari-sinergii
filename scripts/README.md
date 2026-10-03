# Вспомогательные команды

Запускайте команды из корня репозитория. Обычные задачи доступны через `package.json`.

| Каталог | Команды и назначение |
| --- | --- |
| `build/` | `npm run build` и `npm run dev`: публичные ресурсы и Vite |
| `pages/` | `npm run build:pages`, `npm run check:pages`: статическая демонстрация и проверка |
| `qa/` | `npm run check:js`, визуальные сравнения и замеры производительности |
| `assets/` | Воспроизводимое кодирование исходников изображений |

## Проверки и замеры

- `node scripts/qa/smoke-shop.mjs` — пустой каталог и корзина при работающем Django на 8000.
- `node scripts/qa/measure-performance.mjs` — замеры Django; вывод в `var/artifacts/performance-after/`.
- `node scripts/pages/measure-performance.mjs` — замеры готовой демонстрации Pages.
- `node scripts/qa/capture-baseline.mjs` — снимки отдельно запущенной эталонной версии.
- `node scripts/qa/verify-landing.mjs` — сравнение эталона и Django; адреса задаются через
  `QA_BASELINE_ORIGIN` и `QA_SITE_ORIGIN`, каталог — через `QA_LANDING_OUTPUT`.
- `.venv/Scripts/python.exe scripts/assets/encode-brand.py` — lossless WebP и размеры логотипа.

Переменная `PERF_OUTPUT` меняет каталог замеров. Скрипты не запускают production-платежи.

## Архив релиза

`python scripts/package-release.py <имя-релиза>` создаёт проверенный архив в `var/releases/`.
В архив входят существующие отслеживаемые исходники; удалённые файлы исключаются.
Для каждого нового файла, ещё не добавленного в Git, требуется явное
`--include относительный/путь` после проверки его содержимого. Секреты, локальные базы,
загруженные пользователями файлы и кэши в архив не включаются.

## GitHub Pages

`pages/build.mjs` запускает Vite с отдельным транспортом навигации, затем `pages/export.py`.
Экспортёр создаёт временную базу, импортирует опубликованный контент и демонстрационные товары,
выдаёт HTML через Django и сохраняет разрешённые статические страницы и файлы.

`PAGES_BASE_PATH` задаёт префикс (по умолчанию `/daari-sinergii/`), `PAGES_ORIGIN` — публичный домен,
`PAGES_PYTHON` — интерпретатор сборки. Проверка запускает `pages/serve.py` на порту 4173;
для проверки публикации задайте `PAGES_TEST_ORIGIN=https://qwavezzz.github.io`.

Браузерный сервер с тестовым ассортиментом находится в `tests/browser/server.py` и запускается
Playwright автоматически. Он не предназначен для редактирования рабочего каталога.
