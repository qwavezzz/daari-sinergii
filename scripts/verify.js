"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { content, routes } = require("../src/site-content");

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

for (const route of routes) {
  const filePath = path.join(outputRoot, route.output);
  if (!fs.existsSync(filePath)) {
    fail(`${route.path}: generated file is missing.`);
    continue;
  }

  const html = fs.readFileSync(filePath, "utf8");
  const requiredPatterns = [
    [/^<!doctype html>/i, "doctype"],
    [/<html lang="ru">/, "Russian language declaration"],
    [/<header\b/, "header landmark"],
    [/<nav\b[^>]*aria-label=/, "labelled navigation landmark"],
    [/<main\b[^>]*id="main-content"/, "main landmark"],
    [/<h1\b/, "level-one heading"],
    [/<footer\b/, "footer landmark"],
    [/href="#main-content"/, "skip link"],
  ];

  for (const [pattern, label] of requiredPatterns) {
    if (!pattern.test(html)) fail(`${route.path}: missing ${label}.`);
  }

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

const homePath = path.join(outputRoot, "index.html");
if (fs.existsSync(homePath)) {
  const homepage = fs.readFileSync(homePath, "utf8");
  for (const landmark of ["directions", "industries", "selection", "evidence", "consultation"]) {
    if (!homepage.includes(`id="${landmark}"`)) fail(`Homepage: missing ${landmark} content landmark.`);
  }
  for (const label of Object.values(content.cta)) {
    if (!homepage.includes(label)) fail(`Homepage: missing shared CTA label “${label}”.`);
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
