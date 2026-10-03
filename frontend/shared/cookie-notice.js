import './cookie-notice.css'

// Acknowledgement of essential storage only; never consent to tracking.
const storageKey = 'dari-cookie-notice-v1'
const lifetime = 180 * 24 * 60 * 60 * 1000
const notice = document.querySelector('[data-cookie-notice]')
if (notice) {
  const button = notice.querySelector('button')
  let acknowledgedAt = 0
  try {
    acknowledgedAt = Number(localStorage.getItem(storageKey))
  } catch {
    // Browsing and dismissal still work when storage is unavailable.
  }
  const now = Date.now()
  if (acknowledgedAt > 0 && acknowledgedAt <= now && now - acknowledgedAt < lifetime) {
    notice.hidden = true
  } else {
    const reserveSpace = () => {
      document.documentElement.style.setProperty('--cookie-notice-height', `${notice.offsetHeight}px`)
    }
    const observer = new ResizeObserver(reserveSpace)
    observer.observe(notice)
    reserveSpace()
    button.hidden = false
    button.addEventListener('click', () => {
      try {
        localStorage.setItem(storageKey, String(Date.now()))
      } catch {
        // Do not require persistent storage to dismiss an informational notice.
      }
      notice.hidden = true
      observer.disconnect()
      document.documentElement.style.removeProperty('--cookie-notice-height')
      const main = document.getElementById('main-content')
      if (main) {
        if (!main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1')
        main.focus({ preventScroll: true })
      }
    })
  }
}
