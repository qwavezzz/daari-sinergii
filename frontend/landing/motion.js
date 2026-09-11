// Ported from src/motion.js (8fa57e8). Preserve scene geometry and timings.
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import Lenis from 'lenis'
import LenisSnap from 'lenis/snap'

gsap.registerPlugin(ScrollTrigger, SplitText)

const DESKTOP_QUERY = '(min-width: 992px)'
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function isMobileSafari26Phone() {
  return document.documentElement.classList.contains('is-iphone-safari-26')
}

function setupScroll(scopeRef, requestFrame, cleanups) {
  const desktop = window.matchMedia(DESKTOP_QUERY)
  const reducedMotion = window.matchMedia(REDUCED_MOTION_QUERY)
  let lenis = null
  let snap = null
  let tickerAttached = false
  let anchorSnapResumeTimer = 0
  let menuOpen = false

  const tick = (time) => {
    lenis?.raf(time * 1000)
  }

  const detachTicker = () => {
    if (!tickerAttached) return
    gsap.ticker.remove(tick)
    tickerAttached = false
  }

  const destroyLenis = () => {
    snap?.destroy()
    snap = null
    detachTicker()
    document.documentElement.classList.remove('has-smooth-scroll', 'has-section-snap')
    if (!lenis) return
    lenis.off('scroll', ScrollTrigger.update)
    lenis.destroy()
    lenis = null
  }

  const configureLenis = () => {
    destroyLenis()
    if (reducedMotion.matches || !desktop.matches) {
      requestFrame(() => ScrollTrigger.refresh())
      return
    }

    lenis = new Lenis({
      duration: 1,
      easing: (value) => Math.min(1, 1.001 - 2 ** (-10 * value)),
      smoothWheel: true,
      syncTouch: false,
      wheelMultiplier: 0.9,
    })
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    tickerAttached = true
    lenis.on('scroll', ScrollTrigger.update)
    snap = new LenisSnap(lenis, {
      type: 'lock',
      duration: 1.04,
      debounce: 40,
      distanceThreshold: '200%',
      easing: (value) => 1 - (1 - value) ** 4,
    })
    snap.addElements([...scopeRef.current.querySelectorAll('[data-scroll-snap]')], {
      align: 'start',
      ignoreSticky: true,
      ignoreTransform: true,
    })
    document.documentElement.classList.add('has-smooth-scroll')
    document.documentElement.classList.add('has-section-snap')
    requestFrame(() => snap?.resize())
    if (menuOpen) {
      snap.stop()
      lenis.stop()
    }
  }

  const header = scopeRef.current?.querySelector('.site-header')
  const activeLightSections = new Set()
  const syncHeaderContrast = () => {
    header?.classList.toggle('is-on-light', activeLightSections.size > 0)
  }
  const lightHeaderTriggers = isMobileSafari26Phone()
    ? []
    : gsap.utils.toArray('.evidence', scopeRef.current).map((section) =>
        ScrollTrigger.create({
          trigger: section,
          start: 'top 56px',
          end: 'bottom 56px',
          onToggle: (self) => {
            if (self.isActive) activeLightSections.add(section)
            else activeLightSections.delete(section)
            syncHeaderContrast()
          },
        }),
      )

  const handleAnchor = (event) => {
    const link = event.target.closest?.('a[href^="#"]')
    if (
      !link ||
      !lenis ||
      event.defaultPrevented ||
      event.button ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return
    if (!scopeRef.current.contains(link)) return
    const target = document.getElementById(link.hash.slice(1))
    if (!target) return
    event.preventDefault()

    window.clearTimeout(anchorSnapResumeTimer)
    snap?.stop()
    const resumeSnap = () => {
      window.clearTimeout(anchorSnapResumeTimer)
      if (!menuOpen) snap?.start()
    }
    anchorSnapResumeTimer = window.setTimeout(resumeSnap, 1400)

    lenis.scrollTo(target, {
      duration: 1.05,
      lock: true,
      force: true,
      userData: { initiator: 'anchor' },
      onComplete: () => {
        resumeSnap()
        if (link.classList.contains('skip-link')) target.focus({ preventScroll: true })
      },
    })
    window.history.replaceState(window.history.state, '', link.getAttribute('href'))
  }

  const handleMenu = (event) => {
    menuOpen = event.detail.open
    if (menuOpen) {
      snap?.stop()
      lenis?.stop()
    } else {
      lenis?.start()
      snap?.start()
    }
  }
  const resize = () => {
    lenis?.resize()
    snap?.resize()
  }
  const restoreScroll = (event) => {
    if (!lenis) return
    window.clearTimeout(anchorSnapResumeTimer)
    snap?.stop()
    ScrollTrigger.refresh()
    lenis.resize()
    lenis.scrollTo(event.detail.top, {
      immediate: true,
      force: true,
      userData: { initiator: 'history' },
    })
    ScrollTrigger.update()
    snap?.resize()
    event.detail.handled = true
    // Restore both native and Lenis targets before the section snap resumes.
    anchorSnapResumeTimer = window.setTimeout(() => {
      if (!menuOpen) snap?.start()
    }, 200)
  }

  // Register disposal before creating a ticker or listeners, including a failed init.
  cleanups.push(() => {
    window.clearTimeout(anchorSnapResumeTimer)
    lightHeaderTriggers.forEach((trigger) => trigger.kill())
    header?.classList.remove('is-on-light')
    destroyLenis()
    desktop.removeEventListener('change', configureLenis)
    reducedMotion.removeEventListener('change', configureLenis)
    document.removeEventListener('click', handleAnchor)
    scopeRef.current.removeEventListener('landing:menu-state', handleMenu)
    scopeRef.current.removeEventListener('landing:refresh', resize)
    scopeRef.current.removeEventListener('page:restore-scroll', restoreScroll)
  })
  configureLenis()
  desktop.addEventListener('change', configureLenis)
  reducedMotion.addEventListener('change', configureLenis)
  document.addEventListener('click', handleAnchor)
  scopeRef.current.addEventListener('landing:menu-state', handleMenu)
  scopeRef.current.addEventListener('landing:refresh', resize)
  scopeRef.current.addEventListener('page:restore-scroll', restoreScroll)
}

function setupAnimations(scopeRef, cleanups) {
  const motion = gsap.matchMedia()
  cleanups.push(() => motion.revert())

  const createTextEmergence = () => {
    if (isMobileSafari26Phone()) return undefined

    const splits = []
    const isDesktop = window.matchMedia(DESKTOP_QUERY).matches
    const scenes = gsap.utils.toArray('[data-text-emergence]', scopeRef.current)
    const textContext = gsap.context(() => {}, scopeRef.current)
    let stopped = false
    let preparationFrame = 0
    let preparationTask = 0

    const prepareScene = (scene) => {
      const title = scene.querySelector('[data-emergence-title]')
      if (!title) return

      const split = SplitText.create(title, {
        type: 'words,chars',
        mask: 'chars',
        wordsClass: 'emergence-word',
        charsClass: 'emergence-char',
        aria: 'auto',
      })
      const supportingCopy = scene.querySelectorAll('[data-emergence-copy]')
      let measuredViewport = `${window.innerWidth}:${window.innerHeight}`
      const timeline = gsap.timeline({
        scrollTrigger: {
          trigger: scene,
          start: isDesktop ? 'top 38%' : 'top 88%',
          end: 'top top',
          scrub: true,
          // Character transforms are constant. Image/font refreshes must not
          // invalidate hundreds of tweens and force their styles to be reread.
          onRefreshInit: (trigger) => {
            const viewport = `${window.innerWidth}:${window.innerHeight}`
            if (viewport !== measuredViewport) {
              measuredViewport = viewport
              trigger.animation?.invalidate()
            }
          },
        },
      })

      if (isDesktop) {
        timeline.fromTo(
          title,
          {
            y: () => Math.min(160, window.innerHeight * 0.18),
            scaleY: 0.78,
            filter: 'blur(6px)',
            transformOrigin: '50% 100%',
          },
          {
            y: 0,
            scaleY: 1,
            filter: 'blur(0px)',
            duration: 1,
            ease: 'power2.out',
            force3D: true,
          },
          0,
        )
      }

      timeline.fromTo(
        split.chars,
        { yPercent: isDesktop ? 146 : 118 },
        {
          yPercent: 0,
          duration: isDesktop ? 0.42 : 0.82,
          stagger: {
            amount: isDesktop ? 0.34 : 0.18,
            from: 'start',
            ease: 'power1.in',
          },
          ease: 'power4.out',
          force3D: true,
        },
        0,
      )

      if (supportingCopy.length) {
        timeline.fromTo(
          supportingCopy,
          {
            y: () => Math.min(isDesktop ? 124 : 78, window.innerHeight * (isDesktop ? 0.14 : 0.09)),
            clipPath: 'inset(100% 0 0 0)',
          },
          {
            y: 0,
            clipPath: 'inset(0% 0 0 0)',
            duration: 0.72,
            stagger: { amount: 0.08 },
            ease: isDesktop ? 'power2.out' : 'power3.out',
            force3D: true,
          },
          isDesktop ? 0.2 : 0.18,
        )
      }

      splits.push(split)
    }

    // Preserve every scene and its exact timing, but yield a paint/input turn
    // between sections. The nearest section is prepared first after a jump.
    const prepareNext = () => {
      if (stopped || !scopeRef.current.isConnected) return
      if (!scenes.length) {
        scopeRef.current.dispatchEvent(new CustomEvent('landing:motion-ready'))
        return
      }
      preparationFrame = requestAnimationFrame(() => {
        preparationTask = window.setTimeout(() => {
          if (stopped || !scopeRef.current.isConnected) return
          const distances = scenes.map((scene) => Math.abs(scene.getBoundingClientRect().top))
          const next = distances.indexOf(Math.min(...distances))
          const [scene] = scenes.splice(next, 1)
          try {
            textContext.add(() => prepareScene(scene))
          } catch (error) {
            // A failed deferred effect must leave the original text readable.
            stopped = true
            textContext.revert()
            splits.forEach((split) => split.revert())
            console.error('Не удалось подготовить анимацию текста:', error)
            return
          }
          prepareNext()
        }, 0)
      })
    }
    // Split using the actual font metrics; no second split/invalidating pass.
    if (document.fonts) document.fonts.ready.then(prepareNext)
    else prepareNext()

    return () => {
      stopped = true
      cancelAnimationFrame(preparationFrame)
      window.clearTimeout(preparationTask)
      textContext.revert()
      splits.forEach((split) => split.revert())
    }
  }

  motion.add('(prefers-reduced-motion: no-preference)', createTextEmergence)

  motion.add(
    {
      desktop: DESKTOP_QUERY,
      reduce: REDUCED_MOTION_QUERY,
    },
    (context) => {
      if (context.conditions.reduce) return undefined

      const quietSafari26 = isMobileSafari26Phone()
      if (quietSafari26) return undefined

      const hero = scopeRef.current?.querySelector('.hero')

      if (hero) {
        gsap
          .timeline({
            scrollTrigger: {
              trigger: hero,
              start: 'top top',
              end: 'bottom top',
              scrub: 0.45,
              invalidateOnRefresh: true,
            },
          })
          .to('.hero-video', { yPercent: -3.5, scale: 1.04, ease: 'none' }, 0)
          .to('.hero-content', { yPercent: -4, opacity: 0.76, ease: 'none' }, 0)
          .to('.hero-vignette', { opacity: 0.84, ease: 'none' }, 0)
      }

      const openingFlow = gsap.utils.toArray('.opening-flow span')
      if (openingFlow.length) {
        gsap.fromTo(
          openingFlow,
          { clipPath: 'inset(0 100% 0 0)' },
          {
            clipPath: 'inset(0 0% 0 0)',
            stagger: 0.08,
            ease: 'none',
            scrollTrigger: {
              trigger: '.opening-statement',
              start: 'top 62%',
              end: 'bottom 72%',
              scrub: 0.55,
            },
          },
        )
      }

      if (context.conditions.desktop) {
        gsap.utils.toArray('.transition-scene').forEach((scene) => {
          const currentLines = scene.querySelectorAll('.transition-current span')

          gsap.fromTo(
            currentLines,
            { scaleX: 0.12, opacity: 0.18 },
            {
              scaleX: 1,
              opacity: 0.82,
              stagger: 0.045,
              transformOrigin: '0 50%',
              ease: 'none',
              scrollTrigger: {
                trigger: scene,
                start: 'top 82%',
                end: 'top 12%',
                scrub: 0.42,
                invalidateOnRefresh: true,
              },
            },
          )
        })
      }

      gsap.from('.process-acts article', {
        y: 22,
        opacity: 0.56,
        duration: 0.72,
        stagger: 0.1,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.process',
          start: 'top 64%',
          toggleActions: 'play none none reverse',
        },
      })

      gsap.from('.brand-full', {
        y: 22,
        opacity: 0.22,
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.contact',
          start: 'top 62%',
          toggleActions: 'play none none reverse',
        },
      })

      gsap.from('.contact-actions', {
        scaleX: 0.35,
        transformOrigin: '0 50%',
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.contact-actions',
          start: 'top 88%',
          toggleActions: 'play none none reverse',
        },
      })

      return undefined
    },
  )
}

export function initPageMotion(scope) {
  const scopeRef = { current: scope }
  const cleanups = []
  const frames = new Set()
  let disposed = false
  const requestFrame = (callback) => {
    const id = requestAnimationFrame(() => {
      frames.delete(id)
      if (!disposed) callback()
    })
    frames.add(id)
    return id
  }
  const context = gsap.context(() => {}, scope)
  const destroy = () => {
    if (disposed) return
    disposed = true
    frames.forEach(cancelAnimationFrame)
    frames.clear()
    cleanups.reverse().forEach((cleanup) => cleanup?.())
    context.revert()
  }
  try {
    context.add(() => {
      setupScroll(scopeRef, requestFrame, cleanups)
      setupAnimations(scopeRef, cleanups)
    })
  } catch (error) {
    destroy()
    throw error
  }
  return destroy
}

export { gsap, ScrollTrigger }
