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
    await expect(page.getByRole('dialog', { name: 'Корзина' })).toBeVisible()
  }
  await page.getByRole('dialog', { name: 'Корзина' }).getByRole('link', { name: 'Оформить заказ' }).click()
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
  await page.getByLabel('Имя получателя').fill('Тест упаковки')
  await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
  await page.getByLabel('Email', { exact: true }).fill('packing@example.invalid')
  await page.locator('[name=accept_terms]').check()
  await page.locator('[data-checkout-submit]').click()
  await expect(page).toHaveURL(/\/payments\/trial\//)
  await expect(page.locator('main')).toContainText('TEST1')
})
