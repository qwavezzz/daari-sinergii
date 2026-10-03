import { test, expect } from '@playwright/test'

for (const javaScriptEnabled of [true, false]) {
  test(`trial payment preserves total through cancel/retry/success (JS ${javaScriptEnabled})`, async ({
    browser,
  }) => {
    const context = await browser.newContext({
      javaScriptEnabled,
      viewport: { width: 390, height: 844 },
    })
    const page = await context.newPage()
    await page.goto('http://shop.localhost:8001/products/test-product-2/')
    await Promise.all([
      page.waitForResponse(
        (response) => response.url().includes('/cart/set/') && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Добавить в корзину' }).click(),
    ])
    if (javaScriptEnabled) {
      await expect(page.locator('#cart-dialog')).not.toBeVisible()
      await expect(page.locator('#cart-toggle [data-cart-count]')).toHaveText('1')
    }
    await page.goto('http://shop.localhost:8001/checkout/')
    await page.getByLabel('Имя', { exact: true }).fill('Проверка пути покупки')
    await page.getByLabel('Фамилия', { exact: true }).fill('Покупатель')
    await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
    await page.getByLabel('Email', { exact: true }).fill('trial@example.invalid')
    await page.locator('[name=accept_terms]').check()
    await page.locator('[data-checkout-submit]').click()
    await expect(page).toHaveURL(/\/payments\/trial\/[0-9a-f-]+\/$/)
    const url = page.url()
    await expect(page.locator('.order-totals')).toContainText('1 290,50 ₽')
    await expect(page.getByText('Деньги не списываются.', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Отменить пробную оплату' }).click()
    await expect(page.getByRole('heading', { name: 'Проба отменена' })).toBeVisible()
    await page.getByRole('button', { name: 'Повторить пробную оплату' }).click()
    await expect(page.getByRole('heading', { name: 'Пробная оплата', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Завершить пробную оплату' }).click()
    await expect(page.getByRole('heading', { name: 'Проба завершена' })).toBeVisible()
    await expect(page.locator('.order-totals')).toContainText('1 290,50 ₽')
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Проба завершена' })).toBeVisible()
    const foreign = await browser.newContext()
    expect((await foreign.request.get(url)).status()).toBe(404)
    await foreign.close()
    await context.close()
  })
}
