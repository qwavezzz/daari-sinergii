// Only included in the Pages preview build. Real orders always use Django.
import { quantityRequestFailed, syncQuantityFeedback } from './cart-quantity.js'
const catalog = JSON.parse(document.getElementById('demo-products').textContent)
const products = new Map(catalog.map((product) => [String(product.id), product]))
const base = document.documentElement.dataset.demoBase
const storageKey = `dari-preview-cart:v1:${base}`
let items = {}
const money = (cents) =>
  `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(cents / 100)} ₽`
const escape = (text) =>
  String(text).replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char],
  )

function read() {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '{}')
    items = {}
    for (const [id, quantity] of Object.entries(stored || {})) {
      const product = products.get(id)
      if (product?.stock > 0 && Number.isInteger(quantity) && quantity > 0) {
        items[id] = Math.min(quantity, product.stock)
      }
    }
  } catch {
    /* A private browser may only keep the current page's basket. */
  }
}

function save() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(items))
  } catch {
    /* Optional persistence. */
  }
}

function announce(message) {
  const status = document.getElementById('shop-status')
  if (status) status.textContent = message
}

function contents(scope) {
  const rows = Object.entries(items).filter(([id]) => products.has(id))
  if (!rows.length)
    return '<div class="cart-content"><div class="cart-empty"><h2>Корзина пока пуста</h2><p>Добавьте товары из демонстрационного каталога.</p></div></div>'
  const count = rows.reduce((sum, [, quantity]) => sum + quantity, 0)
  const total = rows.reduce((sum, [id, quantity]) => sum + products.get(id).price * quantity, 0)
  return `<div class="cart-content"><div class="cart-summary"><div class="cart-total"><span>Сумма товаров</span><strong>${money(total)}</strong></div><p class="cart-quantity">Количество: ${count}</p><button type="button" class="shop-button" disabled>Оформить заказ</button><p class="cart-delivery-note">Демонстрационная корзина. Заказы и оплата недоступны.</p></div><div class="cart-items">${rows
    .map(([id, quantity]) => {
      const product = products.get(id)
      const inputId = `${scope}-quantity-${id}`
      return `<article class="cart-item" data-item-id="${id}"><a class="cart-item-name" href="${escape(product.url)}">${escape(product.name)}</a><div class="cart-item-image"><img src="${escape(product.image)}" alt="" width="96" height="96"></div><div class="cart-item-info"><p class="cart-sku">${escape(product.sku)}</p><p>${money(product.price)} / шт.</p></div><div class="cart-remove"><button type="button" class="icon-button" data-demo-remove="${id}" aria-label="Удалить ${escape(product.name)}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div><form class="cart-item-quantity" data-demo-quantity="${id}"><label for="${inputId}">Количество</label><input type="number" id="${inputId}" name="quantity" min="1" max="${product.stock}" value="${quantity}" required inputmode="numeric"><button type="submit" class="shop-link">Обновить</button></form><strong class="cart-line-total">${money(product.price * quantity)}</strong></article>`
    })
    .join('')}</div></div>`
}

export function refreshCart() {
  const panel = document.getElementById('cart-panel')
  if (panel) panel.innerHTML = contents('drawer')
  const page = document.querySelector('.cart-page .cart-content')
  if (page) page.outerHTML = contents('page')
  const count = Object.values(items).reduce((sum, quantity) => sum + quantity, 0)
  document.querySelectorAll('[data-cart-count]').forEach((node) => {
    node.textContent = count
  })
  window.shopShell?.sizeCart()
  syncQuantityFeedback()
}

export function installDemoCart() {
  document.querySelectorAll('[data-demo-js-required]').forEach((node) => {
    node.hidden = true
  })
  read()
  refreshCart()
  document.querySelectorAll('[data-demo-add] button').forEach((button) => {
    button.disabled = false
  })
  document.addEventListener('submit', (event) => {
    const form = event.target
    const id = form.dataset.demoAdd || form.dataset.demoQuantity
    if (!id) return
    event.preventDefault()
    const product = products.get(id)
    const input = form.querySelector('[name=quantity]')
    const quantity = Number(input.value)
    read()
    const next = form.hasAttribute('data-demo-add') ? (items[id] || 0) + quantity : quantity
    if (!product || !Number.isInteger(next) || next < 1 || next > product.stock) {
      input.setCustomValidity('Недоступно выбранное количество. Уменьшите количество или измените корзину.')
      input.reportValidity()
      quantityRequestFailed(form)
      syncQuantityFeedback()
      return
    }
    input.setCustomValidity('')
    items[id] = next
    save()
    refreshCart()
    if (form.hasAttribute('data-demo-add')) window.shopShell.showCart(form.querySelector('button'))
    else document.getElementById(input.id)?.focus({ preventScroll: true })
    announce('Демонстрационная корзина обновлена')
  })
  document.addEventListener('input', (event) => {
    if (event.target.matches('[data-demo-add] input, [data-demo-quantity] input'))
      event.target.setCustomValidity('')
  })
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-demo-remove]')
    if (!button) return
    read()
    delete items[button.dataset.demoRemove]
    save()
    refreshCart()
    announce('Товар удалён из демонстрационной корзины')
    document.querySelector('#cart-dialog[open] .cart-drawer-header button')?.focus()
  })
  window.addEventListener('storage', (event) => {
    if (event.key === storageKey) {
      read()
      refreshCart()
    }
  })
}
