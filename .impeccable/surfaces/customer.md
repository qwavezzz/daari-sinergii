---
version: 1
slug: "customer"
primary_target: "templates/customer/content.html"
related_targets: ["templates/customer/page.html", "templates/customer/links.html", "templates/customer/seller.html", "frontend/customer.css", "templates/customer/DESIGN.md", "templates/customer/.impeccable/design.json"]
---

# Customer surface

## Mode

Read.

## Purpose and scope

Покупатель изучает условия обработки данных, покупки, доставки и оплаты, возврата, находит контакты и реквизиты, читает ответы и открывает оригиналы деклараций. Семь страниц доступны на основном сайте и в магазине: privacy, terms, delivery/payment, returns, contacts/requisites, documents, FAQ.

## Direction and constraints

Узкое расширение существующего сайта. Общий шаблон сохраняет оболочку текущего домена; фактические визуальные правила зафиксированы в [templates/customer/DESIGN.md](../../templates/customer/DESIGN.md). Первый экран содержит шапку, хлебные крошки, название страницы и начало содержания. На широком экране разделы находятся слева; на телефоне они следуют после текста. Отличительный элемент — последовательно организованные сведения и прямой доступ к источнику или контакту.

Страница документов публикует три предоставленные декларации с регистрационными сведениями и ссылками на PDF. Контакты, реквизиты, ответы и способы получения отражают серверные данные; недостающие сведения не выдумываются. Наличие этих страниц не означает подтверждения безопасности продукции или одобрения банка.

## Verification and open decisions

Скриншоты и browser-results.json: [artifacts/customer-pages-20260930](../../artifacts/customer-pages-20260930/). Проверены семь маршрутов на двух доменах при ширине 1440 и 390 px: HTTP 200, горизонтального переполнения не зафиксировано. FAQ открывается без JavaScript. Независимый finish-reviewer вернул `ship`, material fixes отсутствуют. Этот результат относится к UI; полнота юридических сведений и готовность платёжной интеграции здесь не оцениваются.

Незакрытых визуальных решений в зафиксированном объёме нет.
