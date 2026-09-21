import { test, expect } from '@playwright/test'

const main = 'http://localhost:8001'
const schema = (page) =>
  page.locator('#page-structured-data').evaluate((node) => JSON.parse(node.textContent))

test('structured data follows full loads, HTMX navigation and history', async ({ page }) => {
  await page.goto(main + '/')
  await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(1)
  expect((await schema(page))['@type']).toBe('Organization')
  await page.locator('.desktop-nav a[href="/materials/"]').click()
  await expect(page).toHaveURL(main + '/materials/')
  await expect.poll(async () => (await schema(page))['@type']).toBe('BreadcrumbList')
  expect((await schema(page)).itemListElement).toHaveLength(2)
  await page.locator('.topic-directory a[href="/materials/water-systems/"]').click()
  await expect(page).toHaveURL(main + '/materials/water-systems/')
  await expect.poll(async () => (await schema(page)).itemListElement.length).toBe(3)
  expect((await schema(page)).itemListElement[2].item).toBe(main + '/materials/water-systems/')
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    main + '/materials/water-systems/',
  )
  await expect(page.locator('[aria-current="page"]')).toHaveText('Системы озонирования воды: подбор и монтаж')
  await page.goBack()
  await expect.poll(async () => (await schema(page)).itemListElement.length).toBe(2)
  await page.getByRole('link', { name: 'Вернуться к сайту', exact: true }).click()
  await expect(page).toHaveURL(main + '/#return')
  await expect.poll(async () => (await schema(page))['@type']).toBe('Organization')
  await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(1)
  await expect(page.locator('#return')).toBeAttached()
})

test('reviewed material pages render readable breadcrumbs and content at desktop and mobile widths', async ({
  page,
}) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    for (const slug of ['water-systems', 'oils', 'hydrolats']) {
      await page.goto(`${main}/materials/${slug}/`)
      await expect(page.getByRole('navigation', { name: 'Хлебные крошки' })).toBeVisible()
      await expect(page.locator('h1')).toBeVisible()
      expect(await page.locator('.material-overview h2').count()).toBeGreaterThanOrEqual(5)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(1)
      if (width !== 320)
        await page.screenshot({ path: `artifacts/seo-fixes/${slug}-${width}.png`, fullPage: true })
    }
  }
  expect(errors).toEqual([])
})

test('schema and material text are available without JavaScript; shop remains noindex', async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  const page = await context.newPage()
  await page.goto(main + '/')
  expect((await schema(page))['@type']).toBe('Organization')
  await page.goto(main + '/materials/water-systems/')
  expect((await schema(page)).itemListElement).toHaveLength(3)
  await expect(page.getByRole('heading', { name: 'Что подготовить для консультации' })).toBeVisible()
  await page.goto('http://shop.localhost:8001/')
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/)
  await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(0)
  await context.close()
})
