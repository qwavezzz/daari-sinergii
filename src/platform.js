function readIOSMajorVersion(navigatorObject) {
  const userAgent = navigatorObject.userAgent || ''
  const platform = navigatorObject.platform || ''
  const isTouchMac = platform === 'MacIntel' && navigatorObject.maxTouchPoints > 1
  const isIOSDevice = /iPhone|iPad|iPod/i.test(userAgent) || /iPhone|iPad|iPod/i.test(platform) || isTouchMac

  if (!isIOSDevice) return null

  const nativeVersion = userAgent.match(/(?:CPU(?: iPhone)? OS|iPhone OS) (\d+)(?:[._]\d+)?/i)
  if (nativeVersion) return Number(nativeVersion[1])

  const desktopIPadVersion = isTouchMac && userAgent.match(/Version\/(\d+)(?:\.\d+)?/i)
  return desktopIPadVersion ? Number(desktopIPadVersion[1]) : null
}

export function applyRuntimePlatformClass() {
  if (typeof window === 'undefined') return

  const iosMajorVersion = readIOSMajorVersion(window.navigator)
  document.documentElement.classList.toggle('is-ios-26', iosMajorVersion === 26)
}

export { readIOSMajorVersion }
