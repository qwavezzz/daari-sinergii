import { mainOrigin, shopOrigin } from './origins.js'
import { test, expect } from '@playwright/test'

test('notice survives navigation, then remembers dismissal without a tracking consent', async ({ page }) => {
  await page.goto('/')
  const notice = page.locator('[data-cookie-notice]')
  await expect(notice).toBeVisible()
  await notice.getByRole('link').click()
  await expect(page.getByRole('heading', { name: 'Использование cookie', exact: true })).toBeVisible()
  await expect(notice).toBeVisible()
  await notice.getByRole('button', { name: 'Понятно' }).click()
  await expect(notice).toBeHidden()
  await page.reload()
  await expect(notice).toBeHidden()
  await page.getByRole('link', { name: 'Контакты и реквизиты', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Контакты и реквизиты', exact: true })).toBeVisible()
  await expect(notice).toBeHidden()
  await page.evaluate(() => localStorage.setItem('dari-cookie-notice-v1', String(Date.now() - 181 * 86400000)))
  await page.reload()
  await expect(notice).toBeVisible()
})

test('blocked storage still allows closing the notice', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage blocked', 'SecurityError') },
  }))
  await page.goto('/')
  await page.locator('[data-cookie-notice]').getByRole('button', { name: 'Понятно' }).click()
  await expect(page.locator('[data-cookie-notice]')).toBeHidden()
})

test('cookie information is accessible without JavaScript on both hosts', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  const page = await context.newPage()
  for (const origin of [mainOrigin, shopOrigin]) {
    await page.goto(`${origin}/legal/cookies/`)
    await expect(page.getByRole('heading', { name: 'Использование cookie', exact: true })).toBeVisible()
    await expect(page.locator('[data-cookie-notice]')).toHaveCSS('position', 'static')
    await expect(page.locator('[data-cookie-notice] button')).toBeHidden()
  }
  await context.close()
})
