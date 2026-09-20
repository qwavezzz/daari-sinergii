// Public pages only: no login, cart changes, orders, forms or email.
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'

const output = 'artifacts/readiness'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
const records = []
try {
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await context.newPage()
    let errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    for (const [name, url] of [
      ['home', 'https://dari-sinergii.ru/'],
      ['materials', 'https://dari-sinergii.ru/materials/'],
      ['catalog', 'https://shop.dari-sinergii.ru/'],
      ['product', 'https://shop.dari-sinergii.ru/products/demo-olive-50/'],
    ]) {
      errors = []
      try {
        const response = await page.goto(url, { waitUntil: 'load', timeout: 30000 })
        await page.waitForTimeout(1500)
        const metrics = await page.evaluate(() => ({
          title: document.title,
          canonical: document.querySelector('link[rel="canonical"]')?.href,
          robots: document.querySelector('meta[name="robots"]')?.content,
          jsonLdCount: document.querySelectorAll('script[type="application/ld+json"]').length,
          h1: [...document.querySelectorAll('h1')].map((item) => item.textContent.trim()),
          horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
          brokenImages: [...document.images].filter((img) => img.complete && !img.naturalWidth).length,
        }))
        await page.screenshot({ path: `${output}/${name}-${width}.png` })
        records.push({ url, width, status: response.status(), metrics, errors: [...errors] })
        console.log(name, width, JSON.stringify(metrics), 'errors', errors.length)
      } catch (error) {
        records.push({ url, width, error: error.message })
      }
    }
    await context.close()
  }
} finally {
  await browser.close()
}
await writeFile(`${output}/browser-live.json`, JSON.stringify(records, null, 2))
