import { defineConfig } from '@playwright/test'
import { shopOrigin } from './tests/browser/origins.js'

export default defineConfig({
  testDir: './tests/browser',
  ...(process.env.BROWSER_TEST_BANK === '1'
    ? { testMatch: '**/bank-payment.spec.js' }
    : process.env.BROWSER_TEST_DEMO_QUOTES === '1'
    ? { testMatch: '**/demo-delivery.spec.js' }
    : { testIgnore: ['**/demo-delivery.spec.js', '**/bank-payment.spec.js'] }),
  outputDir: './var/test-results',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: shopOrigin,
    viewport: { width: 1440, height: 900 },
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer:
    process.env.BROWSER_TEST_EXTERNAL_SERVER === '1'
      ? undefined
      : {
          command: `"${process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'}" tests/browser/server.py`,
          url: `${shopOrigin}/health/`,
          timeout: 120000,
          reuseExistingServer: false,
        },
})
