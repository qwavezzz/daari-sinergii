// The widget selects a code. Only the session-bound server quote establishes totals.
const widgetSource = 'https://cdn.jsdelivr.net/npm/@cdek-it/widget@3.11.1'
let widgetLoading

function loadWidget() {
  if (window.CDEKWidget) return Promise.resolve(window.CDEKWidget)
  if (widgetLoading) return widgetLoading
  widgetLoading = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    const timeout = setTimeout(() => failed(), 15000)
    const failed = () => {
      clearTimeout(timeout)
      script.remove()
      widgetLoading = null
      reject(new Error('Карта не загрузилась. Введите код пункта или попробуйте открыть карту снова.'))
    }
    script.src = widgetSource
    script.async = true
    script.onload = () => {
      clearTimeout(timeout)
      if (window.CDEKWidget) resolve(window.CDEKWidget)
      else failed()
    }
    script.onerror = failed
    document.head.append(script)
  })
  return widgetLoading
}

export function installCheckout(form, htmx) {
  const picker = form.querySelector('[data-cdek-picker]')
  const method = form.elements.delivery_method
  const token = form.elements.delivery_quote
  const code = form.elements.pvz_code
  const submit = form.querySelector('[data-checkout-submit]')
  const label = form.querySelector('[data-checkout-label]')
  const error = form.querySelector('[data-checkout-error]')
  const status = form.querySelector('[data-cdek-status]')
  const calculate = form.querySelector('[data-cdek-calculate]')
  const openMap = form.querySelector('[data-open-cdek]')
  const cleanup = new AbortController()
  let request,
    generation = 0,
    expiry,
    mapTimeout,
    widget,
    destroyed = false
  const money = (value) =>
    new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' }).format(value)
  const listen = (node, event, fn) => node?.addEventListener(event, fn, { signal: cleanup.signal })
  const announceError = (message) => {
    error.textContent = message
    error.hidden = !message
  }
  const invalidate = (message = 'Рассчитайте доставку заново.') => {
    generation += 1
    request?.abort()
    clearTimeout(expiry)
    token.value = ''
    submit.disabled = true
    form.querySelector('[data-delivery-price]').textContent = 'Нужен расчёт'
    form.querySelector('[data-order-total]').textContent = 'После расчёта доставки'
    label.textContent = 'Проверить заказ'
    if (status) status.textContent = message
    else announceError(message)
    if (calculate) calculate.disabled = false
    picker?.removeAttribute('aria-busy')
  }
  const expireIn = (milliseconds) => {
    clearTimeout(expiry)
    expiry = setTimeout(
      () => invalidate('Срок расчёта истёк. Рассчитайте доставку ещё раз.'),
      Math.max(0, milliseconds),
    )
  }
  const quote = async () => {
    invalidate('Проверяем пункт и рассчитываем доставку…')
    announceError('')
    const version = generation
    request = new AbortController()
    const timeout = setTimeout(() => request?.abort(), 30000)
    calculate.disabled = true
    picker.setAttribute('aria-busy', 'true')
    try {
      const response = await fetch(form.dataset.quoteUrl, {
        method: 'POST',
        body: new FormData(form),
        signal: request.signal,
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value },
      })
      const data = await response.json()
      if (destroyed || version !== generation) return
      if (!response.ok) throw new Error(data.message || 'Не удалось рассчитать доставку. Повторите попытку.')
      token.value = data.delivery_quote
      form.elements.quote_token.value = data.quote_token
      form.elements.confirmed_delivery.value = method.value
      code.value = data.shipping.pickup.code
      form.querySelector('[data-delivery-price]').textContent = money(data.shipping.price)
      form.querySelector('[data-order-total]').textContent = money(data.total)
      label.textContent = `Перейти к оплате — ${money(data.total)}`
      status.textContent = `ПВЗ ${data.shipping.pickup.code}: ${data.shipping.pickup.city}, ${data.shipping.pickup.address}. Ориентировочный срок: ${data.shipping.period_min}–${data.shipping.period_max} дн.`
      const map = form.querySelector('#cdek-map')
      if (map && !map.hidden) {
        map.hidden = true
        openMap.disabled = false
        openMap.textContent = 'Изменить пункт на карте'
        status.tabIndex = -1
        status.focus()
      }
      submit.disabled = false
      expireIn(data.expires_in * 1000)
    } catch (failure) {
      if (destroyed || version !== generation) return
      announceError(
        failure.name === 'AbortError' ? 'СДЭК отвечает дольше обычного. Повторите расчёт.' : failure.message,
      )
      status.textContent = 'Доставка не рассчитана. Товары сохранятся в корзине.'
    } finally {
      clearTimeout(timeout)
      if (!destroyed && version === generation) {
        calculate.disabled = false
        picker.removeAttribute('aria-busy')
      }
    }
  }
  listen(calculate, 'click', (event) => {
    event.preventDefault()
    event.stopPropagation()
    quote()
  })
  listen(code, 'input', () => invalidate('Пункт изменён. Рассчитайте доставку для нового пункта.'))
  listen(method, 'change', async () => {
    invalidate('Обновляем способ получения…')
    const version = generation
    request = new AbortController()
    const timeout = setTimeout(() => request?.abort(), 30000)
    const body = new FormData(form)
    body.set('requote', '1')
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body,
        signal: request.signal,
        headers: { 'HX-Request': 'true', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value },
      })
      const html = await response.text()
      if (destroyed || version !== generation) return
      if (!response.ok) throw new Error('Не удалось обновить способ получения. Повторите выбор.')
      htmx.swap('#main-content', html, { swapStyle: 'innerHTML' })
    } catch (failure) {
      if (!destroyed && version === generation)
        announceError('Не удалось обновить способ получения. Повторите выбор или обновите страницу.')
    } finally {
      clearTimeout(timeout)
    }
  })
  if (openMap && picker.dataset.ready === '1') openMap.hidden = false
  listen(openMap, 'click', async () => {
    openMap.disabled = true
    announceError('')
    const map = form.querySelector('#cdek-map')
    map.hidden = false
    try {
      const Widget = await loadWidget()
      if (destroyed) return
      if (!widget) {
        mapTimeout = setTimeout(() => {
          if (destroyed) return
          announceError(
            'Карта загружается дольше обычного. Можно ввести код пункта и рассчитать доставку ниже.',
          )
        }, 20000)
        widget = new Widget({
          root: 'cdek-map',
          apiKey: picker.dataset.mapKey,
          servicePath: picker.dataset.serviceUrl,
          defaultLocation: 'Тольятти',
          canChoose: true,
          lang: 'rus',
          currency: 'RUB',
          // Omitting from deliberately uses official selection-only mode: no browser tariff calculation.
          hideDeliveryOptions: { door: true },
          forceFilters: { type: 'PVZ' },
          onReady() {
            clearTimeout(mapTimeout)
          },
          onChoose(mode, tariff, point) {
            if (destroyed || mode !== 'office' || !point?.code) return
            clearTimeout(mapTimeout)
            code.value = point.code
            quote()
          },
        })
      }
      openMap.textContent = 'Карта пунктов выдачи открыта'
    } catch (failure) {
      if (!destroyed) {
        announceError(failure.message)
        map.hidden = true
        openMap.disabled = false
      }
    }
  })
  listen(document, 'cart-updated', () =>
    invalidate('Корзина изменилась. Обновите страницу оформления и рассчитайте доставку снова.'),
  )
  listen(window, 'pageshow', (event) => {
    if (event.persisted) invalidate('Обновите расчёт доставки перед оплатой.')
  })
  if (token.value && picker?.dataset.quotedAt) {
    expireIn(Date.parse(picker.dataset.quotedAt) + Number(picker.dataset.quoteTtl) * 1000 - Date.now())
  }
  return () => {
    destroyed = true
    generation += 1
    request?.abort()
    clearTimeout(expiry)
    clearTimeout(mapTimeout)
    cleanup.abort()
    widget?.destroy?.()
    widget = null
  }
}
