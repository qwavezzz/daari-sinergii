import { useEffect } from 'react'
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const DESKTOP_QUERY = '(min-width: 992px)'
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function prepareStroke(path) {
  const length = path.getTotalLength?.()
  if (!length) return null
  gsap.set(path, {
    strokeDasharray: length,
    strokeDashoffset: length,
  })
  return length
}

export function usePageMotion(scopeRef, heroProgressRef) {
  useEffect(() => {
    const desktop = window.matchMedia(DESKTOP_QUERY)
    const reducedMotion = window.matchMedia(REDUCED_MOTION_QUERY)
    let lenis = null

    const tick = (time) => {
      lenis?.raf(time * 1000)
    }

    const destroyLenis = () => {
      if (!lenis) return
      lenis.off('scroll', ScrollTrigger.update)
      lenis.destroy()
      lenis = null
      document.documentElement.classList.remove('has-smooth-scroll')
    }

    const configureLenis = () => {
      destroyLenis()
      if (!desktop.matches || reducedMotion.matches) return

      lenis = new Lenis({
        duration: 1,
        easing: (value) => Math.min(1, 1.001 - 2 ** (-10 * value)),
        smoothWheel: true,
        syncTouch: false,
        wheelMultiplier: 0.9,
      })
      lenis.on('scroll', ScrollTrigger.update)
      document.documentElement.classList.add('has-smooth-scroll')
      ScrollTrigger.refresh()
    }

    const handleAnchor = (event) => {
      const link = event.target.closest('a[href^="#"]')
      if (!link || !lenis) return
      const target = document.querySelector(link.getAttribute('href'))
      if (!target) return
      event.preventDefault()
      lenis.scrollTo(target, { duration: 1.05 })
      window.history.replaceState(null, '', link.getAttribute('href'))
    }

    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)
    configureLenis()
    desktop.addEventListener('change', configureLenis)
    reducedMotion.addEventListener('change', configureLenis)
    document.addEventListener('click', handleAnchor)

    return () => {
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

      motion.add(
        {
          desktop: DESKTOP_QUERY,
          reduce: REDUCED_MOTION_QUERY,
        },
        (context) => {
          if (context.conditions.reduce) return undefined

          const hero = scopeRef.current?.querySelector('.hero')
          const header = scopeRef.current?.querySelector('.site-header')
          const evidence = scopeRef.current?.querySelector('.evidence')
          const contact = scopeRef.current?.querySelector('.contact')

          if (hero) {
            gsap
              .timeline({
                scrollTrigger: {
                  trigger: hero,
                  start: 'top top',
                  end: 'bottom top',
                  scrub: 0.45,
                  invalidateOnRefresh: true,
                  onUpdate: (self) => {
                    heroProgressRef.current = self.progress
                  },
                },
              })
              .to('.ozone-canvas', { yPercent: -4.5, scale: 1.035, ease: 'none' }, 0)
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

          scopeRef.current?.querySelectorAll('.system-line').forEach((path) => {
            const length = prepareStroke(path)
            if (!length) return
            gsap.to(path, {
              strokeDashoffset: 0,
              duration: 1.25,
              ease: 'power3.out',
              scrollTrigger: {
                trigger: '.product-system',
                start: 'top 68%',
                toggleActions: 'play none none reverse',
              },
            })
          })

          gsap.from('.system-bubble', {
            x: -18,
            opacity: 0.08,
            duration: 1.1,
            stagger: { each: 0.018, from: 'random' },
            ease: 'power3.out',
            scrollTrigger: {
              trigger: '.product-system',
              start: 'top 62%',
              toggleActions: 'play none none reverse',
            },
          })

          gsap.fromTo(
            '.oil-fill',
            { scaleY: 0 },
            {
              scaleY: 1,
              duration: 1.35,
              ease: 'power3.out',
              transformOrigin: '50% 100%',
              scrollTrigger: {
                trigger: '.product-oil',
                start: 'top 68%',
                toggleActions: 'play none none reverse',
              },
            },
          )

          scopeRef.current?.querySelectorAll('.steam-path, .condenser').forEach((path) => {
            const length = prepareStroke(path)
            if (!length) return
            gsap.to(path, {
              strokeDashoffset: 0,
              duration: 1.4,
              ease: 'power2.out',
              scrollTrigger: {
                trigger: '.product-hydrolat',
                start: 'top 68%',
                toggleActions: 'play none none reverse',
              },
            })
          })

          const processPaths = scopeRef.current?.querySelectorAll('.process-path') ?? []
          processPaths.forEach((path) => {
            const length = prepareStroke(path)
            if (!length) return
            gsap.to(path, {
              strokeDashoffset: 0,
              ease: 'none',
              scrollTrigger: {
                trigger: '.process-diagram',
                start: 'top 78%',
                end: 'bottom 42%',
                scrub: 0.5,
              },
            })
          })

          gsap.from('.process-acts article', {
            y: 22,
            opacity: 0.42,
            duration: 0.72,
            stagger: 0.1,
            ease: 'power3.out',
            scrollTrigger: {
              trigger: '.process-acts',
              start: 'top 78%',
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

          if (header && evidence) {
            ScrollTrigger.create({
              trigger: evidence,
              start: 'top 56px',
              end: 'bottom 56px',
              onEnter: () => header.classList.add('is-on-light'),
              onEnterBack: () => header.classList.add('is-on-light'),
              onLeave: () => header.classList.remove('is-on-light'),
              onLeaveBack: () => header.classList.remove('is-on-light'),
            })
          }

          if (header && contact) {
            ScrollTrigger.create({
              trigger: contact,
              start: 'top 74px',
              onEnter: () => header.classList.add('is-concealed'),
              onLeaveBack: () => header.classList.remove('is-concealed'),
            })
          }

          return () => {
            heroProgressRef.current = 0
            header?.classList.remove('is-on-light')
            header?.classList.remove('is-concealed')
          }
        },
      )

      return () => motion.revert()
    },
    { scope: scopeRef },
  )
}

export { gsap, ScrollTrigger, useGSAP }
