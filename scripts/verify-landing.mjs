import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { chromium } from '@playwright/test'
import { PNG } from 'pngjs'
import pixelmatch from 'pixelmatch'

const origin = process.env.QA_SITE_ORIGIN || 'http://localhost:8000'
const baseline = process.env.QA_BASELINE_ORIGIN || 'http://127.0.0.1:5173/daari-sinergii/'
const output = process.env.QA_LANDING_OUTPUT || 'artifacts/landing-migration'
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
const results = []
const failures = []

async function run(name, action) {
  if (process.env.QA_LANDING_SCENARIO && !name.includes(process.env.QA_LANDING_SCENARIO)) return
  try {
    const result = await action()
    results.push({ name, ...result })
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error: error.stack })
    console.log(`FAIL ${name}: ${error.message}`)
  }
}

async function waitForLanding(page) {
  await page.locator('[data-page="landing"]').waitFor()
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(350)
}

async function sceneState(page) {
  return page.evaluate(() => ({
    pins: document.querySelectorAll('.pin-spacer').length,
    chars: document.querySelectorAll('.emergence-char').length,
    nestedWords: document.querySelectorAll('.emergence-word .emergence-word').length,
    panels: document.querySelectorAll('.context-panel').length,
    smooth: document.documentElement.classList.contains('has-smooth-scroll'),
    scroll: window.scrollY,
    mainWidth: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }))
}

try {
  for (const width of [1440, 768, 390, 320]) {
    await run(`landing-${width}`, async () => {
      const height = width >= 768 ? 900 : 844
      const context = await browser.newContext({ viewport: { width, height } })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.goto(origin, { waitUntil: 'networkidle' })
      await waitForLanding(page)
      const state = await sceneState(page)
      assert.equal(state.panels, 5)
      assert.equal(state.pins, width >= 992 ? 1 : 0)
      assert.equal(state.nestedWords, 0)
      assert.ok(
        state.mainWidth <= state.viewport + 1,
        `Horizontal overflow: ${state.mainWidth} > ${state.viewport}`,
      )
      await page.screenshot({ path: `${output}/landing-${width}.png` })

      if (width < 992) {
        const toggle = page.getByRole('button', { name: 'Открыть меню', exact: true })
        await toggle.click()
        await page.waitForTimeout(800)
        await page.screenshot({ path: `${output}/menu-${width}.png` })
        assert.equal(await page.locator('#site-content').evaluate((node) => node.inert), true)
        await page.locator('#mobile-menu a').last().focus()
        await page.keyboard.press('Tab')
        assert.equal(await page.evaluate(() => document.activeElement.closest('#mobile-menu') !== null), true)
        await page.keyboard.press('Escape')
        await page.waitForTimeout(80)
        assert.equal(await toggle.getAttribute('aria-expanded'), 'false')
        assert.equal(await toggle.evaluate((node) => node === document.activeElement), true)
        assert.equal(await page.locator('#site-content').evaluate((node) => node.inert), false)
      }

      // Freeze only the media layer so old and new text geometry are comparable.
      await page.addStyleTag({ content: '.hero-video { visibility: hidden !important; }' })
      await page.locator('.hero-content').screenshot({ path: `${output}/hero-current-${width}.png` })
      const currentGeometry = await page.locator('.hero-content').evaluate((node) => {
        const rect = node.getBoundingClientRect()
        const title = node.querySelector('h1')
        return {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
          titleSize: getComputedStyle(title).fontSize,
        }
      })
      const oldPage = await context.newPage()
      await oldPage.goto(baseline, { waitUntil: 'networkidle' })
      await oldPage.evaluate(() => document.fonts.ready)
      await oldPage.addStyleTag({ content: '.hero-video { visibility: hidden !important; }' })
      await oldPage.locator('.hero-content').screenshot({ path: `${output}/hero-baseline-${width}.png` })
      const oldGeometry = await oldPage.locator('.hero-content').evaluate((node) => {
        const rect = node.getBoundingClientRect()
        return {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
          titleSize: getComputedStyle(node.querySelector('h1')).fontSize,
        }
      })
      for (const field of ['x', 'y', 'width', 'height']) {
        assert.ok(
          Math.abs(currentGeometry[field] - oldGeometry[field]) <= 1,
          `Hero ${field}: ${currentGeometry[field]} vs ${oldGeometry[field]}`,
        )
      }
      assert.equal(currentGeometry.titleSize, oldGeometry.titleSize)
      const oldImage = PNG.sync.read(await readFile(`${output}/hero-baseline-${width}.png`))
      const currentImage = PNG.sync.read(await readFile(`${output}/hero-current-${width}.png`))
      let difference = null
      if (oldImage.width === currentImage.width && oldImage.height === currentImage.height) {
        const diff = new PNG({ width: oldImage.width, height: oldImage.height })
        difference =
          pixelmatch(oldImage.data, currentImage.data, diff.data, oldImage.width, oldImage.height, {
            threshold: 0.1,
          }) /
          (oldImage.width * oldImage.height)
        await writeFile(`${output}/hero-diff-${width}.png`, PNG.sync.write(diff))
      }
      assert.deepEqual(errors, [])
      await context.close()
      return {
        state,
        currentGeometry,
        baselineGeometry: oldGeometry,
        differingPixelsRatio: difference,
        errors,
      }
    })
  }

  for (const mode of ['no-js', 'reduced-motion', 'iphone-safari-26']) {
    for (const width of [1440, 390]) {
      if (mode === 'iphone-safari-26' && width === 1440) continue
      await run(`${mode}-${width}`, async () => {
        const options = { viewport: { width, height: width === 1440 ? 900 : 844 } }
        if (mode === 'no-js') options.javaScriptEnabled = false
        if (mode === 'reduced-motion') options.reducedMotion = 'reduce'
        if (mode === 'iphone-safari-26')
          options.userAgent =
            'Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1'
        const context = await browser.newContext(options)
        const page = await context.newPage()
        const errors = []
        page.on('pageerror', (error) => errors.push(error.message))
        await page.goto(origin, { waitUntil: 'networkidle' })
        await page.screenshot({ path: `${output}/${mode}-${width}.png` })
        const state = await sceneState(page)
        assert.equal(state.pins, 0)
        assert.equal(state.chars, 0)
        assert.equal(state.smooth, false)
        const positions = await page
          .locator('.context-panel')
          .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().top))
        assert.ok(
          positions.every((top, index) => index === 0 || top > positions[index - 1]),
          'Industry content must remain in document flow',
        )
        assert.ok(state.mainWidth <= state.viewport + 1)
        if (mode === 'no-js') {
          await page.getByRole('link', { name: 'Все материалы по применению' }).click()
          assert.ok(page.url().includes('/materials/'))
        }
        assert.deepEqual(errors, [])
        await context.close()
        return { state, errors, simulatedUserAgent: mode === 'iphone-safari-26' }
      })
    }
  }

  await run('htmx-history-and-scene-disposal', async () => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(origin, { waitUntil: 'networkidle' })
    await waitForLanding(page)
    const initial = await sceneState(page)
    const sentinel = await page.evaluate(() => {
      window.__landingQaSentinel = crypto.randomUUID()
      return window.__landingQaSentinel
    })
    const cycles = []
    for (let cycle = 0; cycle < 3; cycle++) {
      await page.locator('.desktop-nav a[href="/materials/"]').click()
      await page.locator('[data-page="materials"]').waitFor()
      const materialState = await sceneState(page)
      assert.equal(materialState.pins, 0)
      assert.equal(materialState.chars, 0)
      assert.equal(materialState.smooth, false)
      assert.equal(
        await page.evaluate(() => window.__landingQaSentinel),
        sentinel,
        'HTMX must preserve the document',
      )
      await page.goBack()
      await waitForLanding(page)
      const backState = await sceneState(page)
      assert.equal(backState.pins, initial.pins)
      assert.equal(backState.chars, initial.chars)
      assert.equal(backState.nestedWords, 0)
      await page.goForward()
      await page.locator('[data-page="materials"]').waitFor()
      await page.locator('.materials-brand').click()
      await waitForLanding(page)
      cycles.push({ materialState, backState, returned: await sceneState(page) })
    }
    const anchors = []
    page.on('request', (request) => {
      if (request.headers()['hx-request']) anchors.push(request.url())
    })
    await page.locator('.hero-content a[href="#products"]').click()
    await page.waitForTimeout(1250)
    assert.equal(anchors.length, 0, 'Landing anchors must not fetch the page')
    assert.ok((await sceneState(page)).scroll > 0)
    await page.screenshot({ path: `${output}/anchor-products.png` })
    // Return to an actual industry scene, not only to scroll zero.
    const industryScroll = await page.locator('.contexts-track').evaluate((node) => {
      const rect = node.getBoundingClientRect()
      return rect.top + window.scrollY + (rect.height - window.innerHeight) * 0.45
    })
    await page.evaluate((top) => window.scrollTo({ top, behavior: 'instant' }), industryScroll)
    await page.waitForTimeout(600)
    const savedScroll = await page.evaluate(() => window.scrollY)
    await page.screenshot({ path: `${output}/industry-before-navigation.png` })
    await page.locator('.context-panel-sanatorium .context-panel-action').click()
    await page.locator('[data-page="materials"]').waitFor()
    await page.goBack()
    await waitForLanding(page)
    await page.waitForTimeout(500)
    const restoredScroll = await page.evaluate(() => window.scrollY)
    assert.ok(
      Math.abs(restoredScroll - savedScroll) <= 3,
      `Industry scroll was ${savedScroll}, restored ${restoredScroll}`,
    )
    await page.screenshot({ path: `${output}/industry-after-history.png` })
    await page.locator('.context-panel-sanatorium .context-panel-action').click()
    await page.locator('[data-page="materials"]').waitFor()
    await page.locator('.materials-header a[href="/#return"]').click()
    await waitForLanding(page)
    const returnedScroll = await page.evaluate(() => window.scrollY)
    assert.ok(
      Math.abs(returnedScroll - savedScroll) <= 3,
      `Return link restored ${returnedScroll} instead of ${savedScroll}`,
    )
    assert.deepEqual(errors, [])
    await context.close()
    return { cycles, savedScroll, restoredScroll, returnedScroll, errors }
  })
} finally {
  await browser.close()
  await writeFile(
    `${output}/report.json`,
    JSON.stringify(
      {
        baselineCommit: '8fa57e8',
        origin,
        results,
        failures,
        note: 'iPhone check simulates the user agent in Chromium; physical Safari validation remains separate.',
      },
      null,
      2,
    ),
  )
}
if (failures.length) process.exitCode = 1
