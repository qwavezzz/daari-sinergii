"use strict";

(() => {
  const variantId = "sectional-medium";
  const root = document.documentElement;
  const main = document.querySelector(".site-main");
  if (!main) return;

  const sharedRuntime = window.DaryInteractions;
  if (!sharedRuntime) return;
  const route = document.body.dataset.route || "home";
  const routeLabels = {
    home: ["Среда · вода", "Продукт · три направления", "Аудитория", "Процесс выбора", "Подтверждение", "Действие"],
    direction: ["Продукт · среда", "Задача", "Аудитория", "Варианты", "Действие"],
    industries: ["Контекст · среда", "Аудитория организаций", "Частный путь"],
    about: ["Среда компании", "Направления", "Подтверждение"],
    contacts: ["Действие · связь", "Контактные данные"],
  };
  const labels = routeLabels[route] || routeLabels.home;
  const bands = Array.from(main.children).filter((element) => element.matches("section, aside"));
  let frameRequest = 0;

  function slugForLabel(label) {
    if (/действие|контакт/i.test(label)) return "action";
    if (/подтверж/i.test(label)) return "evidence";
    if (/аудитор|частн/i.test(label)) return "audience";
    if (/процесс|задач|вариант/i.test(label)) return "process";
    if (/продукт|направлен/i.test(label)) return "product";
    return "water";
  }

  function decorateBand(band, index) {
    const label = labels[index] || `Слой ${index + 1}`;
    band.dataset.sectionalLayer = slugForLabel(label);
    band.dataset.sectionalLabel = label;
    band.style.setProperty("--section-index", index);

    if (!band.querySelector(":scope > .sectional-band-slice")) {
      const slice = document.createElement("span");
      slice.className = "sectional-band-slice";
      slice.setAttribute("aria-hidden", "true");
      band.prepend(slice);
    }

    if (!band.querySelector(":scope > .sectional-band-label")) {
      const marker = document.createElement("span");
      marker.className = "sectional-band-label";
      marker.setAttribute("aria-hidden", "true");
      marker.innerHTML = `<b>${String(index + 1).padStart(2, "0")}</b><i>${label}</i>`;
      band.insertBefore(marker, band.querySelector(":scope > :not(.sectional-band-slice)"));
    }
  }

  bands.forEach(decorateBand);
  main.querySelectorAll(".direction-item, .content-item, .steps > li, .plain-list > li, .contact-list > div")
    .forEach((item, index) => item.style.setProperty("--item-index", index));

  const rail = document.createElement("div");
  rail.className = "sectional-depth-rail";
  rail.setAttribute("aria-hidden", "true");
  rail.innerHTML = bands.map((band, index) => (
    `<span data-section-target="${index}"><b>${String(index + 1).padStart(2, "0")}</b><i>${band.dataset.sectionalLabel}</i></span>`
  )).join("");
  document.body.append(rail);

  function isActive() {
    return root.dataset.variant === variantId;
  }

  function setStaticState() {
    bands.forEach((band) => {
      band.style.setProperty("--section-progress", "1");
      band.style.setProperty("--section-clip", "0%");
    });
    main.style.setProperty("--section-page-progress", "1");
  }

  function updateProgress() {
    frameRequest = 0;
    if (!isActive()) return;
    const state = sharedRuntime.getState();
    if (state.reducedMotion || state.compact || !state.documentVisible) {
      setStaticState();
      return;
    }

    const viewportHeight = Math.max(window.innerHeight, 1);
    const documentHeight = Math.max(document.documentElement.scrollHeight - viewportHeight, 1);
    const pageProgress = Math.min(1, Math.max(0, window.scrollY / documentHeight));
    main.style.setProperty("--section-page-progress", pageProgress.toFixed(3));

    bands.forEach((band) => {
      const rect = band.getBoundingClientRect();
      const raw = (viewportHeight * 0.9 - rect.top) / (viewportHeight + rect.height * 0.35);
      const progress = Math.min(1, Math.max(0.12, raw));
      band.style.setProperty("--section-progress", progress.toFixed(3));
      band.style.setProperty("--section-clip", `${((1 - progress) * 16).toFixed(2)}%`);
    });
  }

  function scheduleUpdate() {
    if (!frameRequest) frameRequest = window.requestAnimationFrame(updateProgress);
  }

  function stopUpdate() {
    if (frameRequest) window.cancelAnimationFrame(frameRequest);
    frameRequest = 0;
  }

  function reconcile() {
    const active = isActive();
    root.classList.toggle("sectional-active", active);
    if (!active) {
      stopUpdate();
      return;
    }
    const state = sharedRuntime.getState();
    if (state.reducedMotion || state.compact || !state.documentVisible) {
      stopUpdate();
      setStaticState();
    } else {
      scheduleUpdate();
    }
  }

  bands.forEach((band, index) => {
    sharedRuntime.registerStage(band, ({ visible }) => {
      if (visible) {
        bands.forEach((band, bandIndex) => {
          band.toggleAttribute("data-sectional-current", bandIndex === index);
        });
        rail.querySelectorAll("[data-section-target]").forEach((item) => {
          item.toggleAttribute("data-current", Number(item.dataset.sectionTarget) === index);
        });
      }
    });
  });

  document.addEventListener("presentation:variantchange", reconcile);
  sharedRuntime.subscribe(reconcile);
  sharedRuntime.subscribeFrame(() => {
    const state = sharedRuntime.getState();
    if (isActive() && !state.reducedMotion && !state.compact && state.documentVisible) scheduleUpdate();
  });
  reconcile();
})();
