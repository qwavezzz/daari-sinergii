import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import './shop.css'
import Alpine from '@alpinejs/csp'
import { htmx, installNavigation, syncMetadata } from './shared.js'
import { registerContentUI } from './content-ui.js'

let latestVersion = 0
let pendingCartRequests = 0
let cartFocusId = ''
const demoCart = import.meta.env.VITE_STATIC_DEMO === 'true' ? import('./demo-cart.js') : null
const channel = 'BroadcastChannel' in window ? new BroadcastChannel('dari-cart') : null
function cartCounts(count) {
  document.querySelectorAll('[data-cart-count]:not(.cart-content)').forEach((node) => {
    node.textContent = count
  })
}
function refreshCart() {
  if (demoCart) return demoCart.then((cart) => cart.refreshCart())
  return htmx.ajax('GET', '/cart/?drawer=1', { target: '#cart-panel', swap: 'innerHTML' })
}
Alpine.data('shopShell', () => ({
  menuOpen: false,
  opener: null,
  savedY: 0,
  closeTimer: null,
  observer: null,
  get menuClass() {
    return this.menuOpen ? 'is-open' : ''
  },
  toggleMenu() {
    this.menuOpen = !this.menuOpen
  },
  closeMenu() {
    this.menuOpen = false
  },
  trapFocus(event) {
    const dialog = document.getElementById('cart-dialog')
    if (!dialog.open) return
    const controls = [
      ...dialog.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ].filter((node) => node.getClientRects().length > 0)
    const first = controls[0]
    const last = controls.at(-1)
    if (!first) {
      event.preventDefault()
      return
    }
    if (!dialog.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
      event.preventDefault()
      ;(event.shiftKey ? last : first).focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  },
  openCart(event) {
    if (event && (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) return
    event?.preventDefault()
    event?.stopPropagation()
    this.showCart(event?.currentTarget)
    refreshCart().catch(() => {})
  },
  showCart(opener) {
    const dialog = document.getElementById('cart-dialog')
    clearTimeout(this.closeTimer)
    this.closeMenu()
    if (!dialog.open) {
      this.opener = opener || document.activeElement
      this.savedY = window.scrollY
      document.body.style.position = 'fixed'
      document.body.style.top = '-' + this.savedY + 'px'
      document.body.style.width = '100%'
      dialog.showModal()
    }
    dialog.classList.remove('is-closing')
    requestAnimationFrame(() => dialog.classList.add('is-open'))
    dialog.querySelector('button').focus({ preventScroll: true })
    this.sizeCart()
  },
  sizeCart() {
    const dialog = document.getElementById('cart-dialog')
    const header = dialog.querySelector('.cart-drawer-header')?.offsetHeight || 0
    const summary = dialog.querySelector('.cart-summary')?.offsetHeight || 0
    dialog.classList.toggle('whole-scroll', header + summary > window.innerHeight / 2)
  },
  closeCart(immediate = false) {
    const dialog = document.getElementById('cart-dialog')
    if (!dialog.open) return
    dialog.classList.add('is-closing')
    dialog.classList.remove('is-open')
    const done = () => {
      dialog.close()
      document.body.style.position = ''
      document.body.style.top = ''
      document.body.style.width = ''
      window.scrollTo({ top: this.savedY, behavior: 'instant' })
      const target = this.opener?.isConnected ? this.opener : document.getElementById('cart-toggle')
      target?.focus({ preventScroll: true })
    }
    if (immediate === true || matchMedia('(prefers-reduced-motion: reduce)').matches) done()
    else this.closeTimer = setTimeout(done, 200)
  },
  backdropClick(event) {
    if (event.target === document.getElementById('cart-dialog')) this.closeCart()
  },
  init() {
    window.shopShell = this
    this.observer = new ResizeObserver(() => this.sizeCart())
    this.observer.observe(document.getElementById('cart-panel'))
    window.addEventListener('resize', () => this.sizeCart())
  },
}))
Alpine.data('productGallery', () => ({
  index: 0,
  total: 0,
  startX: 0,
  root: null,
  get counter() {
    return this.index + 1 + ' / ' + this.total
  },
  init() {
    this.root = this.$el
    this.total = this.root.querySelectorAll('[data-gallery-slide]').length
    this.root.querySelectorAll('[data-gallery-controls]').forEach((node) => {
      node.hidden = false
    })
    this.update()
  },
  update() {
    const track = this.root.querySelector('.gallery-track')
    track.scrollTo({ left: this.index * track.clientWidth, behavior: 'instant' })
    this.root
      .querySelectorAll('[data-slide]')
      .forEach((node) => node.setAttribute('aria-current', String(Number(node.dataset.slide) === this.index)))
  },
  previous() {
    this.index = (this.index - 1 + this.total) % this.total
    this.update()
  },
  next() {
    this.index = (this.index + 1) % this.total
    this.update()
  },
  select(event) {
    this.index = Number(event.currentTarget.dataset.slide)
    this.update()
  },
  touchStart(event) {
    this.startX = event.changedTouches[0].clientX
  },
  touchEnd(event) {
    const distance = event.changedTouches[0].clientX - this.startX
    if (Math.abs(distance) > 45 && this.total > 1) {
      if (distance < 0) this.next()
      else this.previous()
    }
  },
}))
Alpine.data('checkoutForm', () => ({
  init() {
    // Delivery selection is re-quoted by the server; browser values never establish totals.
    const select = this.$el.querySelector('[name=delivery_method]')
    if (!select) return
    select.addEventListener('change', () => {
      const form = this.$el
      const values = Object.fromEntries(new FormData(form).entries())
      values.requote = '1'
      htmx.ajax('POST', form.action, { target: '#main-content', swap: 'innerHTML', values })
    })
  },
}))
window.Alpine = Alpine
registerContentUI(Alpine)
Alpine.start()
document.documentElement.classList.add('js')
demoCart?.then((cart) => cart.installDemoCart())

document.addEventListener('htmx:beforeRequest', (event) => {
  if (event.detail.requestConfig?.path?.startsWith('/cart/')) {
    cartFocusId =
      document.activeElement?.id ||
      event.detail.elt.closest('.cart-item')?.querySelector('[name=quantity]')?.id ||
      ''
    pendingCartRequests++
    document.querySelectorAll('.checkout-link').forEach((node) => node.setAttribute('aria-disabled', 'true'))
  }
})
document.addEventListener('htmx:beforeSwap', (event) => {
  const version = Number(event.detail.xhr.getResponseHeader('X-Cart-Version'))
  if (event.detail.xhr.getResponseHeader('X-Cart-Version') !== null) {
    if (version < latestVersion) event.detail.shouldSwap = false
    else latestVersion = version
  }
})
document.addEventListener('htmx:afterRequest', (event) => {
  if (event.detail.requestConfig?.path?.startsWith('/cart/')) {
    pendingCartRequests = Math.max(0, pendingCartRequests - 1)
    if (!pendingCartRequests)
      document.querySelectorAll('.checkout-link').forEach((node) => node.removeAttribute('aria-disabled'))
    const source = event.detail.requestConfig?.elt
    if (source?.matches('[data-cart-add]') && event.detail.xhr.status === 422) {
      const response = new DOMParser().parseFromString(event.detail.xhr.responseText, 'text/html')
      const error = source.parentElement.querySelector('[data-form-error]')
      if (error) {
        error.textContent =
          response.querySelector('.shop-error')?.textContent ||
          'Не удалось добавить товар. Проверьте количество и наличие.'
        error.hidden = false
      }
    }
  }
})
document.addEventListener('cart-updated', (event) => {
  const { count, version } = event.detail
  if (Number(version) < latestVersion) return
  latestVersion = Number(version)
  cartCounts(count)
  channel?.postMessage({ version })
})
document.addEventListener('htmx:afterSwap', (event) => {
  const content = document.querySelector('#cart-panel .cart-content')
  if (content) {
    latestVersion = Math.max(latestVersion, Number(content.dataset.cartVersion))
    cartCounts(content.dataset.cartCount)
  }
  if (event.detail.requestConfig?.elt?.matches('[data-cart-add]') && event.detail.xhr.status < 400) {
    window.shopShell.showCart(event.detail.requestConfig.elt.querySelector('button'))
    const summary = content?.querySelector('.cart-summary')
    if (summary) {
      const notice = document.createElement('p')
      notice.className = 'cart-notice'
      notice.setAttribute('role', 'status')
      notice.textContent = 'Товар добавлен в корзину'
      summary.append(notice)
    }
  }
  if (
    event.detail.requestConfig?.path?.startsWith('/cart/') &&
    document.getElementById('cart-dialog').open &&
    cartFocusId
  ) {
    const next =
      document.getElementById(cartFocusId) ||
      document.querySelector('#cart-panel [name=quantity]') ||
      document.querySelector('#cart-dialog button')
    next?.focus({ preventScroll: true })
  }
  window.shopShell?.sizeCart()
})
channel?.addEventListener('message', (event) => {
  if (Number(event.data.version) <= latestVersion) return
  refreshCart().catch(() => {})
})
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshCart().catch(() => {})
})
document.addEventListener(
  'click',
  (event) => {
    if (event.target.closest('.checkout-link') && pendingCartRequests) {
      event.preventDefault()
      event.stopPropagation()
    }
  },
  true,
)
installNavigation({ beforePage: () => window.shopShell?.closeCart(true) })
syncMetadata()
