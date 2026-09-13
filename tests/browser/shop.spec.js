import { test, expect } from '@playwright/test'

test('category URLs, pagination and history retain server HTML without a document reload', async ({
  page,
}) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.locator('.product-tile .product-category')).toHaveCount(0)
  await page.evaluate(() => {
    window.navigationSentinel = 'kept'
  })
  await page.getByRole('link', { name: 'Тестовая пустая категория', exact: true }).click()
  await expect(page).toHaveURL(/category=test-empty/)
  await expect(page.getByRole('heading', { name: 'В этой категории пока нет товаров' })).toBeVisible()
  await page.goBack()
  await expect(page.locator('.product-tile')).toHaveCount(12)
  await expect.poll(() => page.evaluate(() => window.navigationSentinel)).toBe('kept')
  await page.getByRole('link', { name: 'Следующая' }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.locator('.product-tile')).toHaveCount(9)
  expect(errors).toEqual([])
})

test('cart drawer, server mutation, focus, cross-tab persistence and safe checkout', async ({
  page,
  context,
  request,
}) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/products/test-product-1/')
  await expect(page.locator('.product-title .product-category')).toBeVisible()
  await page.getByRole('button', { name: 'Добавить в корзину' }).click()
  const drawer = page.getByRole('dialog', { name: 'Корзина' })
  await expect(drawer).toBeVisible()
  await expect(drawer.locator('.cart-item')).toHaveCount(1)
  await expect(drawer.getByRole('button', { name: 'Обновить', exact: true })).toBeHidden()
  await expect(drawer.locator('.cart-total strong')).toHaveText('1 290,50 ₽')
  await page.waitForTimeout(300)
  await page.screenshot({ path: 'artifacts/shop/cart-filled-1440.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'artifacts/shop/cart-filled-390.png' })
  await page.route('**/cart/update/**', (route) => route.abort())
  await drawer.locator('input[name=quantity]').fill('2')
  await expect(drawer.locator('#cart-error')).toBeVisible()
  await expect(drawer.locator('[data-quantity-status]')).toContainText('Не удалось обновить количество')
  await expect(drawer.locator('input[name=quantity]')).toHaveValue('2')
  await expect(drawer.locator('.checkout-link')).toHaveAttribute('aria-disabled', 'true')
  await expect(drawer.locator('.cart-total strong')).toHaveText('1 290,50 ₽')
  await page.unroute('**/cart/update/**')
  await drawer.getByRole('button', { name: 'Повторить', exact: true }).click()
  await expect(drawer.locator('.cart-total strong')).toHaveText('2 581 ₽')
  await drawer.locator('input[name=quantity]').fill('3')
  await expect(drawer.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
  await expect(page.locator('#cart-toggle [data-cart-count]')).toHaveText('3')
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Добавить в корзину' })).toBeFocused()
  const second = await context.newPage()
  await second.goto('/cart/')
  await expect(second.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
  await second.close()
  await page.locator('#cart-toggle').click()
  await drawer.getByRole('link', { name: 'Оформить заказ' }).click()
  await expect(page).toHaveURL(/checkout/)
  await expect(drawer).not.toBeVisible()
  await page.getByLabel('Имя получателя').fill('Тестовый покупатель')
  await page.getByLabel('Телефон', { exact: true }).fill('+79000000000')
  await page.getByLabel('Email', { exact: true }).fill('qa@example.invalid')
  await page.getByLabel('Способ получения').selectOption({ label: 'Тестовая доставка' })
  await expect(page.locator('.checkout-total dd')).toHaveText('4 221,50 ₽')
  await expect(page.getByLabel('Имя получателя')).toHaveValue('Тестовый покупатель')
  await page.getByLabel('Адрес', { exact: false }).fill('Тестовый адрес')
  await page.locator('[name=accept_terms]').check()
  await page.getByRole('button', { name: /Перейти к оплате/ }).click()
  await expect(page).toHaveURL(/orders\/[0-9a-f-]+\/$/)
  await expect(page.getByRole('heading', { name: 'Не оплачен', exact: true })).toBeVisible()
  await expect(page.locator('.order-totals')).toContainText('4 221,50 ₽')
  await page.screenshot({ path: 'artifacts/shop/order-390.png', fullPage: true })
  const orderUrl = page.url()
  const response = await request.get(orderUrl)
  expect(response.status()).toBe(404)
  expect(errors).toEqual([])
})

test('automatic quantity updates keep the layout stable, reject invalid input and survive reload', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/products/test-product-1/')
  await page.getByRole('button', { name: 'Добавить в корзину' }).click()
  const drawer = page.getByRole('dialog', { name: 'Корзина' })
  await expect(drawer.locator('.cart-item')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await page.goto('/cart/')
  const cart = page.locator('.cart-page')
  await expect(cart.getByRole('button', { name: 'Обновить', exact: true })).toBeHidden()
  const summaryBox = await cart.locator('.cart-summary').boundingBox()
  let release
  const responseGate = new Promise((resolve) => {
    release = resolve
  })
  let mutations = 0
  await page.route('**/cart/update/**', async (route) => {
    mutations++
    await responseGate
    await route.continue()
  })
  await cart.locator('input[name=quantity]').fill('2')
  await cart.locator('input[name=quantity]').fill('3')
  await expect(cart.locator('.cart-content')).toHaveAttribute('aria-busy', 'true')
  await expect(cart.locator('[data-quantity-status]')).toBeHidden()
  const pendingBox = await cart.locator('.cart-summary').boundingBox()
  expect(Math.abs(pendingBox.height - summaryBox.height)).toBeLessThan(1)
  expect(Math.abs(pendingBox.y - summaryBox.y)).toBeLessThan(1)
  await expect(cart.locator('.cart-total strong')).toHaveText('1 290,50 ₽')
  await expect(cart.locator('.checkout-link')).toHaveAttribute('aria-disabled', 'true')
  expect(mutations).toBe(1)
  await page.screenshot({ path: 'artifacts/shop/cart-quantity-pending-390.png' })
  release()
  await expect(cart.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
  await expect(cart.locator('.cart-content')).toHaveAttribute('aria-busy', 'false')
  await expect(cart.locator('.checkout-link')).not.toHaveAttribute('aria-disabled', 'true')
  await cart.locator('input[name=quantity]').fill('0')
  await expect(cart.locator('[data-quantity-status]')).toContainText('допустимое целое количество')
  await cart.locator('.checkout-link').focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/cart\/$/)
  expect(mutations).toBe(1)
  await cart.locator('input[name=quantity]').fill('51')
  await expect(cart.locator('.shop-error')).toBeVisible()
  await expect(cart.locator('input[name=quantity]')).toHaveValue('3')
  await expect(cart.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
  await page.reload()
  await expect(cart.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
  // The server may save a quantity even when the response never reaches us.
  await page.unroute('**/cart/update/**')
  await page.route('**/cart/update/**', async (route) => {
    await route.fetch()
    await route.abort()
  })
  await cart.locator('input[name=quantity]').fill('2')
  await expect(cart.locator('[data-quantity-status]')).toContainText('Не удалось обновить количество')
  await page.screenshot({ path: 'artifacts/shop/cart-quantity-error-390.png' })
  await page.unroute('**/cart/update/**')
  const confirmedUpdate = page.waitForResponse(
    (response) => response.url().includes('/cart/update/') && response.ok(),
  )
  await cart.locator('input[name=quantity]').fill('3')
  await confirmedUpdate
  await expect(cart.locator('[data-quantity-status]')).toBeHidden()
  await page.reload()
  await expect(cart.locator('.cart-total strong')).toHaveText('3 871,50 ₽')
})

test('unavailable products cannot be purchased and network errors preserve catalog', async ({ page }) => {
  await page.goto('/products/test-unavailable/')
  await expect(page.getByText('Нет в наличии', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Добавить в корзину' })).toHaveCount(0)
  await page.goto('/')
  await page.route('**/?category=test-empty', (route) => route.abort())
  await page.getByRole('link', { name: 'Тестовая пустая категория', exact: true }).click()
  await expect(page.locator('#request-feedback')).toBeVisible()
  await expect(page.locator('.product-tile')).toHaveCount(12)
  await page.unroute('**/?category=test-empty')
  await page.getByRole('button', { name: 'Повторить', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'В этой категории пока нет товаров' })).toBeVisible()
})

test('catalog, full cart and checkout operate without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()
  await page.goto('http://shop.localhost:8001/products/test-product-2/')
  await expect(page.getByRole('navigation', { name: 'Навигация магазина' })).toBeVisible()
  await expect(
    page
      .getByRole('navigation', { name: 'Навигация магазина' })
      .getByRole('link', { name: 'Каталог', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeHidden()
  await expect(page.locator('[data-gallery-slide]')).toHaveCount(8)
  await expect(page.locator('.gallery-controls')).toBeHidden()
  await page.locator('.gallery-track').evaluate((node) => {
    node.scrollLeft = node.scrollWidth
  })
  await expect(page.locator('[data-gallery-slide]').last()).toBeInViewport()
  await expect(page.locator('.review-item blockquote p[id]')).toContainText('Это тестовый отзыв')
  await expect(page.locator('.review-item blockquote p[id]')).toBeVisible()
  await page.getByRole('button', { name: 'Добавить в корзину' }).click()
  await expect(page).toHaveURL(/cart/)
  await expect(page.locator('.cart-item')).toHaveCount(1)
  await page.getByRole('spinbutton', { name: 'Количество', exact: true }).fill('2')
  await page.getByRole('button', { name: 'Обновить', exact: true }).click()
  await expect(page.locator('.cart-total strong')).toHaveText('2 581 ₽')
  await page.getByRole('link', { name: 'Оформить заказ' }).click()
  await expect(page.getByRole('heading', { name: 'Оформление заказа' })).toBeVisible()
  await context.close()
})

test('responsive gallery, product and cart stay within viewport at 320–1440px', async ({ page }) => {
  for (const width of [1440, 1024, 768, 640, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/products/test-product-2/')
    await expect(page.locator('.gallery-controls')).toContainText('1 / 8')
    await page.getByRole('button', { name: 'Следующее изображение' }).click()
    await expect(page.locator('.gallery-controls')).toContainText('2 / 8')
    await expect(page.locator('.gallery-thumbnails [data-slide="1"]')).toHaveAttribute('aria-current', 'true')
    if (width === 1440) {
      const disclosure = page.locator('.review-item').getByRole('button', { name: 'Читать полностью' })
      await expect(disclosure).toHaveAttribute('aria-expanded', 'false')
      await expect(page.locator('.review-item blockquote p[id]')).toBeHidden()
      await disclosure.click()
      await expect(page.locator('.review-item blockquote p[id]')).toBeVisible()
      await expect(page.locator('.review-item button')).toHaveAttribute('aria-expanded', 'true')
      await expect(page.locator('.review-item strong')).toHaveText('Тестовый автор')
      const video = page
        .locator('.product-videos')
        .getByRole('link', { name: 'Смотреть видео (новая вкладка)' })
      await expect(video).toHaveAttribute('href', 'https://www.youtube.com/watch?v=test_video')
      await expect(video).toHaveAttribute('target', '_blank')
    }
    await page.screenshot({ path: `artifacts/shop/product-${width}.png`, fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('#cart-toggle').click()
    const drawer = page.getByRole('dialog', { name: 'Корзина' })
    await expect(drawer).toBeVisible()
    const box = await drawer.boundingBox()
    expect(Math.round(box.width)).toBe(width < 640 ? width : 440)
    await page.keyboard.press('Tab')
    expect(await drawer.evaluate((node) => node.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Shift+Tab')
    expect(await drawer.evaluate((node) => node.contains(document.activeElement))).toBe(true)
    await page.screenshot({ path: `artifacts/shop/cart-${width}.png` })
    await page.keyboard.press('Escape')
    await expect(drawer).not.toBeVisible()
  }
})

test('twenty cart lines remain reachable with fixed summary, short viewport and doubled text', async ({
  page,
}) => {
  test.setTimeout(60000)
  await page.goto('/products/test-product-1/')
  const token = await page.locator('[name=csrfmiddlewaretoken]').first().inputValue()
  // Exercise the public CSRF-protected endpoints in the browser's own session.
  for (let index = 1; index <= 20; index++) {
    const productResponse = await page.request.get(`/products/test-product-${index}/`)
    expect(productResponse.ok()).toBe(true)
    const addUrl = (await productResponse.text()).match(/action="(\/cart\/add\/\d+\/)"/)[1]
    const added = await page.request.post(addUrl, {
      form: { quantity: '1', csrfmiddlewaretoken: token },
      headers: { Referer: 'http://shop.localhost:8001/' },
      maxRedirects: 0,
    })
    expect(added.status()).toBe(302)
  }
  await page.locator('#cart-toggle').click()
  const drawer = page.getByRole('dialog', { name: 'Корзина' })
  const list = drawer.locator('.cart-items')
  const checkout = drawer.getByRole('link', { name: 'Оформить заказ' })
  const lastQuantity = drawer
    .locator('.cart-item')
    .last()
    .getByRole('spinbutton', { name: 'Количество', exact: true })
  await expect(drawer.locator('.cart-item')).toHaveCount(20)
  await expect(drawer.locator('.cart-total strong')).toHaveText('25 810 ₽')
  await expect(page.locator('body')).toHaveCSS('position', 'fixed')
  await expect(list).toHaveCSS('overflow-y', 'auto')
  const summaryTop = (await drawer.locator('.cart-summary').boundingBox()).y
  const backgroundY = await page.evaluate(() => scrollY)
  await list.evaluate((node) => {
    node.scrollTop = node.scrollHeight
  })
  await expect(lastQuantity).toBeInViewport()
  await expect(checkout).toBeInViewport()
  expect(Math.abs((await drawer.locator('.cart-summary').boundingBox()).y - summaryTop)).toBeLessThan(1)
  expect(await page.evaluate(() => scrollY)).toBe(backgroundY)
  await list.evaluate((node) => {
    node.scrollTop = 0
  })
  await page.screenshot({ path: 'artifacts/shop/cart-20-1440.png' })

  await page.setViewportSize({ width: 390, height: 400 })
  await expect(drawer).toHaveCSS('overflow-y', 'auto')
  await expect(list).toHaveCSS('overflow-y', 'visible')
  await drawer.evaluate((node) => {
    node.scrollTop = node.scrollHeight
  })
  await expect(lastQuantity).toBeInViewport()
  expect(await drawer.evaluate((node) => node.scrollTop)).toBeGreaterThan(0)
  await drawer.evaluate((node) => {
    node.scrollTop = 0
  })
  await expect(checkout).toBeInViewport()
  await page.screenshot({ path: 'artifacts/shop/cart-short-390.png' })

  await page.setViewportSize({ width: 390, height: 844 })
  // Text-only enlargement: capture original computed sizes first, then double each.
  // Layout widths and overflow rules remain untouched, as with browser text zoom.
  await page.evaluate(() => {
    const sizes = [...document.querySelectorAll('body, body *')].map((node) => [
      node,
      parseFloat(getComputedStyle(node).fontSize),
    ])
    for (const [node, size] of sizes) node.style.fontSize = `${size * 2}px`
  })
  await expect(drawer.locator('.cart-total strong')).toHaveCSS('font-size', '40px')
  await expect(drawer).toHaveClass(/whole-scroll/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await drawer.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true)
  await drawer.evaluate((node) => {
    node.scrollTop = node.scrollHeight
  })
  await expect(lastQuantity).toBeInViewport()
  await lastQuantity.focus()
  await expect(lastQuantity).toBeFocused()
  await checkout.scrollIntoViewIfNeeded()
  await expect(checkout).toBeInViewport()
  await page.screenshot({ path: 'artifacts/shop/cart-text-200.png' })
  await page.getByRole('button', { name: 'Закрыть корзину' }).scrollIntoViewIfNeeded()
  await page.getByRole('button', { name: 'Закрыть корзину' }).click()
  await expect(drawer).not.toBeVisible()
  await expect(page.locator('#cart-toggle')).toBeFocused()
  await expect(page.locator('body')).not.toHaveCSS('position', 'fixed')
})
