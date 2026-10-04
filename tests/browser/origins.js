export const browserPort = Number(process.env.BROWSER_TEST_PORT || 8001)
if (!Number.isInteger(browserPort) || browserPort < 1024 || browserPort > 65535) {
  throw new Error('Invalid BROWSER_TEST_PORT')
}
export const mainOrigin = `http://localhost:${browserPort}`
// Distinct cookie hosts, with a literal IPv4 shop address for Node HTTP clients.
// Windows DNS may resolve shop.localhost to an unusable IPv6-only address.
export const shopOrigin = `http://127.0.0.1:${browserPort}`
