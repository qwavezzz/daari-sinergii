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
    await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+\/$/)
    await expect(page.locator('.order-totals')).toContainText('1 605,50 ₽')
    await expect(page.locator('main')).toContainText('TEST1')
    await expect(page.getByRole('heading', { name: 'Не оплачен', exact: true })).toBeVisible()
    expect(errors).toEqual([])
  })
}

test('changing pickup invalidates the old total; unavailable delivery can be retried', async ({ page }) => {
  await startCheckout(page)
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
