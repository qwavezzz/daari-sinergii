"use strict";

const variants = Object.freeze([
  Object.freeze({ id: "reactor-o3", index: "01", name: "Реактор O₃" }),
  Object.freeze({ id: "white-laboratory", index: "02", name: "Белая лаборатория" }),
  Object.freeze({ id: "water-column", index: "03", name: "Водная колонна" }),
  Object.freeze({ id: "sectional-medium", index: "04", name: "Сечение среды" }),
]);

const presentationConfig = Object.freeze({
  switcherEnabled: true,
  queryParameter: "variant",
  storageKey: "dary-sinergii:presentation-variant",
  defaultVariant: variants[0].id,
  variants,
});

module.exports = { presentationConfig };
