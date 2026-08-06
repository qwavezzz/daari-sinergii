"use strict";

(function exposeSharedInteractions(root, createSharedInteractions) {
  const helpers = createSharedInteractions(root);

  if (typeof module === "object" && module.exports) module.exports = helpers;
  if (root && root.document) root.DaryInteractions = helpers.init();
})(typeof window === "undefined" ? null : window, function createSharedInteractions(windowObject) {
  const defaultBudgets = {
    full: { framesPerSecond: 30, pixelRatio: 1.75, ambientParticles: 72, mediaParticles: 34 },
    compact: { framesPerSecond: 20, pixelRatio: 1.25, ambientParticles: 24, mediaParticles: 12 },
    reduced: { framesPerSecond: 0, pixelRatio: 1, ambientParticles: 18, mediaParticles: 8 },
  };

  function validationMessageFor(field) {
    const name = field.name || "field";
    const value = typeof field.value === "string" ? field.value.trim() : "";
    const validity = field.validity || {};

    if (field.type === "checkbox" && field.required && !field.checked) {
      return "Подтвердите, что понимаете демонстрационный режим.";
    }
    if ((field.required && !value) || validity.valueMissing) {
      const missingMessages = {
        name: "Укажите, как к вам обращаться.",
        email: "Укажите электронную почту.",
        topic: "Выберите предмет разговора.",
        message: "Кратко опишите задачу.",
      };
      return missingMessages[name] || "Заполните это поле.";
    }
    if (name === "name" && value.length < 2) return "Имя должно содержать не менее 2 символов.";
    if (name === "message" && value.length < 10) return "Опишите задачу минимум в 10 символах.";
    if (validity.typeMismatch) return "Проверьте формат электронной почты, например name@example.ru.";
    if (validity.tooLong) return "Сократите текст до допустимой длины.";
    return "";
  }

  function init() {
    const documentObject = windowObject.document;
    const root = documentObject.documentElement;
    const reducedQuery = windowObject.matchMedia?.("(prefers-reduced-motion: reduce)") || { matches: false };
    const compactQuery = windowObject.matchMedia?.("(max-width: 820px), (pointer: coarse)") || { matches: false };
    const stateSubscribers = new Set();
    const frameSubscribers = new Set();
    const stageRecords = new Map();
    let frameRequest = 0;

    function parseBudgets() {
      const element = documentObject.getElementById("interaction-config");
      if (!element) return defaultBudgets;
      try {
        const parsed = JSON.parse(element.textContent);
        return parsed.motionBudgets || defaultBudgets;
      } catch {
        return defaultBudgets;
      }
    }

    const budgets = parseBudgets();
    const state = {
      documentVisible: !documentObject.hidden,
      reducedMotion: Boolean(reducedQuery.matches),
      compact: Boolean(compactQuery.matches),
      scrollY: windowObject.scrollY || 0,
      viewportWidth: windowObject.innerWidth || 0,
      viewportHeight: windowObject.innerHeight || 0,
    };

    function getBudget() {
      if (state.reducedMotion) return budgets.reduced;
      return state.compact ? budgets.compact : budgets.full;
    }

    function snapshot() {
      return Object.freeze({ ...state, budget: Object.freeze({ ...getBudget() }) });
    }

    function exposeState() {
      root.dataset.documentVisibility = state.documentVisible ? "visible" : "hidden";
      root.dataset.motionMode = state.reducedMotion ? "reduced" : "full";
      root.dataset.motionBudget = state.compact ? "compact" : "full";
    }

    function notifyState() {
      exposeState();
      const detail = snapshot();
      for (const subscriber of stateSubscribers) subscriber(detail);
      if (typeof windowObject.CustomEvent === "function") {
        documentObject.dispatchEvent(new windowObject.CustomEvent("dary:runtimechange", { detail }));
      }
    }

    function runFrame() {
      frameRequest = 0;
      state.scrollY = windowObject.scrollY || 0;
      state.viewportWidth = windowObject.innerWidth || 0;
      state.viewportHeight = windowObject.innerHeight || 0;
      const detail = snapshot();
      for (const subscriber of frameSubscribers) subscriber(detail);
    }

    function scheduleFrame() {
      if (!frameRequest) frameRequest = windowObject.requestAnimationFrame(runFrame);
    }

    const stageObserver = typeof windowObject.IntersectionObserver === "function"
      ? new windowObject.IntersectionObserver((entries) => {
        for (const entry of entries) {
          const record = stageRecords.get(entry.target);
          if (!record) continue;
          record.visible = Boolean(entry.isIntersecting);
          entry.target.dataset.motionStageState = record.visible ? "visible" : "offscreen";
          for (const subscriber of record.subscribers) subscriber(getStageState(entry.target));
        }
      }, { rootMargin: "120px 0px", threshold: 0 })
      : null;

    function registerStage(element, subscriber) {
      if (!element) return () => {};
      let record = stageRecords.get(element);
      if (!record) {
        record = { visible: true, subscribers: new Set() };
        stageRecords.set(element, record);
        element.dataset.motionStageState = "visible";
        stageObserver?.observe(element);
      }
      if (subscriber) record.subscribers.add(subscriber);
      subscriber?.(getStageState(element));
      return () => { if (subscriber) record.subscribers.delete(subscriber); };
    }

    function getStageState(element) {
      const visible = stageRecords.get(element)?.visible !== false;
      return Object.freeze({
        visible,
        offscreen: !visible,
        active: visible && state.documentVisible && !state.reducedMotion,
      });
    }

    function initializeMedia() {
      for (const container of documentObject.querySelectorAll("[data-hero-media]")) {
        const video = container.querySelector("video");
        const sources = video ? Array.from(video.querySelectorAll("source[src]")) : [];
        if (!video || sources.length === 0) {
          container.dataset.mediaState = "empty";
          video?.removeAttribute("controls");
          continue;
        }

        container.dataset.mediaState = "loading";
        video.controls = true;
        video.addEventListener("canplay", () => { container.dataset.mediaState = "ready"; }, { once: true });
        video.addEventListener("error", () => {
          container.dataset.mediaState = "error";
          const message = container.querySelector(".media-empty-state span");
          if (message) message.textContent = "Видео временно недоступно; показана синтетическая визуализация";
        }, { once: true });
      }
    }

    function errorTargetFor(field) {
      const ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
      return ids.map((id) => documentObject.getElementById(id))
        .find((element) => element?.classList.contains("form-field__error")) || null;
    }

    function validateField(field, announce = true) {
      field.setCustomValidity?.("");
      const message = validationMessageFor(field);
      field.setCustomValidity?.(message);
      if (message) field.setAttribute("aria-invalid", "true");
      else field.removeAttribute("aria-invalid");
      const error = errorTargetFor(field);
      if (error && announce) error.textContent = message;
      return !message;
    }

    function initializeForms() {
      for (const form of documentObject.querySelectorAll("[data-demo-form]")) {
        const fields = Array.from(form.querySelectorAll("[data-demo-field]"));
        const submit = form.querySelector("[data-demo-submit]");
        const status = form.querySelector("[data-demo-status]");
        if (submit) submit.disabled = false;

        for (const field of fields) {
          const eventName = field.matches("select, [type=checkbox]") ? "change" : "input";
          field.addEventListener(eventName, () => {
            if (field.hasAttribute("aria-invalid")) validateField(field);
            if (status) status.textContent = "Отправка отключена. Проверка выполняется только в браузере.";
          });
          field.addEventListener("blur", () => validateField(field));
        }

        form.addEventListener("submit", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const firstInvalid = fields.find((field) => !validateField(field));
          if (firstInvalid) {
            if (status) status.textContent = "Заявка не проверена: исправьте отмеченные поля. Ничего не отправлено и не сохранено.";
            firstInvalid.focus();
            return;
          }

          form.reset();
          for (const field of fields) {
            field.setCustomValidity?.("");
            field.removeAttribute("aria-invalid");
            const error = errorTargetFor(field);
            if (error) error.textContent = "";
          }
          if (status) status.textContent = "Демо-проверка завершена. Данные не отправлены, не сохранены и удалены из полей.";
          submit?.focus();
        });
      }
    }

    function refreshEnvironment() {
      state.documentVisible = !documentObject.hidden;
      state.reducedMotion = Boolean(reducedQuery.matches);
      state.compact = Boolean(compactQuery.matches);
      notifyState();
      scheduleFrame();
    }

    windowObject.addEventListener("scroll", scheduleFrame, { passive: true });
    windowObject.addEventListener("resize", refreshEnvironment, { passive: true });
    documentObject.addEventListener("visibilitychange", refreshEnvironment);
    reducedQuery.addEventListener?.("change", refreshEnvironment);
    compactQuery.addEventListener?.("change", refreshEnvironment);

    const canvas = documentObject.createElement("canvas");
    if (!canvas.getContext || !canvas.getContext("2d")) root.classList.add("no-canvas");
    documentObject.querySelectorAll("[data-motion-stage]").forEach((stage) => registerStage(stage));
    initializeMedia();
    initializeForms();
    notifyState();
    scheduleFrame();

    return Object.freeze({
      getBudget,
      getStageState,
      getState: snapshot,
      isStageActive: (element) => getStageState(element).active,
      registerStage,
      subscribe(subscriber) {
        stateSubscribers.add(subscriber);
        subscriber(snapshot());
        return () => stateSubscribers.delete(subscriber);
      },
      subscribeFrame(subscriber) {
        frameSubscribers.add(subscriber);
        subscriber(snapshot());
        return () => frameSubscribers.delete(subscriber);
      },
    });
  }

  return { defaultBudgets, init, validationMessageFor };
});
