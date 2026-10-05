// Only a session-bound server quote establishes totals; the map selects a pickup code.
export function installCheckout(form, htmx) {
  const find = (selector) => form.querySelector(selector)
  const picker = find('[data-cdek-picker]')
  const method = form.elements.delivery_method
  const token = form.elements.delivery_quote
  const code = form.elements.pvz_code
  const submit = find('[data-checkout-submit]')
  const label = find('[data-checkout-label]')
  const error = find('[data-checkout-error]')
  const status = find('[data-cdek-status]')
  const calculate = find('[data-cdek-calculate]')
  const mapRoot = find('#cdek-map')
  const mapMessage = find('[data-cdek-map-message]')
  const list = find('[data-cdek-list]')
  const officeList = find('[data-cdek-offices]')
  const more = find('[data-cdek-more]')
  const query = find('[data-cdek-city-query]')
  const search = find('[data-cdek-city-search]')
  const searchStatus = find('[data-cdek-search-status]')
  const locate = find('[data-cdek-locate]')
  const retryTiles = find('[data-cdek-map-retry]')
  const retryPoints = find('[data-cdek-points-retry]')
  const cleanup = new AbortController()
  let request, directoryRequest, expiry, pickupDelay, pickupMap, geoPosition, bounds
  let generation = 0,
    locateGeneration = 0,
    nextPage = 0,
    listLimit = 50
  let destroyed = false,
    loading = false,
    initialView = true,
    searchFit = false,
    activeQuery = ''
  const points = new Map()
  let filtered = []
  const money = (value) =>
    new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' }).format(value)
  const listen = (node, event, callback) =>
    node?.addEventListener(event, callback, { signal: cleanup.signal })
  const announceError = (message) => {
    error.textContent = message
    error.hidden = !message
  }
  const invalidate = (message = 'Рассчитайте доставку заново.') => {
    generation += 1
    request?.abort()
    clearTimeout(expiry)
    clearTimeout(pickupDelay)
    token.value = ''
    submit.disabled = true
    find('[data-delivery-price]').textContent = 'Нужен расчёт'
    find('[data-order-total]').textContent = 'После расчёта доставки'
    label.textContent = 'Проверить заказ'
    if (status) status.textContent = message
    else announceError(message)
    if (calculate) {
      calculate.disabled = false
      calculate.hidden = !code?.value
    }
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
    if (!code?.value) return
    invalidate('Проверяем пункт и рассчитываем доставку…')
    announceError('')
    const version = generation
    const controller = new AbortController()
    request = controller
    const timeout = setTimeout(() => controller.abort(), 30000)
    calculate.disabled = true
    picker.setAttribute('aria-busy', 'true')
    try {
      const response = await fetch(form.dataset.quoteUrl, {
        method: 'POST',
        body: new FormData(form),
        signal: controller.signal,
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
      find('[data-delivery-price]').textContent = money(data.shipping.price)
      find('[data-order-total]').textContent = money(data.total)
      label.textContent = `${form.dataset.paymentLabel || 'Перейти к оплате'} — ${money(data.total)}`
      const deliveryDetails =
        data.shipping.price_source === 'demo'
          ? `Учебная доставка — ${money(data.shipping.price)}, это не тариф СДЭК. Срок доставки не рассчитывается.`
          : `Ориентировочный срок: ${data.shipping.period_min}–${data.shipping.period_max} дн.`
      const packingDetails =
        Number(data.shipping.packing_price) > 0
          ? ` В стоимость получения входят доставка СДЭК ${money(data.shipping.carrier_price)} и упаковка ${money(data.shipping.packing_price)}.`
          : ''
      status.textContent = `ПВЗ ${data.shipping.pickup.code}: ${data.shipping.pickup.city}, ${data.shipping.pickup.address}. ${deliveryDetails}${packingDetails}`
      calculate.hidden = true
      submit.disabled = false
      expireIn(data.expires_in * 1000)
    } catch (failure) {
      if (destroyed || version !== generation) return
      announceError(
        failure.name === 'AbortError' ? 'СДЭК отвечает дольше обычного. Повторите расчёт.' : failure.message,
      )
      status.textContent = 'Пункт выбран, но доставка пока не рассчитана.'
      calculate.hidden = false
    } finally {
      clearTimeout(timeout)
      if (!destroyed && version === generation) {
        calculate.disabled = false
        picker.removeAttribute('aria-busy')
      }
    }
  }
  const clearPickup = () => {
    if (code) code.value = ''
    invalidate('Выберите пункт выдачи, чтобы рассчитать доставку.')
    announceError('')
  }
  const distance = (point) => {
    if (!geoPosition || !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) return Infinity
    const radians = Math.PI / 180
    const a =
      Math.sin(((point.latitude - geoPosition.latitude) * radians) / 2) ** 2 +
      Math.cos(point.latitude * radians) *
        Math.cos(geoPosition.latitude * radians) *
        Math.sin(((point.longitude - geoPosition.longitude) * radians) / 2) ** 2
    return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, a)))
  }
  const inView = (point) =>
    !bounds ||
    !Number.isFinite(point.latitude) ||
    (point.latitude >= bounds.south &&
      point.latitude <= bounds.north &&
      (bounds.west <= bounds.east
        ? point.longitude >= bounds.west && point.longitude <= bounds.east
        : point.longitude >= bounds.west || point.longitude <= bounds.east))
  const renderList = () => {
    if (!officeList) return
    const visible = filtered.filter(inView).sort((a, b) => distance(a) - distance(b))
    officeList.replaceChildren()
    for (const point of visible.slice(0, listLimit)) {
      const row = document.createElement('label')
      row.className = 'cdek-office'
      const radio = document.createElement('input')
      radio.type = 'radio'
      radio.name = 'cdek_office'
      radio.value = point.code
      radio.checked = point.code === code.value
      const info = document.createElement('span')
      const address = document.createElement('strong')
      address.textContent = [point.city, point.address].filter(Boolean).join(', ')
      const details = document.createElement('small')
      const km = distance(point)
      details.textContent = [
        point.work_time,
        Number.isFinite(km)
          ? `≈ ${km.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} км по прямой`
          : '',
        !Number.isFinite(point.latitude) ? 'Без отметки на карте' : '',
      ]
        .filter(Boolean)
        .join(' · ')
      info.append(address, details)
      row.append(radio, info)
      officeList.append(row)
    }
    if (!visible.length) {
      const message = document.createElement('p')
      message.textContent = loading
        ? 'Загружаем пункты…'
        : 'В этой области пунктов нет. Переместите карту или измените поиск.'
      officeList.append(message)
    }
    more.hidden = visible.length <= listLimit
  }
  const normal = (value) => value.toLocaleLowerCase('ru').replaceAll('ё', 'е')
  const refreshPoints = () => {
    const words = normal(activeQuery)
      .split(/[\s,]+/)
      .filter(Boolean)
    filtered = [...points.values()].filter((point) => {
      const text = normal(`${point.city || ''} ${point.region || ''} ${point.address} ${point.name || ''}`)
      return words.every((word) => text.includes(word))
    })
    pickupMap?.setPoints(filtered, { selectedCode: code.value })
    if (searchFit && filtered.some((point) => Number.isFinite(point.latitude))) {
      pickupMap?.fit(filtered)
      if (pickupMap) searchFit = false
    } else if (initialView && pickupMap) {
      const home = filtered.filter((point) => point.city_code === Number(picker.dataset.defaultCity))
      if (home.length) {
        pickupMap.fit(home)
        initialView = false
      }
    }
    renderList()
  }
  const describePoints = () => {
    searchStatus.textContent = loading
      ? `Загружаем ПВЗ СДЭК…${points.size ? ` Уже на карте: ${points.size}.` : ''}`
      : activeQuery
        ? `Найдено пунктов: ${filtered.length}.`
        : `ПВЗ СДЭК: ${points.size}. Выберите удобный адрес на карте.`
  }
  const loadPoints = async () => {
    if (loading || destroyed || nextPage === null) return
    loading = true
    retryPoints.hidden = true
    describePoints()
    try {
      while (!destroyed && nextPage !== null) {
        const controller = new AbortController()
        directoryRequest = controller
        const timeout = setTimeout(() => controller.abort(), 30000)
        let data
        try {
          const endpoint = new URL(picker.dataset.pointsUrl, window.location.origin)
          endpoint.searchParams.set('page', nextPage)
          const response = await fetch(endpoint, { signal: controller.signal, credentials: 'same-origin' })
          data = await response.json()
          if (!response.ok) throw new Error(data.message || 'Не удалось загрузить пункты СДЭК.')
        } finally {
          clearTimeout(timeout)
        }
        if (destroyed) return
        for (const point of data.offices) points.set(point.code, point)
        nextPage = data.next_page
        refreshPoints()
        describePoints()
      }
      loading = false
      describePoints()
      renderList()
    } catch (failure) {
      if (destroyed) return
      loading = false
      searchStatus.textContent = points.size
        ? `Загружено ПВЗ: ${points.size}. Остальные пункты пока недоступны. Повторите загрузку.`
        : 'Не удалось загрузить пункты СДЭК. Повторите загрузку.'
      retryPoints.hidden = false
      renderList()
    }
  }
  const choose = (selectedCode, debounce = false) => {
    code.value = selectedCode
    invalidate('Пункт выбран. Рассчитываем доставку…')
    pickupMap?.select(selectedCode)
    // Preserve radio focus while arrowing through the list.
    officeList.querySelectorAll('input').forEach((input) => {
      input.checked = input.value === selectedCode
    })
    if (debounce) pickupDelay = setTimeout(quote, 250)
    else {
      status.tabIndex = -1
      status.focus({ preventScroll: true })
      quote()
    }
  }
  const mapFailed = () => {
    mapMessage.textContent = 'Карта не загрузилась. Выберите пункт в списке ниже.'
    mapMessage.hidden = false
    retryTiles.hidden = false
    list.open = true
  }
  const initializeMap = async () => {
    if (!mapRoot || pickupMap) return
    try {
      const { createPickupMap } = await import('./cdek-map.js')
      if (destroyed || pickupMap) return
      pickupMap = createPickupMap(mapRoot, {
        tileUrl: picker.dataset.tileUrl,
        attribution: picker.dataset.attribution,
        onChoose: choose,
        onTileState(loaded) {
          if (destroyed) return
          if (!loaded) mapFailed()
          else {
            retryTiles.hidden = true
            mapMessage.hidden = true
          }
        },
        onViewChange(value) {
          bounds = value
          listLimit = 50
          renderList()
        },
      })
      refreshPoints()
      if (geoPosition) pickupMap.locate(geoPosition.latitude, geoPosition.longitude)
    } catch {
      if (!destroyed) mapFailed()
    }
  }
  const performSearch = () => {
    locateGeneration += 1
    activeQuery = query.value.trim()
    geoPosition = null
    pickupMap?.clearLocation()
    initialView = false
    searchFit = Boolean(activeQuery)
    listLimit = 50
    clearPickup()
    refreshPoints()
    describePoints()
  }
  listen(search, 'click', performSearch)
  listen(query, 'keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      performSearch()
    }
  })
  listen(query, 'input', () => {
    locateGeneration += 1
    clearPickup()
    if (!query.value.trim()) performSearch()
  })
  listen(mapRoot, 'pointerdown', () => {
    initialView = false
    searchFit = false
  })
  listen(more, 'click', () => {
    listLimit += 50
    renderList()
  })
  listen(officeList, 'change', (event) => {
    if (event.target.matches('input[type=radio]')) choose(event.target.value, true)
  })
  listen(retryPoints, 'click', loadPoints)
  listen(retryTiles, 'click', () => {
    retryTiles.hidden = true
    if (pickupMap) pickupMap.retry()
    else initializeMap()
  })
  listen(calculate, 'click', quote)
  listen(locate, 'click', async () => {
    const version = ++locateGeneration
    if (!navigator.geolocation || !window.isSecureContext) {
      searchStatus.textContent = 'Геолокация недоступна. Введите город или переместите карту.'
      return
    }
    locate.disabled = true
    searchStatus.textContent = 'Разрешите браузеру определить местоположение…'
    try {
      const position = await new Promise((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          timeout: 10000,
          maximumAge: 300000,
          enableHighAccuracy: false,
        }),
      )
      if (destroyed || version !== locateGeneration) return
      initialView = false
      searchFit = false
      geoPosition = { latitude: position.coords.latitude, longitude: position.coords.longitude }
      query.value = ''
      activeQuery = ''
      clearPickup()
      refreshPoints()
      pickupMap?.locate(geoPosition.latitude, geoPosition.longitude)
      searchStatus.textContent = 'Пункты рядом с вами. Выберите адрес на карте или в списке.'
    } catch (failure) {
      if (!destroyed && version === locateGeneration)
        searchStatus.textContent =
          failure.code === 1
            ? 'Доступ к местоположению не разрешён. Введите город или переместите карту.'
            : 'Не удалось определить местоположение. Введите город или переместите карту.'
    } finally {
      if (!destroyed) locate.disabled = false
    }
  })
  listen(method, 'change', async () => {
    directoryRequest?.abort()
    locateGeneration += 1
    invalidate('Обновляем способ получения…')
    const version = generation
    const controller = new AbortController()
    request = controller
    const timeout = setTimeout(() => controller.abort(), 30000)
    const body = new FormData(form)
    body.set('requote', '1')
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body,
        signal: controller.signal,
        headers: { 'HX-Request': 'true', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value },
      })
      const html = await response.text()
      if (destroyed || version !== generation) return
      if (!response.ok) throw new Error('delivery method')
      htmx.swap('#main-content', html, { swapStyle: 'innerHTML' })
    } catch {
      if (!destroyed && version === generation)
        announceError('Не удалось обновить способ получения. Повторите выбор или обновите страницу.')
    } finally {
      clearTimeout(timeout)
    }
  })
  listen(document, 'cart-updated', () =>
    invalidate('Корзина изменилась. Обновите страницу оформления и рассчитайте доставку снова.'),
  )
  listen(window, 'pageshow', (event) => {
    if (event.persisted) invalidate('Обновите расчёт доставки перед оплатой.')
  })
  if (token.value && picker?.dataset.quotedAt)
    expireIn(Date.parse(picker.dataset.quotedAt) + Number(picker.dataset.quoteTtl) * 1000 - Date.now())
  if (picker?.dataset.ready === '1') {
    find('[data-cdek-search]').hidden = false
    if (!mapRoot) list.open = true
    initializeMap()
    loadPoints()
  }
  return () => {
    destroyed = true
    generation += 1
    locateGeneration += 1
    request?.abort()
    directoryRequest?.abort()
    clearTimeout(expiry)
    clearTimeout(pickupDelay)
    cleanup.abort()
    pickupMap?.destroy()
  }
}
