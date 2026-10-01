import { test, expect } from '@playwright/test'

const widgetUrl = 'https://cdn.jsdelivr.net/npm/@cdek-it/widget@3.11.1'
const fakeWidget = `window.CDEKWidget = class {
  constructor(options) {
    this.root = document.getElementById(options.root);
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = 'Выбрать тестовый ПВЗ';
    button.addEventListener('click', () => options.onChoose('office', {delivery_sum: 1},
      {code: 'TEST1', address: 'Подменённый клиентский адрес'}));
    this.root.append(button);
  }
  destroy() { this.root.replaceChildren(); }
};`

async function startCheckout(page) {
  await page.goto('/products/test-product-1/')
  await page.getByRole('button', { name: 'Добавить в корзину' }).click()
  const cart = page.getByRole('dialog', { name: 'Корзина' })
  await expect(cart).toBeVisible()
  await page.evaluate(() => {
    window.checkoutNavigationSentinel = true
  })
  await cart.getByRole('link', { name: 'Оформить заказ' }).click()
  await expect(page).toHaveURL(/\/checkout\/$/)
  expect(await page.evaluate(() => window.checkoutNavigationSentinel)).toBeUndefined()
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
  await expect(page.locator('[data-cdek-picker]')).toBeVisible()
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
}

for (const width of [1440, 390]) {
  test(`CDEK pickup uses server price and address then persists order at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.route(widgetUrl, (route) =>
      route.fulfill({ contentType: 'application/javascript', body: fakeWidget }),
    )
    await startCheckout(page)
    await page.getByLabel('Имя получателя').fill('Проверка СДЭК')
    await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
    await page.getByLabel('Email', { exact: true }).fill('cdek-qa@example.invalid')
    await page.getByRole('button', { name: 'Выбрать пункт на карте' }).click()
    await page.getByRole('button', { name: 'Выбрать тестовый ПВЗ' }).click()
    await expect(page.locator('[data-delivery-price]')).toHaveText('315,00 ₽')
    await expect(page.locator('[data-order-total]')).toHaveText('1 605,50 ₽')
    await expect(page.locator('[data-cdek-status]')).toContainText('Тестовый адрес, 10')
    await expect(page.locator('[data-cdek-status]')).not.toContainText('Подменённый')
    await page.locator('[name=accept_terms]').check()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: `artifacts/alfa-cdek/checkout-${width}.png`, fullPage: true })
    await page.locator('[data-checkout-submit]').click()
    await expect(page).toHaveURL(/\/payments\/trial\//)
    await expect(page.locator('main')).toContainText('1 605,50 ₽')
    await expect(page.locator('main')).toContainText('TEST1')
    await expect(page.locator('main')).toContainText('Пробная оплата')
    expect(errors).toEqual([])
  })
}

test('changing pickup invalidates the old total; unavailable delivery can be retried', async ({ page }) => {
  await startCheckout(page)
  await page.getByText('У меня есть код пункта СДЭК', { exact: true }).click()
  await page.getByLabel('Код пункта СДЭК').fill('TEST1')
  await page.getByRole('button', { name: 'Рассчитать доставку', exact: true }).click()
  await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
  await page.getByLabel('Код пункта СДЭК').fill('TEST2')
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
  await expect(page.locator('[data-order-total]')).toHaveText('После расчёта доставки')
  await page.route('**/checkout/cdek/quote/', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'СДЭК временно недоступен. Повторите расчёт.' }),
    }),
  )
  await page.getByRole('button', { name: 'Рассчитать доставку', exact: true }).click()
  await expect(page.locator('[data-checkout-error]')).toContainText('СДЭК временно недоступен')
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
  await page.unroute('**/checkout/cdek/quote/')
  await page.getByRole('button', { name: 'Рассчитать доставку', exact: true }).click()
  await expect(page.locator('[data-order-total]')).toHaveText('1 605,50 ₽')
  await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
})

for (const width of [1440, 390]) {
  test(`city search selects an official office and auto-calculates at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await startCheckout(page)
    await page.getByLabel('Город получения', { exact: true }).fill('Тестовый город')
    await page.getByLabel('Город получения', { exact: true }).press('Enter')
    await expect(page.getByLabel('Выберите город')).toBeFocused()
    await page.getByLabel('Выберите город').selectOption('44')
    const office = page.getByRole('radio', { name: /Тестовый адрес, 10/ })
    await expect(office).toBeFocused()
    await office.press('Space')
    await expect(page.locator('[data-order-total]')).toHaveText('1 605,50 ₽')
    await expect(page.locator('[data-checkout-submit]')).toBeEnabled()
    await expect(page.locator('[data-cdek-status]')).toContainText('TEST1')
    await expect(page.locator('[data-cdek-offices-wrap]')).toBeHidden()
    await page.getByRole('button', { name: 'Изменить пункт в списке' }).click()
    await expect(office).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: `artifacts/working-checkout/picker-${width}.png`, fullPage: true })
    await page.getByLabel('Город получения', { exact: true }).fill('Другой город')
    await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
    await expect(page.locator('[name=delivery_quote]')).toHaveValue('')
    expect(errors).toEqual([])
  })
}

test('city search recovers from errors without losing contacts', async ({ page }) => {
  await startCheckout(page)
  await page.getByLabel('Имя получателя').fill('Сохранённое имя')
  await page.route('**/checkout/cdek/cities/**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Повторите поиск позже.' }),
    }),
  )
  await page.getByLabel('Город получения', { exact: true }).fill('Тестовый город')
  await page.getByRole('button', { name: 'Найти город' }).click()
  await expect(page.locator('[data-cdek-search-status]')).toContainText('Повторите поиск позже')
  await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
  await page.unroute('**/checkout/cdek/cities/**')
  await page.getByRole('button', { name: 'Найти город' }).click()
  await expect(page.getByLabel('Выберите город')).toBeVisible()
  await expect(page.getByLabel('Имя получателя')).toHaveValue('Сохранённое имя')
})

test('customer delivery and contacts remain readable on desktop and mobile', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of ['delivery-and-payment', 'contacts']) {
      await page.goto(`/${route}/`)
      await expect(page.locator('.customer-page h1')).toBeVisible()
      if (route === 'delivery-and-payment') {
        await expect(page.locator('.customer-delivery')).toContainText('Расчёт после выбора пункта выдачи')
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: `artifacts/alfa-cdek/${route}-${width}.png`, fullPage: true })
    }
  }
})
