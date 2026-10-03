import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

for (const width of [1440, 390]) {
  test(`customer documents are readable and navigable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    for (const path of ['/legal/terms/', '/legal/privacy/', '/returns/', '/delivery-and-payment/']) {
      await page.goto(path)
      const toc = page.getByRole('navigation', { name: 'Содержание документа' })
      await expect(toc).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await toc.locator('a').nth(1).click()
      const heading = page.locator('#section-2')
      await expect(heading).toBeInViewport()
      expect((await heading.boundingBox()).y).toBeGreaterThan(70)
    }
    await page.goto('/legal/terms/')
    await expect(page.locator('h1')).toHaveText('Публичная оферта')
    await expect(page.locator('.customer-copy')).toContainText('1–3 рабочих дней')
    await mkdir('var/maintenance', { recursive: true })
    await page.screenshot({ path: `var/maintenance/offer-${width}.png` })
    await page.goto('/legal/privacy/')
    await expect(page.locator('.customer-copy')).toContainText('OpenStreetMap')
    await expect(page.locator('.customer-copy')).not.toContainText('Яндекс')
    expect(errors).toEqual([])
  })
}
