"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { content, routes } = require("../src/site-content");
const { presentationConfig } = require("../src/presentation-config");
const {
  appendVariantToHref,
  initPresentation,
  readStoredVariant,
  resolveVariant,
} = require("../src/presentation-runtime");
const { renderVariantSwitcher } = require("../src/render");

const projectRoot = path.resolve(__dirname, "..");
const outputRoot = path.join(projectRoot, "dist");
const failures = [];

function fail(message) {
  failures.push(message);
}

function outputForUrl(urlPath) {
  const cleanPath = urlPath.split(/[?#]/, 1)[0];
  if (cleanPath === "/") return path.join(outputRoot, "index.html");
  if (cleanPath.startsWith("/assets/")) return path.join(outputRoot, cleanPath.slice(1));
  return path.join(outputRoot, cleanPath.replace(/^\//, ""), "index.html");
}

if (routes.length !== 7) {
  fail(`Expected 7 routes, received ${routes.length}.`);
}

const variantIds = presentationConfig.variants.map(({ id }) => id);
if (variantIds.length !== 4 || new Set(variantIds).size !== 4) {
  fail("Presentation config must define four unique variants.");
}

if (resolveVariant(`?${presentationConfig.queryParameter}=water-column`, "white-laboratory", presentationConfig) !== "water-column") {
  fail("A valid URL variant must override the stored variant.");
}

if (resolveVariant("", "sectional-medium", presentationConfig) !== "sectional-medium") {
  fail("Stored variant must be used when the URL has no valid variant.");
}

if (resolveVariant(`?${presentationConfig.queryParameter}=unknown`, "white-laboratory", presentationConfig) !== "white-laboratory") {
  fail("An invalid URL variant must fall back to a valid stored variant.");
}

if (readStoredVariant({ getItem() { throw new Error("storage denied"); } }, presentationConfig.storageKey) !== null) {
  fail("Unavailable local storage must be handled without failing presentation state.");
}

const persistedHref = appendVariantToHref(
  "/about/?source=home#proof",
  "water-column",
  "http://localhost/",
  presentationConfig.queryParameter,
);
if (persistedHref !== "/about/?source=home&variant=water-column#proof") {
  fail(`Navigation variant persistence returned an unexpected URL: ${persistedHref}.`);
}

if (appendVariantToHref("#main-content", "water-column", "http://localhost/", presentationConfig.queryParameter) !== "#main-content") {
  fail("Same-page fragment links must not be rewritten by presentation state.");
}

if (renderVariantSwitcher({ ...presentationConfig, switcherEnabled: false }) !== "") {
  fail("The presentation switcher must be removable through its single configuration flag.");
}

const browserControls = presentationConfig.variants.map(({ id }) => ({
  value: id,
  checked: false,
  addEventListener(_type, listener) { this.listener = listener; },
}));
const browserLinks = [
  {
    href: "/about/",
    getAttribute() { return this.href; },
    setAttribute(_name, value) { this.href = value; },
  },
  {
    href: "#main-content",
    getAttribute() { return this.href; },
    setAttribute(_name, value) { this.href = value; },
  },
];
const browserStorage = {
  value: "white-laboratory",
  getItem() { return this.value; },
  setItem(_key, value) { this.value = value; },
};
const browserDocument = {
  documentElement: { dataset: {} },
  getElementById() { return { textContent: JSON.stringify(presentationConfig) }; },
  querySelectorAll(selector) { return selector.startsWith("input") ? browserControls : browserLinks; },
  dispatchEvent() {},
};
const browserHistory = { href: null, replaceState(_state, _title, href) { this.href = href; } };
initPresentation({
  document: browserDocument,
  localStorage: browserStorage,
  location: {
    href: "http://localhost/?variant=water-column",
    pathname: "/",
    search: "?variant=water-column",
    hash: "",
  },
  history: browserHistory,
  CustomEvent: class CustomEvent {},
});

if (browserDocument.documentElement.dataset.variant !== "water-column" || browserStorage.value !== "water-column") {
  fail("Browser initialization must apply the URL variant to the state hook and local storage.");
}
if (browserLinks[0].href !== "/about/?variant=water-column" || browserLinks[1].href !== "#main-content") {
  fail("Browser initialization must persist the active variant only to navigational links.");
}
if (!browserControls.find(({ value }) => value === "water-column").checked) {
  fail("Browser initialization must synchronize the selected radio control.");
}

const sectionalControl = browserControls.find(({ value }) => value === "sectional-medium");
sectionalControl.checked = true;
sectionalControl.listener();
if (browserDocument.documentElement.dataset.variant !== "sectional-medium"
  || browserStorage.value !== "sectional-medium"
  || browserHistory.href !== "/?variant=sectional-medium"
  || browserLinks[0].href !== "/about/?variant=sectional-medium") {
  fail("Changing a variant control must synchronize the state hook, URL, storage, and navigation.");
}

for (const route of routes) {
  const filePath = path.join(outputRoot, route.output);
  if (!fs.existsSync(filePath)) {
    fail(`${route.path}: generated file is missing.`);
    continue;
  }

  const html = fs.readFileSync(filePath, "utf8");
  const requiredPatterns = [
    [/^<!doctype html>/i, "doctype"],
    [/<html\b[^>]*lang="ru"/, "Russian language declaration"],
    [/<header\b/, "header landmark"],
    [/<nav\b[^>]*aria-label=/, "labelled navigation landmark"],
    [/<main\b[^>]*id="main-content"/, "main landmark"],
    [/<h1\b/, "level-one heading"],
    [/<footer\b/, "footer landmark"],
    [/href="#main-content"/, "skip link"],
    [new RegExp(`<html lang="ru" data-variant="${presentationConfig.defaultVariant}">`), "default variant state hook"],
    [/<fieldset\b[^>]*class="variant-switcher__fieldset"/, "variant switcher fieldset"],
    [/<legend\b[^>]*>[^<]+<\/legend>/, "variant switcher label"],
    [/<script src="\/assets\/presentation-runtime\.js"><\/script>/, "presentation runtime"],
  ];

  for (const [pattern, label] of requiredPatterns) {
    if (!pattern.test(html)) fail(`${route.path}: missing ${label}.`);
  }

  for (const variant of presentationConfig.variants) {
    if (!html.includes(`value="${variant.id}"`)) fail(`${route.path}: missing variant control ${variant.id}.`);
    if (!html.includes(variant.name)) fail(`${route.path}: missing variant name ${variant.name}.`);
    if (!html.includes(`/assets/variants/${variant.id}.css`)) fail(`${route.path}: missing variant stylesheet ${variant.id}.`);
    if (!html.includes(`/assets/variants/${variant.id}.js`)) fail(`${route.path}: missing variant runtime ${variant.id}.`);
  }

  if (!html.includes("data-reactor-field=")) fail(`${route.path}: missing neutral bounded-field hook.`);

  if (!html.includes("PLACEHOLDER — уточнить")) {
    fail(`${route.path}: no explicit factual placeholder found.`);
  }

  if (/\bhttps?:\/\//i.test(html)) {
    fail(`${route.path}: remote URL found in generated HTML.`);
  }

  for (const match of html.matchAll(/href="([^"]+)"/g)) {
    const href = match[1];
    if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) continue;
    if (!href.startsWith("/")) {
      fail(`${route.path}: non-root-relative internal link ${href}.`);
      continue;
    }
    if (!fs.existsSync(outputForUrl(href))) fail(`${route.path}: broken link ${href}.`);
  }
}

const runtimePath = path.join(outputRoot, "assets", "presentation-runtime.js");
if (!fs.existsSync(runtimePath)) {
  fail("Presentation runtime asset is missing.");
}

for (const variant of presentationConfig.variants) {
  for (const extension of ["css", "js"]) {
    const assetPath = path.join(outputRoot, "assets", "variants", `${variant.id}.${extension}`);
    if (!fs.existsSync(assetPath)) fail(`Variant asset is missing: ${variant.id}.${extension}.`);
  }
}

const homePath = path.join(outputRoot, "index.html");
if (fs.existsSync(homePath)) {
  const homepage = fs.readFileSync(homePath, "utf8");
  for (const landmark of ["directions", "industries", "selection", "evidence", "consultation"]) {
    if (!homepage.includes(`id="${landmark}"`)) fail(`Homepage: missing ${landmark} content landmark.`);
  }
  for (const label of Object.values(content.cta)) {
    if (!homepage.includes(label)) fail(`Homepage: missing shared CTA label “${label}”.`);
  }
  if (!/<video\b(?![^>]*\bcontrols\b)(?![^>]*\bsrc=)[^>]*><\/video>/.test(homepage)) {
    fail("Homepage: honest source-free video replacement boundary is missing or exposes a fake control.");
  }
  if (!homepage.includes("Процедурная визуализация") || !homepage.includes("Видео будет добавлено")) {
    fail("Homepage: missing-video state is not explicit.");
  }
  for (const direction of content.directions) {
    if (!homepage.includes(`<li><span aria-hidden="true"></span>${direction.title}</li>`)) {
      fail(`Homepage: Reactor diagnostic is missing factual category “${direction.title}”.`);
    }
  }
  for (const forbiddenTelemetry of ["Концентрация озона", "Растворённый озон", "ОВП"]) {
    if (homepage.includes(forbiddenTelemetry)) fail(`Homepage: unsupported telemetry label found: ${forbiddenTelemetry}.`);
  }
}

const contactsPath = path.join(outputRoot, "contacts", "index.html");
if (fs.existsSync(contactsPath)) {
  const contactsPage = fs.readFileSync(contactsPath, "utf8");
  for (const value of Object.values(content.contacts)) {
    if (!contactsPage.includes(value)) fail(`Contacts: missing centralized value “${value}”.`);
  }
  if (/<form\b/i.test(contactsPage)) fail("Contacts: a submission form was introduced before its ticket.");
}

if (failures.length > 0) {
  console.error("Verification failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`Verified ${routes.length} routes, semantic landmarks, internal links, shared CTAs, and explicit placeholders.`);
}
