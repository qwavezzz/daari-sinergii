import htmx from '#navigation-transport'

if (htmx) {
  htmx.config.allowEval = false
  htmx.config.allowScriptTags = false
  htmx.config.includeIndicatorStyles = false
  htmx.config.historyCacheSize = 0
  htmx.config.historyRestoreAsHxRequest = false
  htmx.config.scrollIntoViewOnBoost = false
  htmx.config.timeout = 15000
  htmx.config.selfRequestsOnly = true
  window.htmx = htmx
}

export function syncMetadata(root = document) {
  const meta = root.querySelector('[data-page-meta]')
  if (!meta) return
  if (meta.dataset.title) document.title = meta.dataset.title
  for (const [selector, value, attribute] of [
    ['meta[name="description"]', meta.dataset.description, 'content'],
    ['meta[property="og:title"]', meta.dataset.title, 'content'],
    ['meta[property="og:description"]', meta.dataset.description, 'content'],
    ['meta[property="og:url"]', meta.dataset.canonical, 'content'],
    ['link[rel="canonical"]', meta.dataset.canonical, 'href'],
  ]) {
    const node = document.querySelector(selector)
    if (node && value !== undefined) node.setAttribute(attribute, value)
  }
  let robots = document.querySelector('meta[name="robots"]')
  if (meta.dataset.noindex === 'true') {
    if (!robots) {
      robots = document.createElement('meta')
      robots.name = 'robots'
      document.head.append(robots)
    }
    robots.content = 'noindex, nofollow'
  } else robots?.remove()
  // HTMX intentionally strips script tags. Carry JSON as escaped data and replace
  // only our head element, so schema never describes the page we navigated away from.
  let schema = document.getElementById('page-structured-data')
  if (meta.dataset.structuredData && meta.dataset.noindex !== 'true') {
    try {
      const data = JSON.parse(meta.dataset.structuredData)
      if (!schema) {
        schema = document.createElement('script')
        schema.id = 'page-structured-data'
        schema.type = 'application/ld+json'
        document.head.append(schema)
      }
      schema.textContent = JSON.stringify(data)
    } catch {
      schema?.remove()
    }
  } else schema?.remove()
}

export function installNavigation({ beforePage = () => {}, afterPage = () => {} } = {}) {
  if (import.meta.env.VITE_STATIC_DEMO === 'true') {
    // Pages serves complete documents. Native navigation owns Back/Forward.
    document.addEventListener('click', (event) => {
      const anchor = event.target.closest('a[href^="#"]')
      const target = anchor && document.getElementById(anchor.hash.slice(1))
      if (target?.tagName === 'DETAILS') target.open = true
    })
    return
  }
  let retry = null
  let currentUrl = location.pathname + location.search
  const positions = new Map()
  let restoring = false
  let pageRevision = 0
  let finishRevision = 0
  let finishFrame = 0
  const pageRequests = new WeakMap()
  const cancelFinish = () => {
    finishRevision++
    cancelAnimationFrame(finishFrame)
  }
  const feedback = document.getElementById('request-feedback')
  const showError = (event) => {
    const detail = event.detail || {}
    const source = detail.requestConfig?.elt || detail.elt
    const status = detail.xhr?.status
    if (status >= 200 && status < 400) return
    const inline = source?.closest('form')?.parentElement?.querySelector('[data-form-error]')
    const message =
      status === 403
        ? 'Сессия обновилась. Обновите страницу и повторите действие.'
        : 'Не удалось выполнить запрос. Проверьте соединение и повторите.'
    if (inline) {
      inline.textContent = message
      inline.hidden = false
    }
    const errorSurface = document.getElementById('cart-dialog')?.open
      ? document.getElementById('cart-error')
      : feedback
    if (errorSurface) {
      errorSurface.querySelector('span').textContent = message
      errorSurface.hidden = false
      // Re-submit through the same form: the checkout idempotency key remains intact.
      retry = source?.closest('form') || source
    }
  }
  document.addEventListener('htmx:configRequest', (event) => {
    const token =
      event.detail.elt.closest('form')?.querySelector('[name=csrfmiddlewaretoken]')?.value ||
      document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
      document.cookie
        .split('; ')
        .find((value) => value.startsWith('csrftoken='))
        ?.split('=')
        .slice(1)
        .join('=')
    if (token) event.detail.headers['X-CSRFToken'] = decodeURIComponent(token)
  })
  document.addEventListener('htmx:beforeRequest', (event) => {
    if (event.detail.target?.id === 'main-content') {
      cancelFinish()
      pageRevision++
      if (event.detail.xhr) pageRequests.set(event.detail.xhr, pageRevision)
      positions.set(currentUrl, window.scrollY)
      if (location.pathname === '/') {
        try {
          sessionStorage.setItem('landingScroll', String(window.scrollY))
        } catch {
          /* Storage is optional. */
        }
      }
    }
    if (feedback) feedback.hidden = true
    const cartError = document.getElementById('cart-error')
    if (cartError) cartError.hidden = true
  })
  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail
    const requestRevision = pageRequests.get(detail.xhr)
    if (
      detail.target?.id === 'main-content' &&
      requestRevision !== undefined &&
      requestRevision !== pageRevision
    ) {
      // A response started before Back/Forward must not replace the restored page.
      detail.shouldSwap = false
      return
    }
    if ([422, 409].includes(detail.xhr.status)) {
      detail.shouldSwap = true
      detail.isError = false
    }
    if (detail.shouldSwap && detail.target?.id === 'main-content') {
      cancelFinish()
      beforePage(detail.target)
    }
  })
  const restoreScroll = (root, top) => {
    const detail = { top, handled: false }
    root.querySelector('[data-page]')?.dispatchEvent(new CustomEvent('page:restore-scroll', { detail }))
    if (!detail.handled) window.scrollTo({ top, behavior: 'instant' })
  }
  const finish = async (isHistory = false) => {
    cancelFinish()
    const revision = finishRevision
    const root = document.getElementById('main-content')
    syncMetadata(root)
    currentUrl = location.pathname + location.search
    await afterPage(root)
    if (revision !== finishRevision || !root.isConnected) return
    const hash = location.hash
    finishFrame = requestAnimationFrame(() => {
      if (revision !== finishRevision) return
      finishFrame = requestAnimationFrame(() => {
        if (revision !== finishRevision) return
        const error = root.querySelector('[data-error-summary], [aria-invalid=true]')
        if (error) {
          error.focus({ preventScroll: true })
          error.scrollIntoView({ block: 'center' })
          return
        }
        if (isHistory || restoring) {
          restoreScroll(root, positions.get(currentUrl) || 0)
          restoring = false
        } else if (hash === '#return') {
          let remembered = 0
          try {
            remembered = Number(sessionStorage.getItem('landingScroll') || 0)
          } catch {
            /* optional */
          }
          restoreScroll(root, remembered)
        } else if (hash && document.getElementById(hash.slice(1))) {
          const target = document.getElementById(hash.slice(1))
          if (target.tagName === 'DETAILS') target.open = true
          restoreScroll(root, target.getBoundingClientRect().top + window.scrollY)
        } else restoreScroll(root, 0)
        if (!isHistory) {
          const heading = root.querySelector('h1')
          if (heading) {
            heading.tabIndex = -1
            heading.focus({ preventScroll: true })
          }
        }
      })
    })
  }
  document.addEventListener('htmx:afterSwap', (event) => {
    if (event.detail.target?.id !== 'main-content') return
    const requestRevision = pageRequests.get(event.detail.xhr)
    if (requestRevision !== undefined && requestRevision !== pageRevision) return
    // Back can be pressed before afterSettle. The visible page already changed,
    // so do not overwrite the departed landing's position with the new page's scroll.
    currentUrl = location.pathname + location.search
  })
  document.addEventListener('htmx:afterSettle', (event) => {
    const requestRevision = pageRequests.get(event.detail.xhr)
    if (event.detail.target?.id !== 'main-content' || restoring) return
    if (requestRevision !== undefined && requestRevision !== pageRevision) return
    finish()
  })
  window.addEventListener('popstate', () => {
    cancelFinish()
    pageRevision++
    positions.set(currentUrl, window.scrollY)
    restoring = true
    beforePage(document.getElementById('main-content'))
  })
  document.addEventListener('htmx:historyRestore', () => finish(true))
  document.addEventListener('htmx:sendError', showError)
  document.addEventListener('htmx:timeout', showError)
  document.addEventListener('htmx:responseError', showError)
  document.querySelectorAll('[data-retry-request]').forEach((button) =>
    button.addEventListener('click', () => {
      if (!retry?.isConnected) {
        location.reload()
        return
      }
      if (retry.tagName === 'FORM') retry.requestSubmit()
      else retry.click()
    }),
  )
  document.querySelector('[data-dismiss-feedback]')?.addEventListener('click', () => {
    feedback.hidden = true
  })
  document.addEventListener('click', (event) => {
    const anchor = event.target.closest('a[href^="#"]')
    if (!anchor) return
    const target = document.getElementById(anchor.hash.slice(1))
    if (target?.tagName === 'DETAILS') target.open = true
  })
}

export { htmx }
