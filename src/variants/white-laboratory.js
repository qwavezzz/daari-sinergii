"use strict";

(function initializeWhiteLaboratory(windowObject) {
  if (!windowObject || !windowObject.document) return;

  const { document: documentObject } = windowObject;
  const variantId = "white-laboratory";
  const sharedRuntime = windowObject.DaryInteractions;
  if (!sharedRuntime) return;
  const canvases = [];
  let frame = 0;
  let heroVisible = true;
  let lastFrame = 0;

  function isActive() {
    return documentObject.documentElement.dataset.variant === variantId;
  }

  function addMeasurementLabels() {
    for (const hero of documentObject.querySelectorAll(".hero")) {
      if (hero.querySelector(".lab-scale")) continue;

      const scale = documentObject.createElement("div");
      scale.className = `lab-scale${hero.classList.contains("hero-inner") ? " lab-scale--inner" : ""}`;
      scale.setAttribute("aria-hidden", "true");
      const labels = hero.classList.contains("hero-home")
        ? ["3 направления", "для организаций", "для частных покупателей", "медиа ожидается"]
        : ["сведения", "уточняются", "без вымышленных данных"];

      for (const label of labels) {
        const item = documentObject.createElement("span");
        item.textContent = label;
        scale.append(item);
      }
      hero.append(scale);
    }
  }

  function configureCanvas(canvas, index) {
    const context = canvas.getContext?.("2d");
    if (!context) return null;

    const entry = {
      canvas,
      context,
      index,
      kind: canvas.classList.contains("media-placeholder-field") ? "media" : "ambient",
      width: 0,
      height: 0,
      ratio: 1,
    };
    canvases.push(entry);
    return entry;
  }

  function resize(entry) {
    const bounds = entry.canvas.getBoundingClientRect();
    if (bounds.width < 1 || bounds.height < 1) return false;

    const ratio = Math.min(windowObject.devicePixelRatio || 1, sharedRuntime.getBudget().pixelRatio);
    const width = Math.max(1, Math.round(bounds.width * ratio));
    const height = Math.max(1, Math.round(bounds.height * ratio));
    if (entry.canvas.width !== width || entry.canvas.height !== height) {
      entry.canvas.width = width;
      entry.canvas.height = height;
    }
    entry.width = bounds.width;
    entry.height = bounds.height;
    entry.ratio = ratio;
    entry.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return true;
  }

  function line(context, fromX, fromY, toX, toY, color, width = 1) {
    context.beginPath();
    context.moveTo(fromX, fromY);
    context.lineTo(toX, toY);
    context.strokeStyle = color;
    context.lineWidth = width;
    context.stroke();
  }

  function drawAmbient(entry) {
    const { context, width, height, index } = entry;
    context.clearRect(0, 0, width, height);
    context.save();
    context.globalAlpha = 0.78;

    const cx = width * 0.62;
    const cy = height * 0.5;
    const radius = Math.min(width, height) * 0.25;
    context.strokeStyle = "rgba(8, 118, 232, 0.58)";
    context.lineWidth = 1;
    context.beginPath();
    context.arc(cx, cy, radius, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.arc(cx, cy, radius * 0.56, 0, Math.PI * 2);
    context.stroke();

    line(context, width * 0.08, cy, width * 0.94, cy, "rgba(0, 167, 245, 0.7)");
    line(context, cx, height * 0.1, cx, height * 0.9, "rgba(8, 118, 232, 0.35)");

    for (let point = 0; point < 5; point += 1) {
      const angle = point * 1.32 + index * 0.4;
      const x = cx + Math.cos(angle) * radius * 0.78;
      const y = cy + Math.sin(angle) * radius * 0.78;
      context.fillStyle = point % 2 ? "#0876e8" : "#00a7f5";
      context.fillRect(x - 1.5, y - 1.5, 3, 3);
    }

    context.restore();
  }

  function drawMedia(entry, elapsed) {
    const { context, width, height } = entry;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#d5f0f4";
    context.fillRect(0, 0, width, height);

    context.save();
    context.lineWidth = 1;
    const columns = 8;
    const rows = 6;
    for (let column = 1; column < columns; column += 1) {
      const x = (width / columns) * column;
      line(context, x, 0, x, height, "rgba(8, 118, 232, 0.2)");
    }
    for (let row = 1; row < rows; row += 1) {
      const y = (height / rows) * row;
      line(context, 0, y, width, y, "rgba(8, 118, 232, 0.2)");
    }

    const lanes = [0.31, 0.5, 0.69];
    for (let lane = 0; lane < lanes.length; lane += 1) {
      const y = height * lanes[lane];
      context.beginPath();
      for (let step = 0; step <= 28; step += 1) {
        const x = width * (0.12 + step / 34);
        const wave = Math.sin(step * 0.7 + lane * 1.65) * height * (0.026 + lane * 0.006);
        if (step === 0) context.moveTo(x, y + wave);
        else context.lineTo(x, y + wave);
      }
      context.strokeStyle = lane === 1 ? "rgba(8, 118, 232, 0.88)" : "rgba(0, 167, 245, 0.58)";
      context.stroke();

      const nodeX = width * (0.34 + lane * 0.18);
      context.fillStyle = "#f7fbfa";
      context.strokeStyle = "#0876e8";
      context.beginPath();
      context.arc(nodeX, y, 4 + lane, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }

    const progress = sharedRuntime.getState().reducedMotion ? 0.58 : ((elapsed / 5400) % 1);
    const scanX = width * (0.22 + progress * 0.66);
    const scan = context.createLinearGradient(scanX - 42, 0, scanX + 20, 0);
    scan.addColorStop(0, "rgba(0, 167, 245, 0)");
    scan.addColorStop(0.75, "rgba(0, 167, 245, 0.28)");
    scan.addColorStop(1, "rgba(0, 167, 245, 0)");
    context.fillStyle = scan;
    context.fillRect(scanX - 42, 0, 62, height);
    line(context, scanX, height * 0.12, scanX, height * 0.86, "rgba(8, 118, 232, 0.72)");

    context.restore();
  }

  function draw(elapsed = 0) {
    if (!isActive()) return;
    for (const entry of canvases) {
      if (!resize(entry)) continue;
      if (entry.kind === "media") drawMedia(entry, elapsed);
      else drawAmbient(entry);
    }
    documentObject.documentElement.classList.add("white-lab-canvas-ready");
  }

  function tick(elapsed) {
    frame = 0;
    const state = sharedRuntime.getState();
    if (!isActive() || !state.documentVisible || !heroVisible || state.reducedMotion) {
      draw(0);
      return;
    }

    if (elapsed - lastFrame >= 1000 / sharedRuntime.getBudget().framesPerSecond) {
      draw(elapsed);
      lastFrame = elapsed;
    }
    frame = windowObject.requestAnimationFrame(tick);
  }

  function reconcile() {
    if (frame) {
      windowObject.cancelAnimationFrame(frame);
      frame = 0;
    }

    if (!isActive()) return;
    draw(0);
    const state = sharedRuntime.getState();
    if (state.documentVisible && heroVisible && !state.reducedMotion) {
      frame = windowObject.requestAnimationFrame(tick);
    }
  }

  addMeasurementLabels();
  Array.from(documentObject.querySelectorAll(".variant-field, .media-placeholder-field"))
    .forEach((canvas, index) => configureCanvas(canvas, index));

  const observedHero = documentObject.querySelector(".hero");
  if (observedHero) {
    sharedRuntime.registerStage(observedHero, ({ visible }) => {
      heroVisible = visible;
      reconcile();
    });
  }

  sharedRuntime.subscribe(() => {
    for (const entry of canvases) entry.width = 0;
    reconcile();
  });
  documentObject.addEventListener("presentation:variantchange", reconcile);
  reconcile();
})(typeof window === "undefined" ? null : window);
