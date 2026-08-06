"use strict";

const { content } = require("./site-content");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function link(path, label, className = "") {
  const classAttribute = className ? ` class="${className}"` : "";
  return `<a${classAttribute} href="${path}">${escapeHtml(label)}</a>`;
}

function renderNavigation(currentPath) {
  const items = content.navigation.map((item) => {
    const current = item.path === currentPath ? ' aria-current="page"' : "";
    return `<li><a href="${item.path}"${current}>${escapeHtml(item.title)}</a></li>`;
  });

  return `<nav aria-label="Основная навигация"><ul class="nav-list">${items.join("")}</ul></nav>`;
}

function renderDirectionCards() {
  return content.directions.map((direction) => `
    <article class="content-item">
      <h3>${escapeHtml(direction.title)}</h3>
      <p>${escapeHtml(direction.summary)}</p>
      ${link(direction.path, "О направлении", "text-link")}
    </article>`).join("");
}

function renderIndustryItems() {
  return content.industries.map((industry) => `
    <article class="content-item">
      <h3>${escapeHtml(industry.title)}</h3>
      <p class="placeholder" data-placeholder>${escapeHtml(industry.relevance)}</p>
    </article>`).join("");
}

function renderHome() {
  const selection = content.selection.map((step, index) => `
    <li>
      <span class="step-number" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(step.title)}</h3>
      <p>${escapeHtml(step.description)}</p>
    </li>`).join("");
  const proof = content.proof.map((item) => `<li class="placeholder" data-placeholder>${escapeHtml(item)}</li>`).join("");

  return `
    <section class="hero" aria-labelledby="page-title">
      <p class="eyebrow">${escapeHtml(content.audiences.primary)} — основной путь</p>
      <h1 id="page-title">Системы озонации, озонированные масла и гидролаты</h1>
      <p class="lead">Выберите направление или начните с отраслевой ситуации.</p>
      <div class="actions">
        ${link("/industry-solutions/", content.cta.primary, "button")}
        ${link("/contacts/", content.cta.secondary, "text-link")}
      </div>
    </section>
    <section id="directions" aria-labelledby="directions-title">
      <p class="eyebrow">Три направления</p>
      <h2 id="directions-title">Выберите предмет разговора</h2>
      <div class="content-grid">${renderDirectionCards()}</div>
    </section>
    <section id="industries" aria-labelledby="industries-title">
      <p class="eyebrow">Для организаций</p>
      <h2 id="industries-title">Навигация по отраслевому контексту</h2>
      <div class="content-grid">${renderIndustryItems()}</div>
      ${link("/industry-solutions/", "Все отраслевые ситуации", "text-link")}
    </section>
    <section id="selection" aria-labelledby="selection-title">
      <p class="eyebrow">Как ориентироваться</p>
      <h2 id="selection-title">От контекста к консультации</h2>
      <ol class="steps">${selection}</ol>
    </section>
    <section id="evidence" aria-labelledby="evidence-title">
      <p class="eyebrow">Основания для выбора</p>
      <h2 id="evidence-title">Материалы ожидают подтверждения</h2>
      <ul class="plain-list">${proof}</ul>
    </section>
    <section id="consultation" class="callout" aria-labelledby="consultation-title">
      <h2 id="consultation-title">Обсудить задачу</h2>
      <p>Контактные данные пока не предоставлены и отмечены на странице контактов.</p>
      ${link("/contacts/", content.cta.secondary, "button")}
    </section>`;
}

function renderDirection(route) {
  const direction = content.directions.find((item) => item.id === route.directionId);
  const applications = direction.applications.map((item) => `<li class="placeholder" data-placeholder>${escapeHtml(item)}</li>`).join("");
  const options = direction.options.map((item) => `<li class="placeholder" data-placeholder>${escapeHtml(item)}</li>`).join("");

  return `
    <section class="hero hero-inner" aria-labelledby="page-title">
      <p class="eyebrow">Направление</p>
      <h1 id="page-title">${escapeHtml(direction.title)}</h1>
      <p class="lead">${escapeHtml(direction.summary)}</p>
      <p class="placeholder" data-placeholder>${escapeHtml(direction.definition)}</p>
    </section>
    <section aria-labelledby="applications-title">
      <h2 id="applications-title">Задачи и области применения</h2>
      <ul class="plain-list">${applications}</ul>
    </section>
    <section aria-labelledby="audience-title">
      <h2 id="audience-title">Кому подходит направление</h2>
      <p class="placeholder" data-placeholder>${escapeHtml(direction.audience)}</p>
    </section>
    <section aria-labelledby="options-title">
      <h2 id="options-title">Продукция и варианты</h2>
      <ul class="plain-list">${options}</ul>
    </section>
    <section class="callout" aria-labelledby="consultation-title">
      <h2 id="consultation-title">Уточнить задачу и доступные варианты</h2>
      ${link("/contacts/", content.cta.secondary, "button")}
    </section>`;
}

function renderIndustries() {
  return `
    <section class="hero hero-inner" aria-labelledby="page-title">
      <p class="eyebrow">${escapeHtml(content.audiences.primary)}</p>
      <h1 id="page-title">Отраслевые решения</h1>
      <p class="lead">Путь от ситуации организации к одному из направлений компании.</p>
    </section>
    <section aria-labelledby="organization-title">
      <h2 id="organization-title">Контексты организаций</h2>
      <div class="content-grid">${renderIndustryItems()}</div>
    </section>
    <aside class="secondary-path" aria-labelledby="private-title">
      <h2 id="private-title">${escapeHtml(content.audiences.secondary)}</h2>
      <p class="placeholder" data-placeholder>${escapeHtml(content.audiences.secondaryNote)}</p>
      ${link("/contacts/", content.cta.secondary, "text-link")}
    </aside>`;
}

function renderAbout() {
  const directionItems = content.directions.map((direction) => `<li>${link(direction.path, direction.title)}</li>`).join("");
  const proofItems = content.proof.map((item) => `<li class="placeholder" data-placeholder>${escapeHtml(item)}</li>`).join("");

  return `
    <section class="hero hero-inner" aria-labelledby="page-title">
      <p class="eyebrow">О компании</p>
      <h1 id="page-title">${escapeHtml(content.company.name)}</h1>
      <p class="lead">${escapeHtml(content.company.description)}</p>
    </section>
    <section aria-labelledby="directions-title">
      <h2 id="directions-title">Направления</h2>
      <ul class="plain-list">${directionItems}</ul>
    </section>
    <section aria-labelledby="proof-title">
      <h2 id="proof-title">Подтверждающие материалы</h2>
      <p>На текущем этапе материалы не предоставлены. Неопубликованные сведения не заменяются рекламными утверждениями.</p>
      <ul class="plain-list">${proofItems}</ul>
    </section>`;
}

function renderContactList() {
  return Object.entries({
    "Телефон": content.contacts.phone,
    "Электронная почта": content.contacts.email,
    "Адрес": content.contacts.address,
    "Режим работы": content.contacts.schedule,
  }).map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd class="placeholder" data-placeholder>${escapeHtml(value)}</dd></div>`).join("");
}

function renderContacts() {
  return `
    <section class="hero hero-inner" aria-labelledby="page-title">
      <p class="eyebrow">Связаться</p>
      <h1 id="page-title">Контакты</h1>
      <p class="lead">Все значения ниже централизованы и ожидают подтверждения.</p>
    </section>
    <section aria-labelledby="details-title">
      <h2 id="details-title">Контактные данные</h2>
      <dl class="contact-list">${renderContactList()}</dl>
      <p class="notice">Форма отправки ещё не подключена. На этой странице данные не передаются и не сохраняются.</p>
    </section>`;
}

function renderMain(route) {
  switch (route.kind) {
    case "home": return renderHome();
    case "direction": return renderDirection(route);
    case "industries": return renderIndustries();
    case "about": return renderAbout();
    case "contacts": return renderContacts();
    default: throw new Error(`Unknown route kind: ${route.kind}`);
  }
}

function renderPage(route) {
  const pageTitle = route.kind === "home" ? content.company.name : `${route.title} — ${content.company.name}`;
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="${escapeHtml(content.company.description)}">
  <title>${escapeHtml(pageTitle)}</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body data-route="${escapeHtml(route.kind)}">
  <a class="skip-link" href="#main-content">К основному содержанию</a>
  <header class="site-header">
    <a class="brand" href="/">${escapeHtml(content.company.name)}</a>
    ${renderNavigation(route.path)}
  </header>
  <main id="main-content">${renderMain(route)}</main>
  <footer class="site-footer">
    <p><strong>${escapeHtml(content.company.name)}</strong></p>
    <p>${escapeHtml(content.contacts.phone)} · ${escapeHtml(content.contacts.email)}</p>
    ${link("/contacts/", "Контакты и реквизиты")}
  </footer>
</body>
</html>`;
}

module.exports = { renderPage };
