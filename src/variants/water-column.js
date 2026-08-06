"use strict";

(function initializeWaterColumn(windowObject) {
  if (!windowObject || !windowObject.document) return;

  const documentObject = windowObject.document;
  const variantId = "water-column";
  const motionQuery = windowObject.matchMedia("(prefers-reduced-motion: reduce)");
  const compactQuery = windowObject.matchMedia("(max-width: 820px)");
  const fields = [];
  let frameRequest = 0;
  let scrollRequest = 0;
  let lastFrame = 0;

  function seededValue(seed) {
    const value = Math.sin(seed * 18.319 + 4.731) * 15431.743;
    return value - Math.floor(value);
  }

  function makeBubbles(count, seedOffset) {
    return Array.from({ length: count }, (_, index) => {
      const seed = seedOffset + index * 9;
      return {
        x: 0.12 + seededValue(seed) * 0.82,
        y: seededValue(seed + 1),
        radius: 3 + Math.pow(seededValue(seed + 2), 2) * 30,
        speed: 0.018 + seededValue(seed + 3) * 0.026,
        drift: 0.018 + seededValue(seed + 4) * 0.06,
        phase: seededValue(seed + 5) * Math.PI * 2,
        alpha: 0.2 + seededValue(seed + 6) * 0.45,
      };
    });
  }

  function bubbleBudget(kind) {
    if (kind === "media") return compactQuery.matches ? 5 : 9;
    return compactQuery.matches ? 9 : 20;
  }

  function resizeField(field) {
    const bounds = field.canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(bounds.width));
    const height = Math.max(1, Math.round(bounds.height));
    const pixelRatio = Math.min(windowObject.devicePixelRatio || 1, 1.5);

    if (field.width === width && field.height === height && field.pixelRatio === pixelRatio) return;
    field.width = width;
    field.height = height;
    field.pixelRatio = pixelRatio;
    field.canvas.width = Math.round(width * pixelRatio);
    field.canvas.height = Math.round(height * pixelRatio);
    field.context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }

  function drawBubble(context, x, y, radius, alpha) {
    const halo = context.createRadialGradient(
      x - radius * 0.28,
      y - radius * 0.34,
      radius * 0.08,
      x,
      y,
      radius,
    );
    halo.addColorStop(0, `rgba(248, 252, 255, ${Math.min(0.9, alpha + 0.24)})`);
    halo.addColorStop(0.17, `rgba(189, 239, 255, ${alpha * 0.16})`);
    halo.addColorStop(0.68, `rgba(94, 168, 255, ${alpha * 0.05})`);
    halo.addColorStop(1, `rgba(189, 239, 255, ${alpha * 0.42})`);

    context.beginPath();
    context.ellipse(x, y, radius * 0.88, radius, -0.08, 0, Math.PI * 2);
    context.fillStyle = halo;
    context.fill();
    context.strokeStyle = `rgba(189, 239, 255, ${alpha * 0.88})`;
    context.lineWidth = Math.max(0.65, radius * 0.032);
    context.stroke();
  }

  function drawCaustics(field, time) {
    const { context, width, height } = field;
    const phase = motionQuery.matches ? 1.8 : time * 0.00018;

    context.save();
    context.globalCompositeOperation = "screen";
    for (let line = 0; line < 4; line += 1) {
      context.beginPath();
      for (let x = -10; x <= width + 10; x += 8) {
        const ratio = x / width;
        const y = height * (0.2 + line * 0.2)
          + Math.sin(ratio * 7 + phase + line * 1.7) * height * 0.045;
        if (x < 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.strokeStyle = `rgba(189, 239, 255, ${0.07 + line * 0.025})`;
      context.lineWidth = 1;
      context.stroke();
    }
    context.restore();
  }

  function drawField(field, time) {
    resizeField(field);
    const { context, width, height } = field;
    context.clearRect(0, 0, width, height);
    if (field.kind === "media") drawCaustics(field, time);

    const elapsed = motionQuery.matches ? 3.8 : time * 0.001;
    for (const bubble of field.bubbles) {
      const ascent = (bubble.y + elapsed * bubble.speed) % 1.18;
      const y = height * (1.12 - ascent);
      const x = width * bubble.x + Math.sin(elapsed * 0.55 + bubble.phase) * width * bubble.drift;
      const edgeFade = Math.min(1, Math.max(0, (y + bubble.radius * 2) / (height * 0.16)));
      drawBubble(context, x, y, bubble.radius, bubble.alpha * edgeFade);
    }
  }

  function isActive() {
    return documentObject.documentElement.dataset.variant === variantId;
  }

  function shouldAnimate() {
    return isActive()
      && !motionQuery.matches
      && !documentObject.hidden
      && fields.some((field) => field.visible);
  }

  function drawStaticFrame() {
    for (const field of fields) drawField(field, 3800);
  }

  function animate(time) {
    frameRequest = 0;
    if (!shouldAnimate()) return;

    if (time - lastFrame >= 1000 / 24) {
      for (const field of fields) {
        if (field.visible) drawField(field, time);
      }
      lastFrame = time;
    }
    frameRequest = windowObject.requestAnimationFrame(animate);
  }

  function scheduleAnimation() {
    if (shouldAnimate() && !frameRequest) frameRequest = windowObject.requestAnimationFrame(animate);
  }

  function stopAnimation() {
    if (!frameRequest) return;
    windowObject.cancelAnimationFrame(frameRequest);
    frameRequest = 0;
  }

  function makeSceneRail() {
    const main = documentObject.querySelector("main");
    if (!main) return { rail: null, scenes: [] };

    const topLevel = Array.from(main.querySelectorAll(":scope > section, :scope > aside"));
    const directionScenes = Array.from(main.querySelectorAll("#directions .direction-item"));
    const scenes = [];

    for (const element of topLevel) {
      if (element.id === "directions" && directionScenes.length) scenes.push(...directionScenes);
      else scenes.push(element);
    }

    if (!scenes.length) return { rail: null, scenes };

    const rail = documentObject.createElement("nav");
    rail.className = "wc-scene-rail";
    rail.setAttribute("aria-label", "Навигация по сценам страницы");

    scenes.forEach((scene, index) => {
      scene.classList.add("wc-scene");
      if (!scene.id) scene.id = `water-scene-${index + 1}`;
      const heading = scene.querySelector("h1, h2, h3");
      const title = heading ? heading.textContent.trim() : `Сцена ${index + 1}`;
      const anchor = documentObject.createElement("a");
      const label = documentObject.createElement("span");
      anchor.href = `#${scene.id}`;
      anchor.setAttribute("aria-label", title);
      label.setAttribute("aria-hidden", "true");
      label.textContent = title;
      anchor.append(label);
      rail.append(anchor);
    });

    documentObject.body.append(rail);
    return { rail, scenes };
  }

  const sceneState = makeSceneRail();

  function updateSceneProgress() {
    scrollRequest = 0;
    const { rail, scenes } = sceneState;
    if (!rail || !scenes.length || !isActive()) return;

    const focusLine = windowObject.innerHeight * 0.48;
    let activeIndex = 0;
    let closestDistance = Number.POSITIVE_INFINITY;

    scenes.forEach((scene, index) => {
      const bounds = scene.getBoundingClientRect();
      const distance = Math.abs(bounds.top + bounds.height * 0.5 - focusLine);
      if (distance < closestDistance) {
        closestDistance = distance;
        activeIndex = index;
      }
    });

    const anchors = rail.querySelectorAll("a");
    anchors.forEach((anchor, index) => {
      if (index === activeIndex) anchor.setAttribute("aria-current", "true");
      else anchor.removeAttribute("aria-current");
    });

    const progress = scenes.length > 1 ? activeIndex / (scenes.length - 1) : 1;
    documentObject.documentElement.style.setProperty("--wc-progress", progress.toFixed(3));
  }

  function scheduleProgress() {
    if (!scrollRequest) scrollRequest = windowObject.requestAnimationFrame(updateSceneProgress);
  }

  for (const [index, canvas] of Array.from(documentObject.querySelectorAll("[data-reactor-field]")).entries()) {
    const context = canvas.getContext && canvas.getContext("2d");
    if (!context) continue;
    const kind = canvas.dataset.reactorField === "media" ? "media" : "hero";
    fields.push({
      canvas,
      context,
      kind,
      bubbles: makeBubbles(bubbleBudget(kind), 37 + index * 61),
      visible: true,
      width: 0,
      height: 0,
      pixelRatio: 0,
    });
  }

  if (fields.length) documentObject.documentElement.classList.add("wc-canvas-ready");

  const fieldObserver = typeof windowObject.IntersectionObserver === "function"
    ? new windowObject.IntersectionObserver((entries) => {
      for (const entry of entries) {
        const field = fields.find((candidate) => candidate.canvas === entry.target);
        if (field) field.visible = entry.isIntersecting;
      }
      if (shouldAnimate()) scheduleAnimation();
      else stopAnimation();
    }, { rootMargin: "100px 0px" })
    : null;

  for (const field of fields) {
    if (fieldObserver) fieldObserver.observe(field.canvas);
  }

  function reconcile() {
    if (!isActive()) {
      stopAnimation();
      return;
    }
    drawStaticFrame();
    updateSceneProgress();
    scheduleAnimation();
  }

  let resizeTimer = 0;
  windowObject.addEventListener("resize", () => {
    windowObject.clearTimeout(resizeTimer);
    resizeTimer = windowObject.setTimeout(() => {
      for (const [index, field] of fields.entries()) {
        field.bubbles = makeBubbles(bubbleBudget(field.kind), 37 + index * 61);
        field.width = 0;
      }
      reconcile();
    }, 140);
  }, { passive: true });

  windowObject.addEventListener("scroll", scheduleProgress, { passive: true });
  documentObject.addEventListener("visibilitychange", reconcile);
  documentObject.addEventListener("presentation:variantchange", reconcile);
  motionQuery.addEventListener?.("change", reconcile);
  compactQuery.addEventListener?.("change", reconcile);
  reconcile();
})(typeof window === "undefined" ? null : window);
