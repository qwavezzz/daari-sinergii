import { chromium } from '@playwright/test'
import { createServer } from 'node:http'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve, extname, sep } from 'node:path'
import { gzipSync } from 'node:zlib'

// Repeatable laboratory comparison; not field Core Web Vitals or a real phone.
const root = resolve('var/pages-site')
const base = '/daari-sinergii/'
const output = process.env.PERF_OUTPUT || 'artifacts/optimize/after'
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
}
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname
  const file = resolve(
    root,
    '.' + pathname.slice(base.length - 1),
    ...(pathname.endsWith('/') ? ['index.html'] : []),
  )
  if (!pathname.startsWith(base) || !file.startsWith(root + sep)) return res.writeHead(404).end()
  try {
    let body = await readFile(file)
    const headers = { 'Content-Type': types[extname(file)] || 'application/octet-stream' }
    if (['.html', '.js', '.css', '.svg'].includes(extname(file))) {
      body = gzipSync(body)
      headers['Content-Encoding'] = 'gzip'
    }
    res.writeHead(200, headers).end(body)
  } catch {
    res.writeHead(404).end()
  }
})
await mkdir(output, { recursive: true })
await new Promise((done) => server.listen(4174, '127.0.0.1', done))
let browser
const results = []
try {
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE })
  for (const [surface, path] of [
    ['landing', ''],
    ['materials', 'materials/'],
    ['catalog', 'shop/'],
    ['product', 'shop/products/demo-olive-50/'],
  ]) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const cdp = await context.newCDPSession(page)
    await cdp.send('Network.enable')
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true })
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 })
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 150,
      downloadThroughput: 200000,
      uploadThroughput: 93750,
      connectionType: 'cellular4g',
    })
    await page.addInitScript(() => {
      window.perfSample = { lcp: 0, cls: 0, blockingMs: 0 }
      for (const type of ['largest-contentful-paint', 'layout-shift', 'longtask']) {
        new PerformanceObserver((list) =>
          list.getEntries().forEach((entry) => {
            if (type === 'largest-contentful-paint') window.perfSample.lcp = entry.startTime
            if (type === 'layout-shift' && !entry.hadRecentInput) window.perfSample.cls += entry.value
            if (type === 'longtask') window.perfSample.blockingMs += Math.max(0, entry.duration - 50)
          }),
        ).observe({ type, buffered: true })
      }
    })
    await page.goto('http://127.0.0.1:4174' + base + path, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(10000)
    const sample = await page.evaluate(() => ({
      ...window.perfSample,
      resources: performance.getEntriesByType('resource').map((r) => ({
        url: r.name,
        bytes: r.encodedBodySize,
        decoded: r.decodedBodySize,
        duration: r.duration,
      })),
      video: [...document.querySelectorAll('video')].map((v) => ({
        paused: v.paused,
        time: v.currentTime,
        source: v.currentSrc,
      })),
    }))
    await page.screenshot({ path: `${output}/${surface}.png` })
    results.push({ surface, ...sample, errors })
    console.log(JSON.stringify({ surface, ...windowlessSummary(sample), errors }))
    await context.close()
  }
  await writeFile(
    `${output}/results.json`,
    JSON.stringify(
      {
        conditions:
          'Chromium 390x844, CPU 4x, 1.6Mbps, 150ms latency, cold cache, local gzip server; one sample per route',
        results,
      },
      null,
      2,
    ),
  )
} finally {
  await browser?.close()
  server.closeAllConnections()
  await new Promise((done) => server.close(done))
}

function windowlessSummary(sample) {
  return {
    lcp: sample.lcp,
    cls: sample.cls,
    blockingMs: sample.blockingMs,
    jsBytes: sample.resources
      .filter((r) => new URL(r.url).pathname.endsWith('.js'))
      .reduce((n, r) => n + r.bytes, 0),
    video: sample.video,
  }
}
