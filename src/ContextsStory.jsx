import { useRef } from 'react'
import { assetPath } from './assetPath.js'
import ConceptPhoto from './ConceptPhoto.jsx'
import { gsap, useGSAP } from './motion.js'

function ContextPanel({ context, index, total }) {
  return (
    <article className={`context-panel context-panel-${context.id}`}>
      <div className="context-panel-meta">
        <span>{String(index + 1).padStart(2, '0')}</span>
        <span aria-hidden="true">/</span>
        <span>{String(total).padStart(2, '0')}</span>
      </div>
      <div className="context-panel-title">
        <h3>{context.title}</h3>
      </div>
      <ConceptPhoto
        className="context-panel-visual context-panel-photo"
        src={assetPath(`assets/photos/optimized/context-${context.id}-bg-1536.webp`)}
        srcSet={`${assetPath(`assets/photos/optimized/context-${context.id}-bg-768.webp`)} 768w, ${assetPath(`assets/photos/optimized/context-${context.id}-bg-1536.webp`)} 1536w`}
        sizes="100vw"
        mobileSrcSet={`${assetPath(`assets/photos/optimized/context-${context.id}-bg-mobile-720.webp`)} 720w`}
        width="1536"
        height="864"
      />
      <div className="context-panel-copy">
        <p className="context-panel-caption">{context.caption}</p>
        <a className="context-panel-action" href="#contact">
          <span>Получить консультацию</span>
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <path d="M3 9h11M10 4l5 5-5 5" />
          </svg>
        </a>
      </div>
    </article>
  )
}

export default function ContextsStory({ contexts }) {
  const sectionRef = useRef(null)
  const trackRef = useRef(null)
  const stageRef = useRef(null)

  useGSAP(
    () => {
      const media = gsap.matchMedia()

      const createStackedStory = () => {
        const panels = gsap.utils.toArray('.context-panel')
        if (!panels.length) return undefined

        panels.slice(1).forEach((panel) => gsap.set(panel, { yPercent: 100 }))

        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: trackRef.current,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.14,
            pin: stageRef.current,
            pinSpacing: false,
            anticipatePin: 1,
            invalidateOnRefresh: true,
          },
        })

        panels.slice(1).forEach((panel, index) => {
          const segmentStart = index

          timeline.to(panel, { yPercent: 0, duration: 0.58, ease: 'power2.inOut' }, segmentStart)
          timeline.to({}, { duration: 0.1 }, segmentStart + 0.9)
        })

        return () => timeline.kill()
      }

      const createMobileStory = () => {
        const intro = stageRef.current?.querySelector('.contexts-story-intro')
        const label = stageRef.current?.querySelector('.contexts-stage-label')
        const panels = gsap.utils.toArray('.context-panel')
        if (!intro || !label || !panels.length) return undefined

        const states = [intro, ...panels]
        let activeState = -1

        const setActiveState = (nextState) => {
          if (nextState === activeState) return
          activeState = nextState
          states.forEach((state, index) => {
            const isActive = index === activeState
            state.inert = !isActive
            state.setAttribute('aria-hidden', String(!isActive))
          })
        }

        setActiveState(0)
        gsap.set(intro, { autoAlpha: 1, yPercent: 0 })
        gsap.set(label, { autoAlpha: 0 })
        gsap.set(panels, { autoAlpha: 1, yPercent: 100 })

        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: trackRef.current,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.18,
            invalidateOnRefresh: true,
            onUpdate: (self) => {
              setActiveState(Math.round(self.progress * (states.length - 1)))
            },
          },
        })

        timeline
          .to({}, { duration: 0.65 })
          .to(intro, { autoAlpha: 0, yPercent: -8, duration: 0.35, ease: 'power2.inOut' })
          .to(panels[0], { yPercent: 0, duration: 0.48, ease: 'power2.inOut' }, '<')
          .to(label, { autoAlpha: 1, duration: 0.2, ease: 'power2.out' }, '<0.15')
          .to({}, { duration: 0.72 })

        panels.slice(1).forEach((panel) => {
          timeline
            .to(panel, { yPercent: 0, duration: 0.48, ease: 'power2.inOut' })
            .to({}, { duration: 0.72 })
        })

        return () => {
          timeline.kill()
          states.forEach((state) => {
            state.inert = false
            state.removeAttribute('aria-hidden')
          })
        }
      }

      media.add('(min-width: 992px) and (prefers-reduced-motion: no-preference)', createStackedStory)
      media.add('(max-width: 767px) and (prefers-reduced-motion: no-preference)', createMobileStory)
      return () => media.revert()
    },
    { scope: sectionRef },
  )

  return (
    <section className="contexts" id="contexts" aria-label="Области применения" ref={sectionRef}>
      <div className="contexts-intro contexts-intro-desktop section-pad transition-scene" data-scroll-snap data-text-emergence>
        <div className="contexts-head">
          <h2 id="contexts-title" data-transition-content data-emergence-title>
            Одна технология. Разные контексты.
          </h2>
          <p data-emergence-copy>
            Сначала определяем задачу и параметры воды, затем подбираем контур, режим работы и
            место системы в существующей инфраструктуре.
          </p>
        </div>
        <div className="transition-current" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="contexts-track" ref={trackRef}>
        <div className="context-snap-range" aria-hidden="true">
          {contexts.map((context, index) => (
            <span
              className="context-snap-marker"
              data-scroll-snap
              key={context.id}
              style={{ top: `${(index / Math.max(contexts.length - 1, 1)) * 100}%` }}
            />
          ))}
        </div>
        <div className="contexts-stage" ref={stageRef}>
          <div className="contexts-story-intro section-pad">
            <div className="contexts-head">
              <h2 id="contexts-title-mobile">Одна технология. Разные контексты.</h2>
              <p>
                Сначала определяем задачу и параметры воды, затем подбираем контур, режим работы и
                место системы в существующей инфраструктуре.
              </p>
            </div>
            <div className="transition-current" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </div>
          <p className="contexts-stage-label">Применение</p>
          <div className="context-panels">
            {contexts.map((context, index) => (
              <ContextPanel key={context.id} context={context} index={index} total={contexts.length} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
