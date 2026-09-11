import { chromium } from '@playwright/test'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'

const output = process.env.PERF_OUTPUT || 'artifacts/performance-after'
await mkdir(output, { recursive: true })
const manifest = JSON.parse(await readFile('static/dist/.vite/manifest.json', 'utf8'))
const bundles = {}
for (const name of ['site', 'shop']) {
  const seen = new Set()
  function visit(key) {
    const item = manifest[key]
    seen.add(item.file)
    for (const css of item.css || []) seen.add(css)
    for (const dependency of item.imports || []) visit(dependency)
  }
  visit(`frontend/${name}.js`)
  bundles[name] = []
  for (const file of seen) {
    const bytes = await readFile(`static/dist/${file}`)
    bundles[name].push({ file, bytes: bytes.length, gzipBytes: gzipSync(bytes).length })
  }
}
console.log('BUNDLES', JSON.stringify(bundles))
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
const results = []
for (const mode of ['desktop', 'mobile-slow']) {
  for (const surface of ['site', 'shop']) {
    const slow = mode === 'mobile-slow'
    const context = await browser.newContext({
      viewport: { width: slow ? 390 : 1440, height: slow ? 844 : 900 },
      deviceScaleFactor: slow ? 2 : 1,
      isMobile: slow,
      hasTouch: slow,
    })
    const page = await context.newPage()
    const session = await context.newCDPSession(page)
    await session.send('Network.enable')
    await session.send('Network.setCacheDisabled', { cacheDisabled: true })
    await session.send('Performance.enable')
    if (slow) {
      await session.send('Emulation.setCPUThrottlingRate', { rate: 4 })
      await session.send('Network.emulateNetworkConditions', {
        offline: false,
        latency: 150,
        downloadThroughput: 200000,
        uploadThroughput: 93750,
        connectionType: 'cellular4g',
      })
    }
    const requests = new Map()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    session.on('Network.requestWillBeSent', (event) =>
      requests.set(event.requestId, { url: event.request.url, type: event.type, bytes: 0, finished: false }),
    )
    session.on('Network.responseReceived', (event) =>
      Object.assign(requests.get(event.requestId) || {}, {
        status: event.response.status,
        encoding: event.response.headers['Content-Encoding'] || '',
        mime: event.response.mimeType,
      }),
    )
    session.on('Network.dataReceived', (event) => {
      const item = requests.get(event.requestId)
      if (item) item.bytes += event.encodedDataLength || 0
    })
    session.on('Network.loadingFinished', (event) => {
      const item = requests.get(event.requestId)
      if (item) {
        item.bytes = event.encodedDataLength
        item.finished = true
      }
    })
    await page.addInitScript(() => {
      window.__perfAudit = { lcp: [], shifts: [], longTasks: [], events: [], frames: [] }
      for (const [type, key] of [
        ['largest-contentful-paint', 'lcp'],
        ['layout-shift', 'shifts'],
        ['longtask', 'longTasks'],
        ['event', 'events'],
      ]) {
        try {
          new PerformanceObserver((list) =>
            list.getEntries().forEach((entry) => {
              window.__perfAudit[key].push({
                ...entry.toJSON(),
                elementName: entry.element?.tagName,
                elementClass: typeof entry.element?.className === 'string' ? entry.element.className : '',
                url: entry.url,
              })
            }),
          ).observe({ type, buffered: true, ...(type === 'event' ? { durationThreshold: 16 } : {}) })
        } catch {}
      }
    })
    const origin = surface === 'shop' ? 'http://shop.localhost:8000' : 'http://localhost:8000'
    console.log('START', mode, surface)
    await page.goto(origin, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(slow ? 12000 : 3000)
    const initial = await page.evaluate(() => ({
      navigation: performance.getEntriesByType('navigation')[0].toJSON(),
      paint: performance.getEntriesByType('paint').map((item) => item.toJSON()),
      lcp: window.__perfAudit.lcp.at(-1),
      cls: window.__perfAudit.shifts
        .filter((item) => !item.hadRecentInput)
        .reduce((sum, item) => sum + item.value, 0),
      longTasks: window.__perfAudit.longTasks,
      dom: document.querySelectorAll('*').length,
      images: [...document.images].map((item) => ({
        url: item.currentSrc,
        width: item.clientWidth,
        naturalWidth: item.naturalWidth,
        complete: item.complete,
      })),
      video: [...document.querySelectorAll('video')].map((item) => ({
        source: item.currentSrc,
        paused: item.paused,
        width: item.videoWidth,
        height: item.videoHeight,
        readyState: item.readyState,
        droppedFrames: item.getVideoPlaybackQuality?.().droppedVideoFrames,
      })),
    }))
    const initialRequests = [...requests.values()].map((item) => ({ ...item }))
    const before = (await session.send('Performance.getMetrics')).metrics
    await page.evaluate(() => {
      let last = performance.now()
      window.__perfAudit.frameEnd = last + 4500
      const frame = (time) => {
        window.__perfAudit.frames.push(time - last)
        last = time
        if (time < window.__perfAudit.frameEnd) requestAnimationFrame(frame)
      }
      requestAnimationFrame(frame)
    })
    if (surface === 'site') {
      for (let index = 0; index < 10; index++) {
        await page.mouse.wheel(0, 700)
        await page.waitForTimeout(400)
      }
    } else {
      await page.locator('#cart-toggle').click()
      await page.waitForTimeout(1200)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(3000)
    }
    await page.waitForTimeout(600)
    const after = (await session.send('Performance.getMetrics')).metrics
    const runtime = await page.evaluate(() => ({
      frames: window.__perfAudit.frames,
      events: window.__perfAudit.events,
      scrollY,
      errors: [],
      totalLongTasks: window.__perfAudit.longTasks,
    }))
    const metric = (list, name) => list.find((item) => item.name === name)?.value || 0
    const times = runtime.frames.filter((value) => value > 0).sort((a, b) => a - b)
    const result = {
      mode,
      surface,
      constraints: slow
        ? '390x844 DPR2, CPU4x, 1.6Mbps, latency150ms, cache disabled, local Django dev, no compression'
        : '1440x900 DPR1, unthrottled, cache disabled, local Django dev, no compression',
      initial,
      initialRequests,
      finalRequests: [...requests.values()],
      errors,
      runtime: {
        scrollY: runtime.scrollY,
        frameMedian: times[Math.floor(times.length / 2)],
        frameP95: times[Math.floor(times.length * 0.95)],
        framesOver50ms: times.filter((value) => value > 50).length,
        frameCount: times.length,
        taskTimeDelta: metric(after, 'TaskDuration') - metric(before, 'TaskDuration'),
        elapsedDelta: metric(after, 'Timestamp') - metric(before, 'Timestamp'),
        heapMB: metric(after, 'JSHeapUsedSize') / 1024 / 1024,
        eventMax: Math.max(0, ...runtime.events.map((item) => item.duration)),
        totalLongTaskBlockingMs: runtime.totalLongTasks.reduce(
          (sum, item) => sum + Math.max(0, item.duration - 50),
          0,
        ),
      },
    }
    results.push(result)
    await writeFile(
      `${output}/results.json`,
      JSON.stringify({ measuredAt: new Date().toISOString(), bundles, results }, null, 2),
    )
    console.log(
      'RESULT',
      JSON.stringify({
        mode,
        surface,
        lcpMs: initial.lcp?.startTime,
        cls: initial.cls,
        initialBytes: initialRequests.reduce((sum, item) => sum + item.bytes, 0),
        finalBytes: result.finalRequests.reduce((sum, item) => sum + item.bytes, 0),
        initialRequests: initialRequests.length,
        dom: initial.dom,
        runtime: result.runtime,
        errors,
      }),
    )
    await context.close()
  }
}
await browser.close()
