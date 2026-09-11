import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const output = 'artifacts/baseline'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
const report = []
for (const width of [1440, 768, 390, 320]) {
  const height = width >= 768 ? 900 : 844
  const context = await browser.newContext({
    viewport: { width, height },
    recordVideo: { dir: output, size: { width, height } },
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('http://127.0.0.1:5173/daari-sinergii/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1800)
  await page.screenshot({ path: `${output}/landing-${width}.png` })
  if (width < 992) {
    await page.getByRole('button', { name: 'Открыть меню', exact: true }).click()
    await page.waitForTimeout(900)
    await page.screenshot({ path: `${output}/menu-${width}.png` })
    await page.keyboard.press('Escape')
  }
  for (let index = 0; index < 10; index++) {
    await page.mouse.wheel(0, 650)
    await page.waitForTimeout(350)
  }
  await page.goto('http://127.0.0.1:5173/daari-sinergii/#/materials/sport', { waitUntil: 'networkidle' })
  await page.screenshot({ path: `${output}/materials-${width}.png`, fullPage: true })
  report.push({ width, errors })
  await context.close()
}
await browser.close()
await writeFile(`${output}/report.json`, JSON.stringify({ commit: '8fa57e8', captures: report }, null, 2))
console.log(JSON.stringify(report))
