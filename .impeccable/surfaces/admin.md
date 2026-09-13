---
version: 1
slug: "admin"
primary_target: "templates/admin/business_index.html"
related_targets: ["templates/admin/base_site.html", "templates/admin/orders/order/change_form.html", "apps/core/static/admin/business.css", "apps/core/admin_site.py", "apps/orders/admin.py", "apps/catalog/admin.py"]
---

# Business administration

## Mode

Operate.

## Purpose

Владелец бизнеса без опыта администрирования находит оплаченные заказы, отмечает сборку и выдачу,
изменяет цены и остатки, редактирует адрес менеджера. На первом экране — очереди заказов и основные задачи.

## Visual authority

Сохраняются стандартные формы, доступность, адаптивность и навигация Django Admin.
Сдержанный синий акцент связывает рабочий интерфейс с магазином. Без декоративной анимации.
Разделы и действия названы по задачам бизнеса; финансовые журналы отделены от ежедневной работы.
Права проверяются на сервере, финансовые статусы устанавливает только проверенная интеграция.
