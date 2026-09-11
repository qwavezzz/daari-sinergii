import { chromium, expect } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { get } from 'node:http'

const origin = process.env.PAGES_TEST_ORIGIN || 'http://127.0.0.1:4173'
const base = process.env.PAGES_BASE_PATH || '/daari-sinergii/'
const output = process.env.PAGES_TEST_OUTPUT || 'artifacts/pages-preview'
await mkdir(output, { recursive: true })
const server = process.env.PAGES_TEST_ORIGIN
  ? null
  : spawn(
      resolve(process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'),
      ['scripts/serve-pages.py'],
      { stdio: 'ignore', windowsHide: true },
    )
let browser
const results = []
try {
  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      const status = await new Promise((done, reject) => {
        if (origin.startsWith('https:')) {
          fetch(origin + base + 'robots.txt').then(async (response) => {
            await response.text()
            done(response.status)
          }, reject)
        } else {
          get(origin + base + 'robots.txt', (response) => {
            response.resume()
            response.on('end', () => done(response.statusCode))
          }).on('error', reject)
        }
      })
      if (status === 200) break
    } catch {
      /* Server is starting. */
    }
    if (attempt === 49) throw new Error('Static preview server did not start')
    await new Promise((done) => setTimeout(done, 100))
  }
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await context.newPage()
    const errors = [],
      failed = [],
      mutations = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('response', (response) => {
      if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`)
    })
    page.on('request', (request) => {
      if (request.method() !== 'GET') mutations.push(request.method() + ' ' + request.url())
    })
    await page.goto(origin + base)
    await expect(page.locator('[data-page=landing]')).toBeVisible()
    await expect.poll(() => page.locator('.emergence-char').count()).toBeGreaterThan(0)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: `${output}/landing-${width}.png` })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.goto(origin + base + 'materials/')
    await expect(page.locator('h1')).toBeVisible()
    const pdf = page.locator('a[href$=".pdf"]').first()
    const pdfResponse = await context.request.get(new URL(await pdf.getAttribute('href'), origin).href)
    expect(pdfResponse.status()).toBe(200)
    expect(pdfResponse.headers()['content-type']).toContain('application/pdf')
    await page.goto(origin + base + 'shop/')
    await expect(page.locator('.catalog-count')).toContainText('16 товаров')
    await expect(page.locator('.product-tile')).toHaveCount(12)
    await page
      .locator('.product-tile-image img')
      .first()
      .evaluate((image) => image.decode())
    await page.screenshot({ path: `${output}/catalog-${width}.png` })
    await page.locator('.category-filter').getByRole('link', { name: 'Гидролаты', exact: true }).click()
    await expect(page).toHaveURL(/shop\/category\/demo-hydrolats\/$/)
    await expect(page.locator('.product-tile')).toHaveCount(6)
    await page.reload()
    await expect(page.locator('.product-tile')).toHaveCount(6)
    await page.locator('.category-filter').getByRole('link', { name: 'Все товары', exact: true }).click()
    await page.getByRole('link', { name: 'Следующая' }).click()
    await expect(page).toHaveURL(/shop\/page\/2\/$/)
    await expect(page.locator('.product-tile')).toHaveCount(4)
    await page.goto(origin + base + 'shop/products/demo-olive-50/')
    const add = page.getByRole('button', { name: 'Добавить в корзину' })
    await expect(add).toBeEnabled()
    await page.locator('#product-quantity').fill('2')
    await add.click()
    const drawer = page.getByRole('dialog', { name: 'Корзина' })
    await expect(drawer).toBeVisible()
    await expect(drawer.locator('.cart-total strong')).toHaveText('2 580 ₽')
    await drawer.locator('input[name=quantity]').fill('3')
    await drawer.getByRole('button', { name: 'Обновить', exact: true }).click()
    await expect(drawer.locator('.cart-total strong')).toHaveText('3 870 ₽')
    await page.screenshot({ path: `${output}/cart-${width}.png` })
    await expect(drawer.getByRole('button', { name: 'Оформить заказ' })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(drawer).not.toBeVisible()
    await page.reload()
    await page.locator('#cart-toggle').click()
    await expect(drawer.locator('.cart-total strong')).toHaveText('3 870 ₽')
    await page.keyboard.press('Escape')
    await page.goto(origin + base + 'shop/cart/')
    await expect(page.locator('.cart-page .cart-total strong')).toHaveText('3 870 ₽')
    await page.locator('.cart-page [data-demo-remove]').click()
    await expect(page.locator('.cart-page')).toContainText('Корзина пока пуста')
    await page.goto(origin + base + 'shop/products/demo-rosemary-200/')
    await expect(page.getByRole('button', { name: 'Добавить в корзину' })).toHaveCount(0)
    expect(errors).toEqual([])
    expect(failed).toEqual([])
    expect(mutations).toEqual([])
    results.push({ width, status: 'PASS', errors, failed, mutations })
    await context.close()
  }
  const noJS = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } })
  const page = await noJS.newPage()
  await page.goto(origin + base + 'shop/products/demo-olive-50/')
  await expect(page.getByRole('button', { name: 'Добавить в корзину' })).toBeDisabled()
  await expect(page.getByText('Для пробной корзины включите JavaScript.', { exact: false })).toBeVisible()
  await noJS.close()
  await writeFile(`${output}/verification.json`, JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results))
} finally {
  await browser?.close()
  server?.kill()
}
