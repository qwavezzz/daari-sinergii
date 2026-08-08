import test from 'node:test'
import assert from 'node:assert/strict'

import {
  isIOSDevice,
  isIPhoneDevice,
  readIOSMajorVersion,
  readMobileSafariMajorVersion,
} from './platform.js'

const navigatorFor = (userAgent, overrides = {}) => ({
  userAgent,
  platform: '',
  maxTouchPoints: 0,
  ...overrides,
})

const safari26IPhone = navigatorFor(
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1',
  { platform: 'iPhone', maxTouchPoints: 5 },
)

test('detects Safari 26 from the browser version despite the frozen iOS token', () => {
  assert.equal(readIOSMajorVersion(safari26IPhone), 18)
  assert.equal(readMobileSafariMajorVersion(safari26IPhone), 26)
  assert.equal(isIPhoneDevice(safari26IPhone), true)
})

test('keeps earlier Mobile Safari versions outside the Safari 26 mode', () => {
  const safari18IPhone = navigatorFor(
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1',
    { platform: 'iPhone', maxTouchPoints: 5 },
  )

  assert.equal(readMobileSafariMajorVersion(safari18IPhone), 18)
})

test('does not apply Safari-specific behavior to alternate iOS browsers', () => {
  const chromeIOS = navigatorFor(
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.7339.122 Mobile/15E148 Safari/604.1',
    { platform: 'iPhone', maxTouchPoints: 5 },
  )

  assert.equal(isIOSDevice(chromeIOS), true)
  assert.equal(readMobileSafariMajorVersion(chromeIOS), null)
})

test('does not identify Android or desktop Safari as Mobile Safari', () => {
  const androidChrome = navigatorFor(
    'Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36',
    { platform: 'Linux armv8l', maxTouchPoints: 5 },
  )
  const desktopSafari = navigatorFor(
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15',
    { platform: 'MacIntel' },
  )

  assert.equal(readMobileSafariMajorVersion(androidChrome), null)
  assert.equal(readMobileSafariMajorVersion(desktopSafari), null)
})
