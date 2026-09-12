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
  // Verify actual inline playback and navigation in the Pages bundle.
  const android = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 7 Build/UP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36',
  })
  await android.addInitScript(() => {
    window.heroPlayCalls = 0
    const original = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function (...args) {
      if (this.matches('.hero-video')) window.heroPlayCalls++
      return original.apply(this, args)
    }
  })
  const androidPage = await android.newPage()
  const androidMedia = []
  androidPage.on('request', (request) => {
    if (request.resourceType() === 'media') androidMedia.push(request.url())
  })
  for (let visit = 0; visit < 2; visit++) {
    if (visit === 0) await androidPage.goto(origin + base)
    else await androidPage.reload()
    await expect(androidPage.locator('html')).toHaveClass(/\bjs\b/)
    await expect(androidPage.locator('.hero-video')).toBeVisible()
    await expect(androidPage.locator('#hero-title')).toBeVisible()
    await expect
      .poll(() => androidPage.locator('.hero-video').evaluate((video) => video.currentTime))
      .toBeGreaterThan(0)
    expect(
      await androidPage
        .locator('.hero-video')
        .evaluate(
          (video) =>
            video.playsInline &&
            video.muted &&
            !video.controls &&
            getComputedStyle(video).pointerEvents === 'none',
        ),
    ).toBe(true)
    expect(await androidPage.evaluate(() => document.fullscreenElement)).toBeNull()
    await androidPage.locator('#contact').scrollIntoViewIfNeeded()
    await expect(androidPage.locator('#contact')).toBeInViewport()
    expect(await androidPage.evaluate(() => window.heroPlayCalls)).toBeGreaterThan(0)
    await androidPage.goto(origin + base + 'materials/')
    await expect(androidPage.locator('h1')).toBeVisible()
    await androidPage.goBack()
    await expect(androidPage.locator('.hero-video')).toBeVisible()
    await androidPage.locator('#hero-title').scrollIntoViewIfNeeded()
    await expect
      .poll(() =>
        androidPage.locator('.hero-video').evaluate((video) => !video.paused && video.currentTime > 0),
      )
      .toBe(true)
  }
  expect(androidMedia.length).toBeGreaterThan(0)
  await androidPage.locator('#hero-title').scrollIntoViewIfNeeded()
  await androidPage.screenshot({ path: `${output}/landing-android-webview.png` })
  await androidPage.addInitScript(() => {
    const play = HTMLMediaElement.prototype.play
    let blocked = false
    HTMLMediaElement.prototype.play = function (...args) {
      if (this.matches('.hero-video') && !blocked) {
        blocked = true
        window.autoplayRejected = true
        return Promise.reject(new DOMException('Test autoplay restriction', 'NotAllowedError'))
      }
      return play.apply(this, args)
    }
  })
  await androidPage.goto(origin + base)
  await expect.poll(() => androidPage.evaluate(() => window.autoplayRejected)).toBe(true)
  await androidPage.locator('#hero-title').tap()
  await expect
    .poll(() => androidPage.locator('.hero-video').evaluate((video) => video.currentTime))
    .toBeGreaterThan(0)
  await android.close()
  const androidResult = { scenario: 'embedded Android inline playback and navigation', status: 'PASS' }
  results.push(androidResult)
  await writeFile(`${output}/android-verification.json`, JSON.stringify(androidResult, null, 2))
  console.log(JSON.stringify(androidResult))
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
