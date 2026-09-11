import { gsap } from './motion.js'

/** Original ContextsStory scene, scoped to one replaceable server-rendered page. */
export function initContextsStory(root) {
  const section = root.querySelector('.contexts')
  if (!section) return () => {}
  const track = section.querySelector('.contexts-track')
  const stage = section.querySelector('.contexts-stage')
  const panels = [...section.querySelectorAll('.context-panel')]
  const markers = [...section.querySelectorAll('.context-snap-marker')]
  markers.forEach((marker, index) => {
    marker.style.top = `${(index / Math.max(markers.length - 1, 1)) * 100}%`
  })

  const context = gsap.context(() => {}, section)
  const media = gsap.matchMedia(section)
  let disposed = false
  const destroy = () => {
    if (disposed) return
    disposed = true
    media.revert()
    context.revert()
    section.classList.remove('is-stacked')
    track.style.removeProperty('height')
    markers.forEach((marker) => marker.style.removeProperty('top'))
  }

  try {
    context.add(() => {
      media.add('(min-width: 992px) and (prefers-reduced-motion: no-preference)', () => {
        if (panels.length < 2) return undefined
        section.classList.add('is-stacked')
        // Five original panels occupy 420svh; publication changes keep the same pace.
        track.style.height = `${(panels.length - 1) * 105}svh`
        panels.slice(1).forEach((panel) => gsap.set(panel, { yPercent: 100 }))

        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: track,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.14,
            pin: stage,
            pinSpacing: false,
            anticipatePin: 1,
            invalidateOnRefresh: true,
          },
        })

        panels.slice(1).forEach((panel, index) => {
          timeline.to(panel, { yPercent: 0, duration: 0.58, ease: 'power2.inOut' }, index)
          timeline.to({}, { duration: 0.1 }, index + 0.9)
        })
        return () => {
          timeline.kill()
          section.classList.remove('is-stacked')
          track.style.removeProperty('height')
        }
      })
    })
  } catch (error) {
    destroy()
    throw error
  }
  return destroy
}
