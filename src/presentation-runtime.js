"use strict";

(function exposePresentationRuntime(root, createRuntime) {
  const runtime = createRuntime();

  if (typeof module === "object" && module.exports) {
    module.exports = runtime;
  }

  if (root && root.document) {
    runtime.initPresentation(root);
  }
})(typeof window === "undefined" ? null : window, function createPresentationRuntime() {
  function variantIds(config) {
    return new Set(config.variants.map(({ id }) => id));
  }

  function resolveVariant(search, storedVariant, config) {
    const validIds = variantIds(config);
    const urlVariant = new URLSearchParams(search).get(config.queryParameter);

    if (validIds.has(urlVariant)) return urlVariant;
    if (validIds.has(storedVariant)) return storedVariant;
    return config.defaultVariant;
  }

  function readStoredVariant(storage, storageKey) {
    if (!storage) return null;

    try {
      return storage.getItem(storageKey);
    } catch {
      return null;
    }
  }

  function writeStoredVariant(storage, storageKey, variant) {
    if (!storage) return;

    try {
      storage.setItem(storageKey, variant);
    } catch {
      // Presentation state still works through the URL when storage is unavailable.
    }
  }

  function appendVariantToHref(href, variant, baseHref, queryParameter) {
    if (typeof href !== "string" || href.startsWith("#")) return href;

    let target;
    let base;
    try {
      base = new URL(baseHref);
      target = new URL(href, base);
    } catch {
      return href;
    }

    if (target.origin !== base.origin || !/^https?:$/.test(target.protocol)) return href;

    target.searchParams.set(queryParameter, variant);
    return `${target.pathname}${target.search}${target.hash}`;
  }

  function parseConfig(documentObject) {
    const configElement = documentObject.getElementById("presentation-config");
    if (!configElement) return null;

    try {
      return JSON.parse(configElement.textContent);
    } catch {
      return null;
    }
  }

  function initPresentation(windowObject) {
    const { document: documentObject } = windowObject;
    const config = parseConfig(documentObject);
    if (!config || !Array.isArray(config.variants) || config.variants.length === 0) return;

    let storage = null;
    try {
      storage = windowObject.localStorage;
    } catch {
      // Some privacy modes block even reading the localStorage property.
    }

    const controls = Array.from(documentObject.querySelectorAll('input[name="presentation-variant"]'));
    const links = Array.from(documentObject.querySelectorAll("a[href]"));
    const availableIds = variantIds(config);

    function persistNavigation(variant) {
      for (const anchor of links) {
        const href = anchor.getAttribute("href");
        const persistentHref = appendVariantToHref(
          href,
          variant,
          windowObject.location.href,
          config.queryParameter,
        );
        if (persistentHref !== href) anchor.setAttribute("href", persistentHref);
      }
    }

    function applyVariant(variant, updateLocation) {
      if (!availableIds.has(variant)) return;

      documentObject.documentElement.dataset.variant = variant;
      for (const control of controls) control.checked = control.value === variant;

      writeStoredVariant(storage, config.storageKey, variant);
      persistNavigation(variant);

      if (updateLocation) {
        const nextHref = appendVariantToHref(
          windowObject.location.href,
          variant,
          windowObject.location.href,
          config.queryParameter,
        );
        const currentHref = `${windowObject.location.pathname}${windowObject.location.search}${windowObject.location.hash}`;
        if (nextHref !== currentHref) windowObject.history.replaceState(null, "", nextHref);
      }

      if (typeof windowObject.CustomEvent === "function") {
        documentObject.dispatchEvent(new windowObject.CustomEvent("presentation:variantchange", {
          detail: { variant },
        }));
      }
    }

    const storedVariant = readStoredVariant(storage, config.storageKey);
    const activeVariant = resolveVariant(windowObject.location.search, storedVariant, config);
    applyVariant(activeVariant, true);

    for (const control of controls) {
      control.addEventListener("change", () => {
        if (control.checked) applyVariant(control.value, true);
      });
    }
  }

  return {
    appendVariantToHref,
    initPresentation,
    readStoredVariant,
    resolveVariant,
  };
});
