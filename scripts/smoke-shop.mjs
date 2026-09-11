import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
await mkdir('artifacts/shop', { recursive: true })
const results = []
for (const width of [1440, 1024, 768, 640, 390, 320]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  const response = await page.goto('http://shop.localhost:8000/', { waitUntil: 'networkidle' })
  await page.screenshot({ path: `artifacts/shop/catalog-empty-${width}.png` })
  await page.locator('#cart-toggle').click()
  await page.waitForTimeout(600)
  const dialogOpen = await page.locator('#cart-dialog').evaluate((node) => node.open)
  const emptyVisible = await page.locator('#cart-dialog').getByText('В корзине пока нет товаров').isVisible()
  await page.screenshot({ path: `artifacts/shop/cart-empty-${width}.png` })
  await page.keyboard.press('Escape')
  await page.waitForTimeout(250)
  const focusReturned = await page.locator('#cart-toggle').evaluate((node) => node === document.activeElement)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  results.push({
    width,
    status: response.status(),
    errors,
    dialogOpen,
    emptyVisible,
    focusReturned,
    overflow,
  })
  await context.close()
}
await browser.close()
await writeFile('artifacts/shop/smoke.json', JSON.stringify(results, null, 2))
console.log(JSON.stringify(results, null, 2))
