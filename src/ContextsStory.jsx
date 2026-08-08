import { useRef } from 'react'
import { assetPath } from './assetPath.js'
import ConceptPhoto from './ConceptPhoto.jsx'
import { gsap, useGSAP } from './motion.js'

function ContextPanel({ context, index, total }) {
  return (
    <article className={`context-panel context-panel-${context.id}`} data-mobile-snap>
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

      media.add('(min-width: 992px) and (prefers-reduced-motion: no-preference)', createStackedStory)
      return () => media.revert()
    },
    { scope: sectionRef },
  )

  return (
    <section className="contexts" id="contexts" aria-labelledby="contexts-title" ref={sectionRef}>
      <div className="contexts-intro section-pad transition-scene" data-scroll-snap data-text-emergence>
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
