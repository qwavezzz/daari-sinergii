import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { browserPort, shopOrigin } from './origins.js'

test('email link opens one order on a new device and removes its token', async ({ browser }) => {
  const order = JSON.parse(readFileSync(`var/browser-order-${browserPort}.json`, 'utf8'))
  const customer = await browser.newContext({ viewport: { width: 390, height: 844 }, javaScriptEnabled: false })
  const page = await customer.newPage()
  const direct = await page.goto(`${shopOrigin}${order.path}`)
  expect(direct.status()).toBe(404)
  await page.goto(`${shopOrigin}${order.path}access/?token=${order.token}`)
  await expect(page).toHaveURL(`${shopOrigin}${order.path}`)
  await expect(page.getByRole('heading', { name: 'Оплачен', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'var/artifacts/shop/order-email-390.png', fullPage: true })
  const stranger = await browser.newContext()
  const strangerPage = await stranger.newPage()
  const response = await strangerPage.goto(`${shopOrigin}${order.path}access/?token=invalid`)
  expect(response.status()).toBe(410)
  await expect(strangerPage.getByRole('heading', { name: 'Ссылка на заказ недействительна' })).toBeVisible()
  await strangerPage.getByRole('link', { name: 'Вернуться в магазин' }).click()
  await expect(strangerPage).toHaveURL(`${shopOrigin}/`)
  await customer.close()
  await stranger.close()
})
