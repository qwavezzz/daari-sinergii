import { test, expect } from '@playwright/test'

test('email errors appear on blur and clear after correction, including after a delivery change', async ({
  page,
}) => {
  await page.goto('/products/test-product-1/')
  await page.getByRole('button', { name: 'Добавить в корзину', exact: true }).click()
  await expect(page.locator('#cart-toggle [data-cart-count]')).toHaveText('1')
  await page.goto('/checkout/')
  const email = page.getByLabel('Email', { exact: true })
  const error = page.locator('#email-error')
  await expect(error).toBeHidden()
  await expect(page.getByLabel('Телефон', { exact: true })).toHaveAttribute('placeholder', '(999) 123 45 67')
  await expect(page.locator('#phone-help')).toHaveText('Формат: +7 (999) 123 45 67')
  await email.fill('dsadasdadas')
  await email.press('Tab')
  await expect(error).toContainText('Проверьте email')
  await expect(email).toHaveAttribute('aria-invalid', 'true')
  await email.fill('buyer@example.ru')
  await expect(error).toBeHidden()
  expect(await email.evaluate((node) => node.checkValidity())).toBe(true)
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовый СДЭК до ПВЗ' })
  await expect(page.locator('[data-cdek-picker]')).toBeVisible()
  await email.fill('buyer@local')
  await email.press('Tab')
  await expect(error).toContainText('Проверьте email')
})
