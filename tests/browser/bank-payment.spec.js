import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { browserPort, shopOrigin } from './origins.js'

for (const javaScriptEnabled of [false, true]) {
  test(`checkout and retry reach bank with JavaScript=${javaScriptEnabled}`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled, viewport: { width: 390, height: 844 } })
    const page = await context.newPage()
    const violations = []
    page.on('console', (message) => {
      if (/form-action|Refused to send form data/.test(message.text())) violations.push(message.text())
    })
    // Fulfil the external document locally: this verifies browser CSP enforcement,
    // while making no request, creating no charge and sending no mail at the bank.
    // Playwright routing only intercepts the first URL in an HTTP redirect chain.
    // CDP Fetch pauses the redirected request too, before any network operation.
    const cdp = await context.newCDPSession(page)
    await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] })
    cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
      if (request.url.startsWith('https://alfa.rbsuat.com/')) {
        await cdp.send('Fetch.fulfillRequest', {
          requestId, responseCode: 200,
          responseHeaders: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }],
          body: Buffer.from('<!doctype html><html lang="ru"><title>Bank fixture</title><h1>Bank fixture</h1></html>').toString('base64'),
        })
      } else if (['127.0.0.1', 'localhost'].includes(new URL(request.url).hostname)) {
        await cdp.send('Fetch.continueRequest', { requestId })
      } else {
        await cdp.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' })
      }
    })
    await page.goto(`${shopOrigin}/products/test-product-2/`)
    await page.getByRole('button', { name: 'Добавить в корзину' }).click()
    if (javaScriptEnabled) await expect(page.locator('#cart-toggle [data-cart-count]')).toHaveText('1')
    await page.goto(`${shopOrigin}/checkout/`)
    await page.getByLabel('Имя', { exact: true }).fill('Проверка')
    await page.getByLabel('Фамилия', { exact: true }).fill('Оплаты')
    await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
    await page.getByLabel('Email', { exact: true }).fill('browser@example.test')
    await page.locator('[name=accept_terms]').check()
    const orderResponse = page.waitForResponse((response) => response.url() === `${shopOrigin}/checkout/` && response.request().method() === 'POST')
    await page.getByRole('button', { name: /Перейти к оплате/ }).click()
    const response = await orderResponse
    const destination = response.headers()['hx-redirect'] || response.headers().location
    expect(destination).toMatch(/^https:\/\/alfa\.rbsuat\.com\/payment\/merchants\//)
    await expect(page.getByRole('heading', { name: 'Bank fixture' })).toBeVisible()
    await expect(page).toHaveURL(destination)
    const number = new URL(destination).searchParams.get('mdOrder')
    const returnUrl = JSON.parse(readFileSync(`var/browser-bank-${browserPort}.json`, 'utf8'))[number]
    await page.goto(returnUrl)
    await expect(page.getByRole('heading', { name: 'Ожидает подтверждения', exact: true })).toBeVisible()
    await page.getByRole('button', { name: /Перейти к оплате/ }).click()
    await expect(page).toHaveURL(destination)
    await expect(page.getByRole('heading', { name: 'Bank fixture' })).toBeVisible()
    expect(violations).toEqual([])
    await context.close()
  })
}
