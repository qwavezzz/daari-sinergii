import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: 'http://shop.localhost:8001',
    viewport: { width: 1440, height: 900 },
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'}" scripts/browser_server.py`,
    url: 'http://localhost:8001/health/',
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
  },
})
