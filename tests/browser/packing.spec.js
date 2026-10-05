import { test, expect } from '@playwright/test'

test('manager confirms a measured arrangement and sees native packing forms', async ({ page }) => {
  await page.goto('/admin/login/')
  await page.getByLabel('Имя пользователя:').fill('browser-owner')
  await page.getByLabel('Пароль:').fill('browser-fixture-only')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL('/admin/')
  await page.goto('/admin/orders/packingrecipe/')
  const row = page.getByRole('row').filter({ hasText: 'Черновик для проверки замеров' })
  await expect(row).toContainText('Замеры не подтверждены')
  await row.getByRole('checkbox').check()
  await page.getByLabel('Действие:').selectOption('confirm_actual_measurements')
  await page.getByRole('button', { name: 'Выполнить' }).click()
  await expect(row).toContainText('Замеры подтверждены')
  await row.getByRole('link', { name: 'Черновик для проверки замеров' }).click()
  await expect(page.getByLabel('Измеренный вес готовой посылки, г:')).toHaveValue('1000')
  await expect(page.getByLabel('Как собрать посылку:')).toContainText('Только тест')
  await page.screenshot({ path: 'var/artifacts/packing/recipe-1440.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'var/artifacts/packing/recipe-390.png', fullPage: true })
  await expect(page.getByLabel('Измеренный вес готовой посылки, г:')).toBeVisible()
  await page.goto('/admin/orders/packingbox/')
  await page.getByRole('link', { name: 'Тестовая коробка для сборки' }).click()
  await expect(page.getByLabel('Внутренняя длина, мм:')).toHaveValue('200')
})

test('mixed cart is quoted as one measured parcel and reaches trial payment', async ({ page }) => {
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#f0f0e8"/></svg>',
    }),
  )
  for (const number of [19, 20]) {
    await page.goto(`/products/test-product-${number}/`)
    await page.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(page.locator('#cart-dialog')).not.toBeVisible()
    await page.locator('#cart-toggle').click()
    await expect(page.getByRole('dialog', { name: 'Корзина' })).toBeVisible()
  }
  await page.getByRole('dialog', { name: 'Корзина' }).getByRole('link', { name: 'Оформить заказ' }).click()
  await page.waitForLoadState('load')
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Выберите удобный адрес')
  await page.getByRole('button', { name: 'ПВЗ TEST1: Тестовый адрес, 10', exact: true }).click()
  const quoteResponse = page.waitForResponse(
    (response) => response.url().endsWith('/checkout/cdek/quote/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Выбрать этот пункт' }).click()
  const quote = await (await quoteResponse).json()
  expect(quote.shipping.packages).toEqual([{ weight: 700, length: 22, width: 12, height: 17 }])
  expect(quote.shipping.declared_value).toBe('2581.00')
  expect(quote.shipping.packing.measurements_confirmed).toBe(true)
  expect(quote.shipping.packing.parcels[0].contents).toHaveLength(2)
  await expect(page.locator('[data-order-total]')).toHaveText('2 896,00 ₽')
  await page.getByLabel('Имя', { exact: true }).fill('Тест упаковки')
  await page.getByLabel('Фамилия', { exact: true }).fill('Покупатель')
  await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
  await page.getByLabel('Email', { exact: true }).fill('packing@example.invalid')
  await page.locator('[name=accept_terms]').check()
  await page.locator('[data-checkout-submit]').click()
  await expect(page).toHaveURL(/\/payments\/trial\//)
  await expect(page.locator('main')).toContainText('TEST1')
})

test('automatic mixed cart chooses a shared box and discloses packaging price', async ({ page }) => {
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"></svg>',
    }),
  )
  for (const number of [17, 18]) {
    await page.goto(`/products/test-product-${number}/`)
    await page.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(page.locator('#cart-dialog')).not.toBeVisible()
    await page.locator('#cart-toggle').click()
    await expect(page.getByRole('dialog', { name: 'Корзина' })).toBeVisible()
  }
  await page.getByRole('dialog', { name: 'Корзина' }).getByRole('link', { name: 'Оформить заказ' }).click()
  await page.waitForLoadState('load')
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Выберите удобный адрес')
  await page.getByRole('button', { name: 'ПВЗ TEST1: Тестовый адрес, 10', exact: true }).click()
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/checkout/cdek/quote/') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Выбрать этот пункт' }).click()
  const quote = await (await response).json()
  expect(quote.shipping.packages).toEqual([{ weight: 350, length: 22, width: 17, height: 17 }])
  expect(quote.shipping.packing.parcels[0].box_code).toBe('browser-auto-shared')
  expect(quote.shipping.packing.parcels[0].placements).toHaveLength(2)
  expect(quote.shipping.carrier_price).toBe('315.00')
  expect(quote.shipping.packing_price).toBe('45.50')
  expect(quote.shipping.price).toBe('360.50')
  await expect(page.locator('[data-cdek-status]')).toContainText('упаковка 45,50')
  await expect(page.locator('[data-order-total]')).toHaveText('2 941,50 ₽')
  await page.getByLabel('Имя', { exact: true }).fill('Автоподбор')
  await page.getByLabel('Фамилия', { exact: true }).fill('Проверка')
  await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
  await page.getByLabel('Email', { exact: true }).fill('autopacking@example.invalid')
  await page.locator('[name=accept_terms]').check()
  await page.locator('[data-checkout-submit]').click()
  await expect(page).toHaveURL(/\/payments\/trial\//)
})

test('automatic box profile is editable in native admin on desktop and mobile', async ({ page }) => {
  await page.goto('/admin/login/')
  await page.getByLabel('Имя пользователя:').fill('browser-owner')
  await page.getByLabel('Пароль:').fill('browser-fixture-only')
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.goto('/admin/orders/packingbox/')
  await page.getByRole('link', { name: 'Автокоробка для браузерной проверки shared', exact: true }).click()
  await expect(page.getByLabel('Использовать для автоматического подбора')).toBeChecked()
  await expect(page.getByLabel('Как учитывать стоимость упаковки:')).toHaveValue('charge')
  await expect(page.getByLabel('Коробка и общие материалы на одно место, ₽:')).toHaveValue('45.50')
  await page.screenshot({ path: 'var/artifacts/automatic-packing/box-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByLabel('Внутренняя длина, мм:')).toBeVisible()
  await page.screenshot({ path: 'var/artifacts/automatic-packing/box-mobile.png', fullPage: true })
})
