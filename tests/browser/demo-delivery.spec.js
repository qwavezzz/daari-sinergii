import { test, expect } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`demo delivery is labeled throughout checkout and trial at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    await page.route('https://tile.openstreetmap.org/**', (route) =>
      route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#f0f0e8"/></svg>',
      }),
    )
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('/products/test-product-1/')
    await page.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(page.locator('#cart-toggle [data-cart-count]')).toHaveText('1')
    await page.goto('/checkout/')
    await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
    await expect(page.locator('[data-cdek-picker] .shop-warning')).toContainText('это не тариф СДЭК')
    await expect(page.locator('[data-checkout-submit]')).toBeDisabled()
    await page.getByLabel('Имя', { exact: true }).fill('Пробный')
    await page.getByLabel('Фамилия', { exact: true }).fill('Покупатель')
    await page.getByLabel('Телефон', { exact: true }).fill('+79991234567')
    await page.getByLabel('Email', { exact: true }).fill('demo@example.invalid')
    await page.getByRole('button', { name: 'ПВЗ TEST1: Тестовый адрес, 10', exact: true }).click()
    await page.getByRole('button', { name: 'Выбрать этот пункт' }).click()
    await expect(page.locator('[data-delivery-price]')).toHaveText('500,00 ₽')
    await expect(page.locator('[data-order-total]')).toHaveText('1 790,50 ₽')
    await expect(page.locator('[data-cdek-status]')).toContainText('Срок доставки не рассчитывается')
    await page.locator('[name=accept_terms]').check()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `var/test-results/demo-checkout-${width}.png`, fullPage: true })
    await page.locator('[data-checkout-submit]').click()
    await expect(page).toHaveURL(/\/payments\/trial\//)
    await expect(page.locator('main')).toContainText('Учебная доставка — 500 ₽')
    await expect(page.locator('main')).toContainText('это не тариф СДЭК')
    await page.getByRole('button', { name: 'Завершить пробную оплату' }).click()
    await expect(page.getByRole('heading', { name: 'Проба завершена' })).toBeVisible()
    await page.getByRole('link', { name: 'Посмотреть заказ' }).click()
    await expect(page.locator('main')).toContainText('Учебная доставка — 500 ₽')
    await expect(page.locator('main')).not.toContainText('None')
    expect(errors).toEqual([])
  })
}
