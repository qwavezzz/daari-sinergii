import { applyRuntimePlatformClass } from '../src/platform.js'
import { initPageMotion, ScrollTrigger } from './landing/motion.js'
import { initContextsStory } from './landing/contexts.js'
import { initHeroVideo } from './landing/hero.js'
import './landing/fallbacks.css'

export { registerLandingUI } from './landing/menu.js'

const instances = new WeakMap()

function findLanding(root) {
  return root?.matches?.('[data-page="landing"]') ? root : root?.querySelector?.('[data-page="landing"]')
}

/** Idempotent page lifecycle; the host calls this after a full page/history swap. */
export function initLanding(root = document) {
  const scope = findLanding(root)
  if (!scope || instances.has(scope)) return instances.get(scope)?.destroy
  applyRuntimePlatformClass()
  const disposers = []
  const controller = new AbortController()
  let frame = 0
  let refreshTimer = 0
  let disposed = false

  const refresh = () => {
    window.clearTimeout(refreshTimer)
    cancelAnimationFrame(frame)
    refreshTimer = window.setTimeout(() => {
      frame = requestAnimationFrame(() => {
        if (disposed || !scope.isConnected) return
        ScrollTrigger.refresh()
        scope.dispatchEvent(new CustomEvent('landing:refresh'))
      })
    }, 80)
  }
  const destroy = () => {
    if (disposed) return
    disposed = true
    controller.abort()
    window.clearTimeout(refreshTimer)
    cancelAnimationFrame(frame)
    disposers.reverse().forEach((dispose) => dispose())
    instances.delete(scope)
  }
  instances.set(scope, { destroy, refresh })

  try {
    disposers.push(initHeroVideo(scope))
    disposers.push(initContextsStory(scope))
    disposers.push(initPageMotion(scope))

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.16 },
    )
    scope.querySelectorAll('[data-reveal]').forEach((node) => observer.observe(node))
    disposers.push(() => observer.disconnect())

    // Images reserve their dimensions in HTML/CSS. Their bytes arriving do not
    // change scene geometry and must not restart every character animation.
    document.fonts?.ready.then(() => {
      if (!disposed) refresh()
    })
    scope.addEventListener('content:changed', refresh, { signal: controller.signal })
    scope.addEventListener('landing:motion-ready', refresh, { signal: controller.signal })
    refresh()
  } catch (error) {
    // Revert SplitText, pins and hidden styles so the server HTML remains readable.
    destroy()
    console.error('Не удалось запустить анимацию страницы:', error)
  }
  return destroy
}

export function destroyLanding(root = document) {
  const scope = findLanding(root)
  if (scope) instances.get(scope)?.destroy()
}

export function refreshLanding(root = document) {
  const scope = findLanding(root)
  if (scope) instances.get(scope)?.refresh()
}
