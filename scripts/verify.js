"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { content, routes } = require("../src/site-content");
const { presentationConfig } = require("../src/presentation-config");
const { heroMedia, motionBudgets } = require("../src/interaction-config");
const { validationMessageFor } = require("../src/shared-interactions");
const {
  appendVariantToHref,
  initPresentation,
  readStoredVariant,
  resolveVariant,
} = require("../src/presentation-runtime");
const { renderHeroMedia, renderVariantSwitcher } = require("../src/render");

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

if (heroMedia.sources.map(({ format }) => format).join(",") !== "webm,mp4"
  || heroMedia.sources.map(({ type }) => type).join(",") !== "video/webm,video/mp4") {
  fail("Hero media configuration must preserve replaceable WebM and MP4 source boundaries.");
}
if (heroMedia.sources.some(({ src }) => src) || heroMedia.poster) {
  fail("Hero media must remain source-free until owned video and poster files are supplied.");
}
const configuredMedia = renderHeroMedia({
  poster: "/media/hero-poster.jpg",
  sources: [
    { format: "webm", type: "video/webm", src: "/media/hero.webm" },
    { format: "mp4", type: "video/mp4", src: "/media/hero.mp4" },
  ],
});
if (!configuredMedia.includes('poster="/media/hero-poster.jpg" controls')
  || !configuredMedia.includes('data-media-state="configured" data-media-poster="true"')
  || !configuredMedia.includes('src="/media/hero.webm" type="video/webm" data-media-format="webm"')
  || !configuredMedia.includes('src="/media/hero.mp4" type="video/mp4" data-media-format="mp4"')) {
  fail("Hero media renderer must activate native playback for configured local WebM, MP4, and poster assets.");
}
if (motionBudgets.compact.ambientParticles >= motionBudgets.full.ambientParticles
  || motionBudgets.compact.pixelRatio >= motionBudgets.full.pixelRatio
  || motionBudgets.reduced.framesPerSecond !== 0) {
  fail("Shared compact and reduced-motion budgets must cap continuous work.");
}

const requiredName = { name: "name", type: "text", value: "", required: true, validity: {} };
const shortMessage = { name: "message", type: "textarea", value: "коротко", required: true, validity: {} };
const uncheckedDemo = { name: "demo-acknowledgement", type: "checkbox", checked: false, required: true, validity: {} };
if (!validationMessageFor(requiredName) || !validationMessageFor(shortMessage) || !validationMessageFor(uncheckedDemo)) {
  fail("Demonstration form validation must reject missing, short, and unacknowledged input.");
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
    [/<script src="\/assets\/shared-interactions\.js"><\/script>/, "shared interaction runtime"],
    [/id="interaction-config"[^>]*>[^<]*motionBudgets/, "shared motion budget configuration"],
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

  for (const value of [content.contacts.phone, content.contacts.email]) {
    if (!html.includes(value)) fail(`${route.path}: footer is missing centralized contact value “${value}”.`);
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
  if (!homepage.includes('data-hero-media data-media-state="empty" data-media-poster="false"')
    || homepage.includes("data-media-format")) {
    fail("Homepage: source-free media state must be explicit and must not emit empty source elements.");
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
  const formRequirements = [
    [/<form\b[^>]*data-demo-form[^>]*novalidate/, "labelled demonstration form boundary"],
    [/<button\b[^>]*type="submit"[^>]*disabled[^>]*data-demo-submit/, "safe-by-default submit control"],
    [/role="status"[^>]*aria-live="polite"/, "announced local result state"],
    [/данные не будут отправлены или сохранены/i, "unmistakable non-submission message"],
  ];
  for (const [pattern, label] of formRequirements) {
    if (!pattern.test(contactsPage)) fail(`Contacts: missing ${label}.`);
  }
  if (/<form\b[^>]*\baction=/i.test(contactsPage)) fail("Contacts: demonstration form must not expose a submission endpoint.");
  for (const { label } of content.consultation.topics) {
    if (!contactsPage.includes(label)) fail(`Contacts: missing centralized consultation option “${label}”.`);
  }
}

const sharedRuntimePath = path.join(outputRoot, "assets", "shared-interactions.js");
if (!fs.existsSync(sharedRuntimePath)) {
  fail("Shared interaction runtime asset is missing.");
} else {
  const sharedRuntime = fs.readFileSync(sharedRuntimePath, "utf8");
  for (const forbiddenTransport of ["fetch(", "XMLHttpRequest", "sendBeacon", "FormData(", "localStorage", "sessionStorage"]) {
    if (sharedRuntime.includes(forbiddenTransport)) fail(`Shared runtime contains forbidden transport/storage API: ${forbiddenTransport}.`);
  }
}

for (const variant of presentationConfig.variants) {
  const variantRuntimePath = path.join(outputRoot, "assets", "variants", `${variant.id}.js`);
  if (!fs.existsSync(variantRuntimePath)) continue;
  const variantRuntime = fs.readFileSync(variantRuntimePath, "utf8");
  if (!variantRuntime.includes("DaryInteractions")) fail(`${variant.name}: runtime is not connected to shared motion state.`);
  if (/addEventListener\(["']scroll["']/.test(variantRuntime)) fail(`${variant.name}: independent scroll listener bypasses the shared coordinator.`);
}

if (failures.length > 0) {
  console.error("Verification failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`Verified ${routes.length} routes, shared media/runtime boundaries, local-only form behavior, contacts, and motion budgets.`);
}
