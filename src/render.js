"use strict";

const { content } = require("./site-content");
const { presentationConfig } = require("./presentation-config");

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

function renderVariantSwitcher(config = presentationConfig) {
  if (!config.switcherEnabled) return "";

  const controls = config.variants.map((variant) => {
    const checked = variant.id === config.defaultVariant ? " checked" : "";
    return `<div class="variant-switcher__option">
      <input type="radio" id="variant-${variant.id}" name="presentation-variant" value="${variant.id}"${checked}>
      <label for="variant-${variant.id}"><span class="variant-switcher__index" aria-hidden="true">${variant.index}</span><span class="variant-switcher__name">${escapeHtml(variant.name)}</span></label>
    </div>`;
  }).join("");

  return `<aside class="variant-switcher" aria-label="Выбор варианта оформления">
    <fieldset class="variant-switcher__fieldset">
      <legend>Вариант оформления</legend>
      <div class="variant-switcher__options">${controls}</div>
    </fieldset>
  </aside>`;
}

function serializePresentationConfig(config) {
  return JSON.stringify(config).replaceAll("<", "\\u003c");
}

function renderDirectionSymbol(direction) {
  const symbols = {
    "ozone-systems": `<circle cx="34" cy="40" r="14"/><path d="M8 40h12m28 0h16M27 31l14 18M27 49l14-18"/>`,
    "ozonated-oils": `<path d="M36 10c0 0-17 21-17 34a17 17 0 0 0 34 0C53 31 36 10 36 10Z"/><path d="M30 48c2 4 5 6 10 6"/>`,
    hydrolats: `<path d="M31 17c0 0-13 16-13 26a13 13 0 0 0 26 0c0-10-13-26-13-26Z"/><path d="M51 55c8-6 8-14 0-20m8 23c8-8 8-20 0-28"/>`,
  };
  return `<figure class="direction-symbol">
    <svg viewBox="0 0 72 72" aria-hidden="true" focusable="false">${symbols[direction.id]}</svg>
    <figcaption>Схема направления; изображение ${direction.id === "ozone-systems" ? "оборудования" : "продукции"} уточняется</figcaption>
  </figure>`;
}

function renderDirectionCards() {
  return content.directions.map((direction, index) => `
    <article class="content-item direction-item" data-direction="${escapeHtml(direction.id)}">
      <span class="direction-index" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>
      ${renderDirectionSymbol(direction)}
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

function renderAtmosphereCanvas(kind = "ambient") {
  return `<canvas class="variant-field variant-field--${kind}" data-reactor-field="${kind}" aria-hidden="true"></canvas>
    <div class="variant-field-fallback" aria-hidden="true"><i></i><i></i><i></i></div>`;
}

function renderHeroMedia() {
  const diagnostics = content.directions.map((direction) => `
    <li><span aria-hidden="true"></span>${escapeHtml(direction.title)}</li>`).join("");

  return `<div class="hero-stage" data-variant-stage>
    <figure class="media-aperture">
      <video class="hero-video" preload="metadata" muted playsinline aria-describedby="hero-media-caption"></video>
      <canvas class="media-placeholder-field" data-reactor-field="media" aria-hidden="true"></canvas>
      <div class="media-empty-state">
        <strong>Процедурная визуализация</strong>
        <span>Видео будет добавлено после предоставления медиафайла</span>
      </div>
      <figcaption id="hero-media-caption">Зарезервировано место для подтверждённого видео о технологии или процессе. Сейчас показана синтетическая визуализация.</figcaption>
    </figure>
    <ul class="hero-diagnostics" aria-label="Подтверждённые направления компании">${diagnostics}</ul>
  </div>`;
}

function renderInnerHero(title, lead, supporting = "") {
  return `<section class="hero hero-inner" aria-labelledby="page-title">
      ${renderAtmosphereCanvas()}
      <div class="hero-copy">
        <h1 id="page-title">${escapeHtml(title)}</h1>
        <p class="lead">${escapeHtml(lead)}</p>
        ${supporting}
      </div>
    </section>`;
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
    <section class="hero hero-home" aria-labelledby="page-title">
      ${renderAtmosphereCanvas("hero")}
      <div class="hero-copy">
        <h1 id="page-title"><span class="hero-line">Технологии озона</span><span class="hero-line">для воды, среды</span><span class="hero-line">и продукта</span></h1>
        <p class="lead">Три направления для организаций и частных покупателей.</p>
        <div class="actions">
          ${link("/industry-solutions/", content.cta.primary, "button")}
          ${link("/contacts/", content.cta.secondary, "button button--secondary")}
        </div>
      </div>
      ${renderHeroMedia()}
    </section>
    <section id="directions" aria-labelledby="directions-title">
      <h2 id="directions-title">Выберите предмет разговора</h2>
      <div class="content-grid directions-grid">${renderDirectionCards()}</div>
    </section>
    <section id="industries" aria-labelledby="industries-title">
      <h2 id="industries-title">Навигация по отраслевому контексту</h2>
      <div class="content-grid">${renderIndustryItems()}</div>
      ${link("/industry-solutions/", "Все отраслевые ситуации", "text-link")}
    </section>
    <section id="selection" aria-labelledby="selection-title">
      <h2 id="selection-title">От контекста к консультации</h2>
      <ol class="steps">${selection}</ol>
    </section>
    <section id="evidence" aria-labelledby="evidence-title">
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
    ${renderInnerHero(direction.title, direction.summary, `<p class="placeholder" data-placeholder>${escapeHtml(direction.definition)}</p>`)}
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
    ${renderInnerHero("Отраслевые решения", "Путь от ситуации организации к одному из направлений компании.")}
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
    ${renderInnerHero(content.company.name, content.company.description)}
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
    ${renderInnerHero("Контакты", "Все значения ниже централизованы и ожидают подтверждения.")}
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
  const variantStyles = presentationConfig.variants
    .map((variant) => `<link rel="stylesheet" href="/assets/variants/${variant.id}.css">`)
    .join("\n  ");
  const variantScripts = presentationConfig.variants
    .map((variant) => `<script src="/assets/variants/${variant.id}.js" defer></script>`)
    .join("\n  ");
  return `<!doctype html>
<html lang="ru" data-variant="${presentationConfig.defaultVariant}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="description" content="${escapeHtml(content.company.description)}">
  <title>${escapeHtml(pageTitle)}</title>
  <link rel="stylesheet" href="/assets/styles.css">
  ${variantStyles}
  <script id="presentation-config" type="application/json">${serializePresentationConfig(presentationConfig)}</script>
</head>
<body data-route="${escapeHtml(route.kind)}">
  <a class="skip-link" href="#main-content">К основному содержанию</a>
  <header class="site-header">
    <a class="brand" href="/">${escapeHtml(content.company.name)}</a>
    ${renderNavigation(route.path)}
  </header>
  ${renderVariantSwitcher()}
  <main id="main-content" class="site-main">${renderMain(route)}</main>
  <footer class="site-footer">
    <p><strong>${escapeHtml(content.company.name)}</strong></p>
    <p>${escapeHtml(content.contacts.phone)} · ${escapeHtml(content.contacts.email)}</p>
    ${link("/contacts/", "Контакты и реквизиты")}
  </footer>
  <script src="/assets/presentation-runtime.js"></script>
  ${variantScripts}
</body>
</html>`;
}

module.exports = { renderPage, renderVariantSwitcher };
