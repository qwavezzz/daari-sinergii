/** Playback policy and poster fallback from the existing HeroVideo component. */
export function initHeroVideo(root) {
  const video = root.querySelector('.hero-video')
  if (!video) return () => {}
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  let isVisible = false
  let disposed = false
  let sourceAttached = false
  let playPending = false
  let autoplayBlocked = false
  const connection = navigator.connection
  // The muted property must be set as well as the HTML attribute on Safari.
  video.muted = true
  video.defaultMuted = true
  video.playsInline = true
  video.controls = false
  video.setAttribute('webkit-playsinline', '')
  video.setAttribute('controlslist', 'nofullscreen noremoteplayback nodownload')

  const syncPlayback = () => {
    const shouldPlay =
      !disposed && isVisible && !document.hidden && !reduceMotion.matches && !connection?.saveData
    if (!shouldPlay) {
      video.pause()
      return
    }
    if (!sourceAttached) {
      video.querySelectorAll('source[data-src]').forEach((source) => {
        source.src = source.dataset.src
      })
      sourceAttached = true
      video.load()
    }
    if (playPending || !video.paused || autoplayBlocked) return
    playPending = true
    const attempt = video.play()
    attempt
      ?.then(() => {
        if (disposed || !isVisible || document.hidden || reduceMotion.matches || connection?.saveData)
          video.pause()
      })
      .catch((error) => {
        autoplayBlocked = error.name === 'NotAllowedError'
      })
      .finally(() => {
        playPending = false
      })
    if (!attempt) playPending = false
  }
  const observer = new IntersectionObserver(
    ([entry]) => {
      isVisible = entry.isIntersecting
      syncPlayback()
    },
    { threshold: 0.05 },
  )

  // Retry a blocked autoplay inside a real gesture, without consuming navigation.
  const retryPlayback = () => {
    if (!autoplayBlocked) return
    autoplayBlocked = false
    syncPlayback()
  }
  root.addEventListener('pointerup', retryPlayback, true)
  root.addEventListener('keydown', retryPlayback, true)
  observer.observe(video)
  document.addEventListener('visibilitychange', syncPlayback)
  reduceMotion.addEventListener('change', syncPlayback)
  connection?.addEventListener('change', syncPlayback)
  video.addEventListener('canplay', syncPlayback)
  syncPlayback()

  return () => {
    disposed = true
    observer.disconnect()
    root.removeEventListener('pointerup', retryPlayback, true)
    root.removeEventListener('keydown', retryPlayback, true)
    document.removeEventListener('visibilitychange', syncPlayback)
    reduceMotion.removeEventListener('change', syncPlayback)
    connection?.removeEventListener('change', syncPlayback)
    video.removeEventListener('canplay', syncPlayback)
    video.pause()
  }
}
