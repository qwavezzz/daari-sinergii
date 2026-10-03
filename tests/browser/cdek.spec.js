import { test, expect } from '@playwright/test'

// No automated tile traffic to public OSM; Leaflet/Supercluster themselves are real.
const tiles = 'https://tile.openstreetmap.org/**'
const tile =
  '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#f0f0e8"/><path d="M0 40h256M0 120h256M0 215h256M45 0v256M170 0v256" stroke="#fff" stroke-width="12"/></svg>'
const serveTile = (route) => route.fulfill({ contentType: 'image/svg+xml', body: tile })
test.beforeEach(async ({ page }) => {
  await page.route(tiles, serveTile)
})
async function startCheckout(page) {
  await page.goto('/products/test-product-1/')
  await page.getByRole('button', { name: 'Добавить в корзину' }).click()
  await expect(page.locator('#cart-dialog')).not.toBeVisible()
  await page.locator('#cart-toggle').click()
  const cart = page.getByRole('dialog', { name: 'Корзина' })
  await expect(cart).toBeVisible()
  await cart.getByRole('link', { name: 'Оформить заказ' }).click()
  await page.waitForLoadState('load')
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
  await expect(page.locator('[data-cdek-picker]')).toBeVisible()
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
}
async function ready(page) {
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Выберите удобный адрес')
  await expect(page.locator('#cdek-map .cdek-marker').first()).toBeVisible()
}
for (const width of [1440, 390]) {
  test(`map is immediately visible and remains after verified pickup at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await startCheckout(page)
    await ready(page)
    await expect(page.locator('#cdek-map')).toBeVisible()
    await expect(page.locator('[data-open-cdek],.cdek-manual')).toHaveCount(0)
    await expect(page.locator('[name=pvz_code]')).toHaveAttribute('type', 'hidden')
    await expect(page.getByRole('button', { name: 'Приблизить', exact: true })).toHaveCSS('width', '44px')
    await expect(page.getByRole('link', { name: 'OpenStreetMap' })).toBeVisible()
    await page.getByLabel('Имя', { exact: true }).fill('Проверка СДЭК')
    await page.getByLabel('Фамилия', { exact: true }).fill('Покупатель')
    await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
    await page.getByLabel('Email', { exact: true }).fill('cdek-qa@example.invalid')
    await page.getByRole('button', { name: 'ПВЗ TEST1: Тестовый адрес, 10', exact: true }).click()
    await expect(page.locator('.leaflet-popup')).toContainText('Пн–Пт 9–18')
    await page.getByRole('button', { name: 'Выбрать этот пункт' }).click()
    await expect(page.locator('[data-delivery-price]')).toHaveText('315,00 ₽')
    await expect(page.locator('[data-order-total]')).toHaveText('1 605,50 ₽')
    await expect(page.locator('#cdek-map')).toBeVisible()
    await expect(page.locator('.cdek-pin.is-selected')).toHaveCount(1)
    await page.locator('[name=accept_terms]').check()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('[data-checkout-submit]').click()
    await expect(page).toHaveURL(/\/payments\/trial\//)
    await expect(page.locator('main')).toContainText('TEST1')
    expect(errors).toEqual([])
  })
  test(`list supports keyboard selection and search resets quotes at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    await startCheckout(page)
    await ready(page)
    await page.getByText('Пункты в этой области', { exact: true }).click()
    const office = page.getByRole('radio', { name: /Тестовый адрес, 10/ })
    await office.focus()
    await office.press('Space')
    await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
    await page.getByLabel('Город или адрес').fill('Другой тестовый адрес')
    await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
    await page.getByRole('button', { name: 'Найти', exact: true }).click()
    await expect(page.getByRole('radio')).toHaveCount(1)
    await expect(
      page.getByRole('button', { name: 'ПВЗ TEST2: Другой тестовый адрес, 20', exact: true }),
    ).toBeVisible()
    await expect(page.locator('[name=delivery_quote]')).toHaveValue('')
  })
}
test('cluster count splits into individual offices when zoomed', async ({ page }) => {
  const points = [0, 1, 2].map((i) => ({
    code: `TEST${i + 1}`,
    city_code: 99999,
    city: 'Тестовый город',
    address: `Адрес ${i + 1}`,
    work_time: '9–18',
    latitude: 53.51 + i * 0.0003,
    longitude: 49.42 + i * 0.0003,
  }))
  await page.route('**/cdek/map-points/**', (route) =>
    route.fulfill({ json: { offices: points, next_page: null } }),
  )
  await startCheckout(page)
  await ready(page)
  await expect(page.locator('.cdek-pin-cluster')).toHaveText('3')
  await page.getByRole('button', { name: 'Пунктов: 3. Приблизить', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Пунктов: 2. Приблизить', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Пунктов: 2. Приблизить', exact: true }).click()
  await expect(page.locator('.cdek-pin:not(.cdek-pin-cluster)')).toHaveCount(3)
  await page.getByRole('button', { name: 'ПВЗ TEST1: Адрес 1', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Выбрать этот пункт' })).toBeVisible()
})
test('failed directory can retry and city search does not make geocoder requests', async ({ page }) => {
  let geocoding = 0
  page.on('request', (r) => {
    if (/\/cdek\/(cities|locate)\//.test(r.url())) geocoding++
  })
  await page.route('**/cdek/map-points/**', (route) =>
    route.fulfill({ status: 503, json: { message: 'Недоступно' } }),
  )
  await startCheckout(page)
  await expect(page.locator('#cdek-map')).toBeVisible()
  await expect(page.locator('[data-cdek-points-retry]')).toBeVisible()
  await page.getByLabel('Имя', { exact: true }).fill('Сохранённое имя')
  await page.getByLabel('Фамилия', { exact: true }).fill('Покупатель')
  await page.unroute('**/cdek/map-points/**')
  await page.locator('[data-cdek-points-retry]').click()
  await ready(page)
  await page.getByLabel('Город или адрес').fill('Тестовый город')
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Найдено пунктов: 2')
  await expect(page.getByLabel('Имя', { exact: true })).toHaveValue('Сохранённое имя')
  expect(geocoding).toBe(0)
})
test('directory loads all pages automatically and deduplicates pickup codes', async ({ page }) => {
  const base = {
    city_code: 99999,
    city: 'Тестовый город',
    latitude: 53.51,
    longitude: 49.42,
    address: 'Адрес',
  }
  await page.route('**/cdek/map-points/**', (route) => {
    const next = new URL(route.request().url()).searchParams.get('page') === '1'
    return route.fulfill({
      json: {
        offices: next
          ? [
              { ...base, code: 'TEST1' },
              { ...base, code: 'TEST2', longitude: 49.44 },
            ]
          : [{ ...base, code: 'TEST1' }],
        next_page: next ? null : 1,
      },
    })
  })
  await startCheckout(page)
  await ready(page)
  await expect(page.locator('[data-cdek-search-status]')).toContainText('ПВЗ СДЭК: 2.')
})
test('geolocation only moves the map after consent without a city API dependency', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 53.50781, longitude: 49.42041 })
  const requests = []
  page.on('request', (r) => {
    if (r.url().includes('/cdek/locate/')) requests.push(r)
  })
  await startCheckout(page)
  await ready(page)
  await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(0)
  await page.getByRole('button', { name: 'Рядом со мной', exact: true }).click()
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Пункты рядом с вами')
  await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(1)
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
  expect(requests).toHaveLength(0)
})
test('denied and late geolocation leave search and map usable', async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition: (_success, failure) => failure({ code: 1 }) },
    }),
  )
  await startCheckout(page)
  await ready(page)
  await page.getByRole('button', { name: 'Рядом со мной', exact: true }).click()
  await expect(page.locator('[data-cdek-search-status]')).toContainText('не разрешён')
  await page.getByLabel('Город или адрес').fill('Тестовый город')
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Найдено пунктов: 2')
  await page.evaluate(() =>
    Object.defineProperty(navigator, 'geolocation', {
      value: {
        getCurrentPosition: (success) => {
          window.resolveLocation = success
        },
      },
    }),
  )
  await page.getByRole('button', { name: 'Рядом со мной', exact: true }).click()
  await page.getByLabel('Город или адрес').fill('Другой')
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  await page.evaluate(() => window.resolveLocation({ coords: { latitude: 0, longitude: 0 } }))
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Найдено пунктов: 1')
})
test('tile failure and stalled tiles do not prevent list selection', async ({ page }) => {
  await page.route(tiles, (route) => route.abort())
  await startCheckout(page)
  await ready(page)
  await expect(page.locator('[data-cdek-map-message]')).toContainText('Карта не загрузилась')
  await expect(page.getByRole('radio', { name: /Тестовый адрес, 10/ })).toBeVisible()
  await page.unroute(tiles)
  await page.route(tiles, serveTile)
  await page.getByRole('button', { name: 'Повторить загрузку карты' }).click()
  await expect(page.locator('[data-cdek-map-retry]')).toBeHidden()
  await page.getByRole('radio', { name: /Тестовый адрес, 10/ }).check()
  await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
})
test('delivery quote failure can retry without a manual pickup code field', async ({ page }) => {
  await page.route('**/cdek/quote/', (route) =>
    route.fulfill({ status: 503, json: { message: 'СДЭК временно недоступен.' } }),
  )
  await startCheckout(page)
  await ready(page)
  await page.getByRole('button', { name: 'ПВЗ TEST1: Тестовый адрес, 10', exact: true }).click()
  await page.getByRole('button', { name: 'Выбрать этот пункт' }).click()
  await expect(page.locator('[data-checkout-error]')).toContainText('СДЭК временно недоступен')
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
  await expect(page.locator('#cdek-map')).toBeVisible()
  await page.unroute('**/cdek/quote/')
  await page.getByRole('button', { name: 'Повторить расчёт доставки' }).click()
  await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
})
