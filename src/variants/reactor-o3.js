"use strict";

(function initializeReactorPresentation(windowObject) {
  if (!windowObject || !windowObject.document) return;

  const documentObject = windowObject.document;
  const variantId = "reactor-o3";
  const sharedRuntime = windowObject.DaryInteractions;
  if (!sharedRuntime) return;
  const fields = [];
  let frameRequest = 0;
  let lastTime = 0;

  function seededValue(seed) {
    const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
    return value - Math.floor(value);
  }

  function createParticles(count, offset) {
    return Array.from({ length: count }, (_, index) => ({
      position: seededValue(index + offset),
      lane: seededValue(index * 3 + offset + 1) * 2 - 1,
      size: 0.7 + seededValue(index * 5 + offset + 2) * 2.2,
      speed: 0.035 + seededValue(index * 7 + offset + 3) * 0.045,
      alpha: 0.25 + seededValue(index * 11 + offset + 4) * 0.65,
    }));
  }

  function particleBudget(kind) {
    const budget = sharedRuntime.getBudget();
    return kind === "media" ? budget.mediaParticles : budget.ambientParticles;
  }

  function resizeField(field) {
    const rectangle = field.canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rectangle.width));
    const height = Math.max(1, Math.round(rectangle.height));
    const pixelRatio = Math.min(windowObject.devicePixelRatio || 1, sharedRuntime.getBudget().pixelRatio);

    if (field.width === width && field.height === height && field.pixelRatio === pixelRatio) return;
    field.width = width;
    field.height = height;
    field.pixelRatio = pixelRatio;
    field.canvas.width = Math.round(width * pixelRatio);
    field.canvas.height = Math.round(height * pixelRatio);
    field.context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }

  function drawMediaField(field, time) {
    const { context, width, height } = field;
    context.clearRect(0, 0, width, height);
    const phase = sharedRuntime.getState().reducedMotion ? 0.35 : time * 0.00022;

    for (let line = 0; line < 5; line += 1) {
      context.beginPath();
      for (let x = 0; x <= width; x += 5) {
        const normalized = x / width;
        const envelope = Math.sin(normalized * Math.PI);
        const y = height * (0.46 + line * 0.025)
          + Math.sin(normalized * 10 + phase * (line + 1) + line) * height * 0.08 * envelope;
        if (x === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.strokeStyle = `rgba(57, 189, 248, ${0.18 + line * 0.055})`;
      context.lineWidth = line === 2 ? 1.4 : 0.7;
      context.stroke();
    }

    for (const particle of field.particles) {
      const x = particle.position * width;
      const wave = Math.sin(particle.position * 11 + phase * 3 + particle.lane) * height * 0.14;
      const y = height * 0.5 + wave + particle.lane * height * 0.14;
      context.beginPath();
      context.arc(x, y, particle.size, 0, Math.PI * 2);
      context.fillStyle = `rgba(189, 239, 255, ${particle.alpha})`;
      context.fill();
    }
  }

  function drawAmbientField(field, time) {
    const { context, width, height } = field;
    context.clearRect(0, 0, width, height);
    const phase = sharedRuntime.getState().reducedMotion ? 0.42 : time * 0.00006;

    context.save();
    context.globalCompositeOperation = "lighter";
    for (const particle of field.particles) {
      const progress = (particle.position + phase * particle.speed * 20) % 1;
      const x = width * (-0.08 + progress * 1.02);
      const curve = Math.sin(progress * Math.PI);
      const baseY = height * (0.82 - curve * 0.34);
      const y = baseY + particle.lane * height * (0.03 + curve * 0.12);
      const glow = context.createRadialGradient(x, y, 0, x, y, particle.size * 5);
      glow.addColorStop(0, `rgba(189, 239, 255, ${particle.alpha})`);
      glow.addColorStop(0.35, `rgba(57, 189, 248, ${particle.alpha * 0.5})`);
      glow.addColorStop(1, "rgba(57, 189, 248, 0)");
      context.beginPath();
      context.arc(x, y, particle.size * 5, 0, Math.PI * 2);
      context.fillStyle = glow;
      context.fill();
    }
    context.restore();
  }

  function drawField(field, time) {
    resizeField(field);
    if (field.kind === "media") drawMediaField(field, time);
    else drawAmbientField(field, time);
  }

  function shouldAnimate() {
    return documentObject.documentElement.dataset.variant === variantId
      && !sharedRuntime.getState().reducedMotion
      && sharedRuntime.getState().documentVisible
      && fields.some((field) => field.visible);
  }

  function drawStaticFrame() {
    for (const field of fields) drawField(field, 2400);
  }

  function animate(time) {
    frameRequest = 0;
    if (!shouldAnimate()) return;

    if (time - lastTime >= 1000 / sharedRuntime.getBudget().framesPerSecond) {
      for (const field of fields) {
        if (field.visible) drawField(field, time);
      }
      lastTime = time;
    }
    frameRequest = windowObject.requestAnimationFrame(animate);
  }

  function schedule() {
    if (shouldAnimate() && !frameRequest) frameRequest = windowObject.requestAnimationFrame(animate);
  }

  function stop() {
    if (!frameRequest) return;
    windowObject.cancelAnimationFrame(frameRequest);
    frameRequest = 0;
  }

  function reconcile() {
    if (documentObject.documentElement.dataset.variant !== variantId) {
      stop();
      return;
    }
    drawStaticFrame();
    schedule();
  }

  for (const [index, canvas] of Array.from(documentObject.querySelectorAll("[data-reactor-field]")).entries()) {
    const context = canvas.getContext && canvas.getContext("2d");
    if (!context) continue;
    const kind = canvas.dataset.reactorField;
    fields.push({
      canvas,
      context,
      kind,
      particles: createParticles(particleBudget(kind), 17 + index * 41),
      visible: true,
      width: 0,
      height: 0,
      pixelRatio: 0,
    });
  }

  if (fields.length === 0) return;
  documentObject.documentElement.classList.add("reactor-canvas-ready");
  for (const field of fields) {
    sharedRuntime.registerStage(field.canvas, ({ visible }) => {
      field.visible = visible;
      if (shouldAnimate()) schedule();
      else stop();
    });
  }

  sharedRuntime.subscribe(() => {
    for (const field of fields) {
      field.particles = createParticles(particleBudget(field.kind), 17 + fields.indexOf(field) * 41);
      field.width = 0;
    }
    reconcile();
  });
  documentObject.addEventListener("presentation:variantchange", reconcile);
  reconcile();
})(typeof window === "undefined" ? null : window);
