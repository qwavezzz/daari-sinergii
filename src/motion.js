import { useEffect } from 'react'
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'
import Lenis from 'lenis'
import LenisSnap from 'lenis/snap'

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

const DESKTOP_QUERY = '(min-width: 992px)'
const PHONE_QUERY = '(max-width: 767px)'
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function isIOS26Phone() {
  return document.documentElement.classList.contains('is-ios-26') && window.matchMedia(PHONE_QUERY).matches
}

export function usePageMotion(scopeRef) {
  useEffect(() => {
    const desktop = window.matchMedia(DESKTOP_QUERY)
    const reducedMotion = window.matchMedia(REDUCED_MOTION_QUERY)
    let lenis = null
    let snap = null
    let anchorSnapResumeTimer = 0

    const tick = (time) => {
      lenis?.raf(time * 1000)
    }

    const destroyLenis = () => {
      snap?.destroy()
      snap = null
      if (!lenis) return
      lenis.off('scroll', ScrollTrigger.update)
      lenis.destroy()
      lenis = null
      document.documentElement.classList.remove('has-smooth-scroll', 'has-section-snap')
    }

    const configureLenis = () => {
      destroyLenis()
      if (reducedMotion.matches || !desktop.matches) {
        requestAnimationFrame(() => ScrollTrigger.refresh())
        return
      }

      lenis = new Lenis({
        duration: 1,
        easing: (value) => Math.min(1, 1.001 - 2 ** (-10 * value)),
        smoothWheel: true,
        syncTouch: false,
        wheelMultiplier: 0.9,
      })
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
      ScrollTrigger.refresh()
      requestAnimationFrame(() => snap?.resize())
    }

    const header = scopeRef.current?.querySelector('.site-header')
    const activeLightSections = new Set()
    const syncHeaderContrast = () => {
      header?.classList.toggle('is-on-light', activeLightSections.size > 0)
    }
    const lightHeaderTriggers = isIOS26Phone()
      ? []
      : gsap.utils
          .toArray('.evidence', scopeRef.current)
          .map((section) =>
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
      const link = event.target.closest('a[href^="#"]')
      if (!link || !lenis) return
      const target = document.querySelector(link.getAttribute('href'))
      if (!target) return
      event.preventDefault()

      window.clearTimeout(anchorSnapResumeTimer)
      snap?.stop()
      const resumeSnap = () => {
        window.clearTimeout(anchorSnapResumeTimer)
        snap?.start()
      }
      anchorSnapResumeTimer = window.setTimeout(resumeSnap, 1400)

      lenis.scrollTo(target, {
        duration: 1.05,
        lock: true,
        force: true,
        userData: { initiator: 'anchor' },
        onComplete: resumeSnap,
      })
      window.history.replaceState(null, '', link.getAttribute('href'))
    }

    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    configureLenis()
    desktop.addEventListener('change', configureLenis)
    reducedMotion.addEventListener('change', configureLenis)
    document.addEventListener('click', handleAnchor)

    return () => {
      window.clearTimeout(anchorSnapResumeTimer)
      lightHeaderTriggers.forEach((trigger) => trigger.kill())
      header?.classList.remove('is-on-light')
      destroyLenis()
      gsap.ticker.remove(tick)
      desktop.removeEventListener('change', configureLenis)
      reducedMotion.removeEventListener('change', configureLenis)
      document.removeEventListener('click', handleAnchor)
    }
  }, [])

  useGSAP(
    () => {
      const motion = gsap.matchMedia()

      const createTextEmergence = () => {
        if (isIOS26Phone()) return undefined

        const splits = []
        const isDesktop = window.matchMedia(DESKTOP_QUERY).matches

        gsap.utils.toArray('[data-text-emergence]', scopeRef.current).forEach((scene) => {
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
          const timeline = gsap.timeline({
              scrollTrigger: {
                trigger: scene,
                start: isDesktop ? 'top 38%' : 'top 88%',
                end: 'top top',
              scrub: true,
              invalidateOnRefresh: true,
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
        })

        return () => splits.forEach((split) => split.revert())
      }

      motion.add('(prefers-reduced-motion: no-preference)', createTextEmergence)

      motion.add(
        {
          desktop: DESKTOP_QUERY,
          reduce: REDUCED_MOTION_QUERY,
        },
        (context) => {
          if (context.conditions.reduce) return undefined

          const quietIOS26 = isIOS26Phone()
          const hero = scopeRef.current?.querySelector('.hero')

          if (hero && !quietIOS26) {
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
          if (openingFlow.length && !quietIOS26) {
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
              toggleActions: quietIOS26 ? 'play none none none' : 'play none none reverse',
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
              toggleActions: quietIOS26 ? 'play none none none' : 'play none none reverse',
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
              toggleActions: quietIOS26 ? 'play none none none' : 'play none none reverse',
            },
          })

          return undefined
        },
      )

      return () => motion.revert()
    },
    { scope: scopeRef },
  )
}

export { gsap, ScrollTrigger, useGSAP }
