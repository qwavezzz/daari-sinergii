import { test, expect } from '@playwright/test'

test('mobile header keeps its geometry while the application module is delayed', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let release
  const moduleReady = new Promise((resolve) => {
    release = resolve
  })
  await page.route('**/static/dist/assets/shop-*.js', async (route) => {
    await moduleReady
    await route.continue()
  })
  await page.goto('/', { waitUntil: 'commit' })
  await expect(page.locator('.catalog-intro')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  const before = await page.locator('#main-content').boundingBox()
  release()
  await expect(page.locator('html')).toHaveClass(/\bjs\b/)
  const after = await page.locator('#main-content').boundingBox()
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1)
  await page.getByRole('button', { name: 'Открыть меню' }).click()
  await expect(page.locator('#shop-navigation')).toBeVisible()
})

for (const preference of ['reduce', 'save-data']) {
  test(`hero respects ${preference} without requesting video bytes`, async ({ browser }) => {
    const context = await browser.newContext({
      reducedMotion: preference === 'reduce' ? 'reduce' : 'no-preference',
    })
    if (preference === 'save-data') {
      await context.addInitScript(() => {
        if (navigator.connection) Object.defineProperty(navigator.connection, 'saveData', { get: () => true })
      })
    }
    const page = await context.newPage()
    const media = []
    page.on('request', (request) => {
      if (request.resourceType() === 'media') media.push(request.url())
    })
    await page.goto('http://localhost:8001/', { waitUntil: 'networkidle' })
    await expect(page.locator('html')).toHaveClass(/\bjs\b/)
    await expect(page.locator('#hero-title')).toBeVisible()
    expect(await page.locator('.hero-video').evaluate((video) => video.paused && !video.currentSrc)).toBe(
      true,
    )
    expect(media).toEqual([])
    const poster = await page.locator('.hero-video').getAttribute('poster')
    const background = await page.locator('.hero').evaluate((hero) => getComputedStyle(hero).backgroundImage)
    expect(background).toContain(poster)
    await context.close()
  })
}

test('leaving during deferred scene preparation cleans up the departed landing', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('http://localhost:8001/', { waitUntil: 'domcontentloaded' })
  await page.locator('.desktop-nav a[href="/materials/"]').click()
  await expect(page.locator('[data-page=materials]')).toBeVisible()
  await page.waitForTimeout(600)
  await expect(page.locator('.emergence-char, .pin-spacer')).toHaveCount(0)
  await page.goBack()
  await expect(page.locator('[data-page=landing]')).toBeVisible()
  await expect(page.locator('.emergence-char').first()).toBeAttached()
  await expect(page.locator('.pin-spacer')).toHaveCount(1)
  await expect(page.locator('.emergence-word .emergence-word')).toHaveCount(0)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(page.locator('.emergence-char, .pin-spacer')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('video starts while motion is downloading and a departed page is not initialized', async ({ page }) => {
  let release
  const motionReady = new Promise((resolve) => {
    release = resolve
  })
  await page.route('**/static/dist/assets/landing-*.js', async (route) => {
    await motionReady
    await route.continue()
  })
  try {
    await page.goto('http://localhost:8001/', { waitUntil: 'domcontentloaded' })
    await expect
      .poll(() => page.locator('.hero-video').evaluate((video) => video.currentTime))
      .toBeGreaterThan(0)
    await expect(page.locator('.pin-spacer')).toHaveCount(0)
    await page.locator('.desktop-nav a[href="/materials/"]').click()
    await expect(page.locator('[data-page=materials]')).toBeVisible()
    release()
    await page.waitForTimeout(300)
    await expect(page.locator('.emergence-char, .pin-spacer')).toHaveCount(0)
    await page.goBack()
    await expect(page.locator('[data-page=landing]')).toBeVisible()
    await expect(page.locator('.pin-spacer')).toHaveCount(1)
    await expect.poll(() => page.locator('.hero-video').evaluate((video) => !video.paused)).toBe(true)
  } finally {
    release()
  }
})
