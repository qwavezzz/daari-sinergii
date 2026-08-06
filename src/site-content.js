"use strict";

const placeholder = (label) => `PLACEHOLDER — уточнить: ${label}`;

const directions = [
  {
    id: "ozone-systems",
    title: "Системы озонации",
    path: "/ozone-systems/",
    summary: "Оборудование и решения, связанные с созданием и применением озона.",
    definition: placeholder("точные конфигурации систем озонации"),
    applications: [placeholder("задачи и области применения")],
    audience: placeholder("для каких организаций подходят конкретные конфигурации"),
    options: [placeholder("модели, комплектации и технические характеристики")],
  },
  {
    id: "ozonated-oils",
    title: "Озонированные масла",
    path: "/ozonated-oils/",
    summary: "Одно из трёх направлений компании.",
    definition: placeholder("состав и описание направления озонированных масел"),
    applications: [placeholder("назначение и области применения")],
    audience: placeholder("для каких организаций и частных покупателей подходит направление"),
    options: [placeholder("виды продукции, объёмы и характеристики")],
  },
  {
    id: "hydrolats",
    title: "Гидролаты",
    path: "/hydrolats/",
    summary: "Одно из трёх направлений компании.",
    definition: placeholder("растительное сырьё и описание направления гидролатов"),
    applications: [placeholder("назначение и области применения")],
    audience: placeholder("для каких организаций и частных покупателей подходит направление"),
    options: [placeholder("виды продукции, объёмы и характеристики")],
  },
];

const industries = [
  "Спортивные и восстановительные центры",
  "Санатории и оздоровительные комплексы",
  "Бассейны и SPA",
  "Водоподготовка",
  "Ветеринарные клиники",
  "Животноводческие предприятия",
  "Сельскохозяйственные предприятия",
].map((title, index) => ({
  id: `industry-${index + 1}`,
  title,
  relevance: placeholder("релевантное направление и сценарий применения"),
}));

const content = {
  company: {
    name: "Дары Синергии",
    description: "Три направления: системы озонации, озонированные масла и гидролаты.",
  },
  navigation: [
    { title: "Главная", path: "/" },
    ...directions.map(({ title, path }) => ({ title, path })),
    { title: "Отраслевые решения", path: "/industry-solutions/" },
    { title: "О компании", path: "/about/" },
    { title: "Контакты", path: "/contacts/" },
  ],
  directions,
  industries,
  audiences: {
    primary: "Организации",
    secondary: "Частные покупатели",
    secondaryNote: placeholder("варианты для личного использования"),
  },
  selection: [
    {
      title: "Контекст",
      description: "Выберите направление или отраслевую ситуацию.",
    },
    {
      title: "Уточнение",
      description: "Недостающие характеристики и условия явно отмечены как уточняемые.",
    },
    {
      title: "Консультация",
      description: "Обсудите задачу со специалистом после публикации контактных данных.",
    },
  ],
  proof: [
    placeholder("документы и сертификаты"),
    placeholder("кейсы и подтверждённые результаты"),
    placeholder("фотографии и видео продукции"),
  ],
  contacts: {
    phone: placeholder("телефон"),
    email: placeholder("электронная почта"),
    address: placeholder("адрес"),
    schedule: placeholder("режим работы"),
  },
  cta: {
    primary: "Подобрать решение",
    secondary: "Получить консультацию",
  },
};

const routes = [
  { path: "/", output: "index.html", kind: "home", title: "Главная" },
  ...directions.map((direction) => ({
    path: direction.path,
    output: `${direction.id}/index.html`,
    kind: "direction",
    title: direction.title,
    directionId: direction.id,
  })),
  {
    path: "/industry-solutions/",
    output: "industry-solutions/index.html",
    kind: "industries",
    title: "Отраслевые решения",
  },
  { path: "/about/", output: "about/index.html", kind: "about", title: "О компании" },
  { path: "/contacts/", output: "contacts/index.html", kind: "contacts", title: "Контакты" },
];

module.exports = { content, placeholder, routes };
