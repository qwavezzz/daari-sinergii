/** Playback policy and poster fallback from the existing HeroVideo component. */
export function initHeroVideo(root) {
  const video = root.querySelector('.hero-video')
  if (!video) return () => {}
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  let isVisible = false
  let disposed = false
  let sourceAttached = false
  const connection = navigator.connection
  // The muted property must be set as well as the HTML attribute on Safari.
  video.muted = true

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
    const attempt = video.play()
    attempt
      ?.then(() => {
        if (disposed) video.pause()
      })
      .catch(() => {
        // Keep the native poster and the matching CSS background when autoplay fails.
      })
  }
  const observer = new IntersectionObserver(
    ([entry]) => {
      isVisible = entry.isIntersecting
      syncPlayback()
    },
    { threshold: 0.05 },
  )

  observer.observe(video)
  document.addEventListener('visibilitychange', syncPlayback)
  reduceMotion.addEventListener('change', syncPlayback)
  connection?.addEventListener('change', syncPlayback)
  video.addEventListener('canplay', syncPlayback)
  syncPlayback()

  return () => {
    disposed = true
    observer.disconnect()
    document.removeEventListener('visibilitychange', syncPlayback)
    reduceMotion.removeEventListener('change', syncPlayback)
    connection?.removeEventListener('change', syncPlayback)
    video.removeEventListener('canplay', syncPlayback)
    video.pause()
  }
}
