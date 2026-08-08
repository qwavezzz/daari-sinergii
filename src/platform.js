function isIOSDevice(navigatorObject) {
  const userAgent = navigatorObject.userAgent || ''
  const platform = navigatorObject.platform || ''
  const isTouchMac = platform === 'MacIntel' && navigatorObject.maxTouchPoints > 1

  return /iPhone|iPad|iPod/i.test(userAgent) || /iPhone|iPad|iPod/i.test(platform) || isTouchMac
}

function isIPhoneDevice(navigatorObject) {
  const userAgent = navigatorObject.userAgent || ''
  const platform = navigatorObject.platform || ''

  return /iPhone|iPod/i.test(userAgent) || /iPhone|iPod/i.test(platform)
}

function readMobileSafariMajorVersion(navigatorObject) {
  const userAgent = navigatorObject.userAgent || ''
  if (!isIOSDevice(navigatorObject)) return null

  const isAlternateIOSBrowser = /CriOS|FxiOS|EdgiOS|OPiOS|DuckDuckGo/i.test(userAgent)
  const isSafari = /Version\/\d+(?:\.\d+)?/i.test(userAgent) && /Safari\//i.test(userAgent)

  if (isAlternateIOSBrowser || !isSafari) return null

  const safariVersion = userAgent.match(/Version\/(\d+)(?:\.\d+)?/i)
  return safariVersion ? Number(safariVersion[1]) : null
}

function readIOSMajorVersion(navigatorObject) {
  const userAgent = navigatorObject.userAgent || ''
  const platform = navigatorObject.platform || ''
  const isTouchMac = platform === 'MacIntel' && navigatorObject.maxTouchPoints > 1

  if (!isIOSDevice(navigatorObject)) return null

  const nativeVersion = userAgent.match(/(?:CPU(?: iPhone)? OS|iPhone OS) (\d+)(?:[._]\d+)?/i)
  if (nativeVersion) return Number(nativeVersion[1])

  const desktopIPadVersion = isTouchMac && userAgent.match(/Version\/(\d+)(?:\.\d+)?/i)
  return desktopIPadVersion ? Number(desktopIPadVersion[1]) : null
}

export function applyRuntimePlatformClass() {
  if (typeof window === 'undefined') return

  const mobileSafariMajorVersion = readMobileSafariMajorVersion(window.navigator)
  const root = document.documentElement

  root.classList.remove('is-ios-26', 'is-mobile-safari-26')
  root.classList.toggle(
    'is-iphone-safari-26',
    isIPhoneDevice(window.navigator) && mobileSafariMajorVersion === 26,
  )
}

export { isIOSDevice, isIPhoneDevice, readIOSMajorVersion, readMobileSafariMajorVersion }
