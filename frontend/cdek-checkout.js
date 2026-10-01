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
      reject(new Error('Карта не загрузилась. Выберите город и пункт из списка или откройте карту снова.'))
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
  const map = form.querySelector('#cdek-map')
  const mapMessage = form.querySelector('[data-cdek-map-message]')
  const listFallback = form.querySelector('[data-cdek-list]')
  const cityQuery = form.querySelector('[data-cdek-city-query]')
  const searchButton = form.querySelector('[data-cdek-city-search]')
  const citySelect = form.querySelector('[data-cdek-cities]')
  const cityWrap = form.querySelector('[data-cdek-cities-wrap]')
  const officeWrap = form.querySelector('[data-cdek-offices-wrap]')
  const officeList = form.querySelector('[data-cdek-offices]')
  const moreOffices = form.querySelector('[data-cdek-more]')
  const changeOffice = form.querySelector('[data-cdek-change-office]')
  const searchStatus = form.querySelector('[data-cdek-search-status]')
  const cleanup = new AbortController()
  let request,
    directoryRequest,
    directoryGeneration = 0,
    nextPage = null,
    generation = 0,
    pickupDelay,
    expiry,
    mapTimeout,
    mapAttempt = 0,
    mapReady = false,
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
    clearTimeout(pickupDelay)
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
    const controller = request
    const timeout = setTimeout(() => controller.abort(), 30000)
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
      if (officeList?.querySelector('input:checked')) {
        officeWrap.hidden = true
        changeOffice.hidden = false
        changeOffice.focus({ preventScroll: true })
      }
      form.querySelector('[data-delivery-price]').textContent = money(data.shipping.price)
      form.querySelector('[data-order-total]').textContent = money(data.total)
      label.textContent = `${form.dataset.paymentLabel || 'Перейти к оплате'} — ${money(data.total)}`
      status.textContent = `ПВЗ ${data.shipping.pickup.code}: ${data.shipping.pickup.city}, ${data.shipping.pickup.address}. Ориентировочный срок: ${data.shipping.period_min}–${data.shipping.period_max} дн.`
      if (map && !map.hidden) {
        map.hidden = true
        openMap.disabled = false
        openMap.setAttribute('aria-expanded', 'false')
        openMap.textContent = 'Изменить пункт на карте'
        mapMessage.hidden = true
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
  const cancelDirectory = () => {
    directoryGeneration += 1
    directoryRequest?.abort()
    if (searchButton) searchButton.disabled = false
    if (moreOffices) moreOffices.disabled = false
    officeWrap?.removeAttribute('aria-busy')
  }
  const clearPickup = () => {
    if (code) code.value = ''
    invalidate('Выберите пункт выдачи, чтобы рассчитать доставку.')
    announceError('')
  }
  // Independent request generation stops stale city results from replacing a later selection.
  const directory = async (url, params, onSuccess) => {
    cancelDirectory()
    const version = directoryGeneration
    const controller = new AbortController()
    directoryRequest = controller
    const timeout = setTimeout(() => controller.abort(), 30000)
    searchButton.disabled = true
    moreOffices.disabled = true
    officeWrap.setAttribute('aria-busy', 'true')
    try {
      const endpoint = new URL(url, window.location.origin)
      endpoint.search = new URLSearchParams(params).toString()
      const response = await fetch(endpoint, { signal: controller.signal, credentials: 'same-origin' })
      const data = await response.json()
      if (destroyed || version !== directoryGeneration) return
      if (!response.ok) throw new Error(data.message || 'Не удалось найти пункт. Повторите поиск.')
      onSuccess(data)
    } catch (failure) {
      if (destroyed || version !== directoryGeneration) return
      searchStatus.textContent =
        failure.name === 'AbortError' ? 'СДЭК отвечает дольше обычного. Повторите поиск.' : failure.message
    } finally {
      clearTimeout(timeout)
      if (!destroyed && version === directoryGeneration) {
        searchButton.disabled = false
        moreOffices.disabled = false
        officeWrap.removeAttribute('aria-busy')
      }
    }
  }
  const searchCities = () => {
    const query = cityQuery.value.trim()
    if (query.length < 2 || query.length > 80) {
      searchStatus.textContent = 'Введите название города: от 2 до 80 символов.'
      cityQuery.focus()
      return
    }
    clearPickup()
    cityWrap.hidden = true
    officeWrap.hidden = true
    changeOffice.hidden = true
    officeList.replaceChildren()
    searchStatus.textContent = 'Ищем город в справочнике СДЭК…'
    directory(picker.dataset.citiesUrl, { q: query }, (data) => {
      citySelect.replaceChildren(new Option('Выберите город', ''))
      for (const city of data.cities) {
        citySelect.add(new Option([city.city, city.region].filter(Boolean).join(', '), city.code))
      }
      cityWrap.hidden = data.cities.length === 0
      searchStatus.textContent = data.cities.length
        ? data.has_more
          ? 'Показаны первые 20 городов. Уточните название, если нужного нет.'
          : 'Выберите город из списка.'
        : 'Город не найден. Проверьте название и повторите поиск.'
      if (data.cities.length) citySelect.focus()
    })
  }
  const loadOffices = (page = 0) => {
    if (!citySelect.value) return
    searchStatus.textContent = 'Загружаем пункты выдачи…'
    directory(picker.dataset.officesUrl, { city_code: citySelect.value, page }, (data) => {
      const existing = new Set(Array.from(officeList.querySelectorAll('input'), (input) => input.value))
      let firstNew
      for (const office of data.offices) {
        if (existing.has(office.code)) continue
        existing.add(office.code)
        const row = document.createElement('label')
        row.className = 'cdek-office'
        const radio = document.createElement('input')
        radio.type = 'radio'
        radio.name = 'cdek_office'
        radio.value = office.code
        const info = document.createElement('span')
        const address = document.createElement('strong')
        address.textContent = office.address
        const details = document.createElement('small')
        details.textContent = [office.name, `ПВЗ ${office.code}`, office.work_time]
          .filter(Boolean)
          .join(' · ')
        info.append(address, details)
        row.append(radio, info)
        officeList.append(row)
        firstNew ||= radio
      }
      nextPage = data.next_page
      moreOffices.hidden = nextPage === null
      officeWrap.hidden = false
      searchStatus.textContent = existing.size
        ? `Загружено пунктов: ${existing.size}. Выберите удобный адрес — стоимость рассчитается автоматически.`
        : nextPage !== null
          ? 'На этой странице нет доступных пунктов. Загрузите следующие.'
          : 'В этом городе нет доступных пунктов выдачи. Выберите другой город.'
      if (firstNew) firstNew.focus()
    })
  }
  listen(searchButton, 'click', searchCities)
  listen(cityQuery, 'keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      searchCities()
    }
  })
  listen(cityQuery, 'input', () => {
    cancelDirectory()
    clearPickup()
    cityWrap.hidden = true
    officeWrap.hidden = true
    changeOffice.hidden = true
    citySelect.replaceChildren()
    officeList.replaceChildren()
    searchStatus.textContent = ''
  })
  listen(citySelect, 'change', () => {
    cancelDirectory()
    clearPickup()
    officeList.replaceChildren()
    officeWrap.hidden = true
    changeOffice.hidden = true
    if (citySelect.value) loadOffices()
    else searchStatus.textContent = 'Выберите город из списка.'
  })
  listen(moreOffices, 'click', () => {
    if (nextPage !== null) loadOffices(nextPage)
  })
  listen(changeOffice, 'click', () => {
    officeWrap.hidden = false
    changeOffice.hidden = true
    officeList.querySelector('input:checked')?.focus()
  })
  listen(officeList, 'change', (event) => {
    if (!event.target.matches('input[type=radio]')) return
    code.value = event.target.value
    invalidate('Пункт выбран. Рассчитываем доставку…')
    // Arrow-key navigation through a radio group should not send a request for every row passed.
    pickupDelay = setTimeout(quote, 250)
  })
  listen(code, 'input', () => {
    officeList?.querySelectorAll('input').forEach((input) => {
      input.checked = false
    })
    invalidate('Пункт изменён. Рассчитайте доставку для нового пункта.')
  })
  if (picker?.dataset.ready === '1') form.querySelector('[data-cdek-search]').hidden = false
  listen(method, 'change', async () => {
    cancelDirectory()
    invalidate('Обновляем способ получения…')
    const version = generation
    request = new AbortController()
    const controller = request
    const timeout = setTimeout(() => controller.abort(), 30000)
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
  const closeMap = () => {
    if (!map) return
    map.hidden = true
    mapMessage.hidden = true
    openMap.disabled = false
    openMap.setAttribute('aria-expanded', 'false')
    openMap.textContent = token.value ? 'Изменить пункт на карте' : 'Выбрать пункт на карте'
    if (!mapReady) {
      mapAttempt += 1
      clearTimeout(mapTimeout)
      widget?.destroy?.()
      widget = null
      map.replaceChildren()
    }
  }
  const mapFailed = (attempt) => {
    if (destroyed || attempt !== mapAttempt) return
    mapReady = false
    closeMap()
    openMap.textContent = 'Повторить загрузку карты'
    mapMessage.textContent = 'Карта не загрузилась. Выберите пункт из списка или попробуйте снова.'
    mapMessage.hidden = false
    listFallback.open = true
  }
  listen(listFallback, 'toggle', () => {
    if (listFallback.open && map && !map.hidden) closeMap()
  })
  if (openMap && picker.dataset.ready === '1') openMap.hidden = false
  listen(openMap, 'click', async () => {
    if (!map.hidden) {
      closeMap()
      return
    }
    cancelDirectory()
    listFallback.open = false
    map.hidden = false
    openMap.setAttribute('aria-expanded', 'true')
    openMap.textContent = 'Скрыть карту'
    mapMessage.textContent = mapReady ? 'Выберите удобный пункт выдачи на карте.' : 'Загружаем карту СДЭК…'
    mapMessage.hidden = false
    if (widget && mapReady) return
    const attempt = ++mapAttempt
    try {
      const Widget = await loadWidget()
      if (destroyed || attempt !== mapAttempt) return
      mapTimeout = setTimeout(() => mapFailed(attempt), 20000)
      widget = new Widget({
        root: 'cdek-map',
        apiKey: picker.dataset.mapKey,
        servicePath: picker.dataset.serviceUrl,
        defaultLocation: 'Тольятти',
        canChoose: true,
        lang: 'rus',
        currency: 'RUB',
        // Selection only: final price comes from the signed server-side quote.
        hideDeliveryOptions: { door: true },
        forceFilters: { type: 'PVZ' },
        onReady() {
          if (destroyed || attempt !== mapAttempt) return
          mapReady = true
          clearTimeout(mapTimeout)
          mapMessage.textContent = 'Выберите удобный пункт выдачи на карте.'
        },
        onChoose(mode, tariff, point) {
          if (destroyed || attempt !== mapAttempt || map.hidden || mode !== 'office' || !point?.code) return
          mapReady = true
          clearTimeout(mapTimeout)
          cancelDirectory()
          officeList?.querySelectorAll('input').forEach((input) => {
            input.checked = false
          })
          code.value = point.code
          quote()
        },
      })
    } catch {
      mapFailed(attempt)
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
    cancelDirectory()
    clearTimeout(pickupDelay)
    clearTimeout(expiry)
    clearTimeout(mapTimeout)
    cleanup.abort()
    widget?.destroy?.()
    widget = null
  }
}
