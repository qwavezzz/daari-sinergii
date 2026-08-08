const MOBILE_QUERY = '(max-width: 991px)'
const MAX_BROWSER_CHROME_RATIO = 0.28

function isComparableWidth(candidate, viewportWidth) {
  if (!candidate || !viewportWidth) return false
  return Math.abs(candidate - viewportWidth) <= Math.max(4, viewportWidth * 0.08)
}

function readMobileViewport() {
  const visualViewport = window.visualViewport
  const viewportWidth = visualViewport?.width || window.innerWidth
  const visibleHeight = visualViewport?.scale === 1
    ? visualViewport.height
    : window.innerHeight
  const heightCandidates = [window.innerHeight, visibleHeight]

  if (isComparableWidth(window.outerWidth, viewportWidth)) {
    heightCandidates.push(window.outerHeight)
  }

  if (isComparableWidth(window.screen?.width, viewportWidth)) {
    heightCandidates.push(window.screen.height, window.screen.availHeight)
  }

  const screenHeight = Math.ceil(
    Math.max(...heightCandidates.filter((value) => Number.isFinite(value) && value > 0)),
  )
  const browserChrome = Math.ceil(
    Math.min(
      Math.max(0, screenHeight - visibleHeight),
      screenHeight * MAX_BROWSER_CHROME_RATIO,
    ),
  )

  return { screenHeight, browserChrome }
}

export function syncMobileViewport() {
  if (typeof window === 'undefined') return

  const root = document.documentElement
  if (!window.matchMedia(MOBILE_QUERY).matches) {
    root.classList.remove('has-measured-mobile-viewport')
    root.style.removeProperty('--mobile-scene-height')
    root.style.removeProperty('--mobile-browser-chrome')
    return
  }

  const { screenHeight, browserChrome } = readMobileViewport()
  root.style.setProperty('--mobile-scene-height', `${screenHeight}px`)
  root.style.setProperty('--mobile-browser-chrome', `${browserChrome}px`)
  root.classList.add('has-measured-mobile-viewport')
}

export function installMobileViewport() {
  if (typeof window === 'undefined') return () => {}

  const mobile = window.matchMedia(MOBILE_QUERY)
  const visualViewport = window.visualViewport
  let frame = 0
  let orientationTimer = 0

  const scheduleSync = () => {
    window.cancelAnimationFrame(frame)
    frame = window.requestAnimationFrame(syncMobileViewport)
  }

  const handleOrientation = () => {
    scheduleSync()
    window.clearTimeout(orientationTimer)
    orientationTimer = window.setTimeout(scheduleSync, 280)
  }

  syncMobileViewport()
  mobile.addEventListener('change', scheduleSync)
  window.addEventListener('resize', scheduleSync)
  window.addEventListener('orientationchange', handleOrientation)
  visualViewport?.addEventListener('resize', scheduleSync)

  return () => {
    window.cancelAnimationFrame(frame)
    window.clearTimeout(orientationTimer)
    mobile.removeEventListener('change', scheduleSync)
    window.removeEventListener('resize', scheduleSync)
    window.removeEventListener('orientationchange', handleOrientation)
    visualViewport?.removeEventListener('resize', scheduleSync)
  }
}
