import { useRef } from 'react'
import { gsap, useGSAP } from './motion.js'

function ContextField({ mode }) {
  const common = (
    <>
      <circle className="context-field-halo" cx="360" cy="360" r="238" />
      <circle className="context-field-core" cx="360" cy="360" r="7" />
    </>
  )

  const fields = {
    directed: (
      <>
        {common}
        <path className="context-field-line" pathLength="1" d="M58 430c128 0 164-140 298-140 112 0 154 72 306 72" />
        <path className="context-field-line is-soft" pathLength="1" d="M58 470c146 0 174-110 302-110 118 0 160 64 302 64" />
        <path className="context-field-line is-faint" pathLength="1" d="M58 510c168 0 188-80 306-80 118 0 166 54 298 54" />
        {[0, 1, 2, 3, 4, 5, 6, 7].map((index) => (
          <circle
            key={index}
            className="context-field-particle"
            cx={392 + index * 32}
            cy={314 + ((index * 29) % 96)}
            r={3 + (index % 3)}
          />
        ))}
      </>
    ),
    concentric: (
      <>
        {common}
        <ellipse className="context-field-line" pathLength="1" cx="360" cy="360" rx="264" ry="150" />
        <ellipse className="context-field-line is-soft" pathLength="1" cx="360" cy="360" rx="196" ry="112" />
        <ellipse className="context-field-line is-faint" pathLength="1" cx="360" cy="360" rx="128" ry="72" />
        <path className="context-field-line is-soft" pathLength="1" d="M82 360h556" />
      </>
    ),
    layered: (
      <>
        {common}
        <path className="context-field-line" pathLength="1" d="M68 252c92-42 174 42 268 0 90-40 170 42 316 0" />
        <path className="context-field-line is-soft" pathLength="1" d="M68 326c92-42 174 42 268 0 90-40 170 42 316 0" />
        <path className="context-field-line is-soft" pathLength="1" d="M68 400c92-42 174 42 268 0 90-40 170 42 316 0" />
        <path className="context-field-line is-faint" pathLength="1" d="M68 474c92-42 174 42 268 0 90-40 170 42 316 0" />
      </>
    ),
    local: (
      <>
        {common}
        <circle className="context-field-line" pathLength="1" cx="360" cy="360" r="184" />
        <circle className="context-field-line is-soft" pathLength="1" cx="360" cy="360" r="116" />
        <path className="context-field-line is-faint" pathLength="1" d="M360 118v484M118 360h484" />
        <circle className="context-field-particle" cx="360" cy="176" r="7" />
        <circle className="context-field-particle" cx="518" cy="454" r="5" />
        <circle className="context-field-particle" cx="250" cy="488" r="4" />
      </>
    ),
    branching: (
      <>
        {common}
        <path className="context-field-line" pathLength="1" d="M54 360h230c78 0 64-150 142-150h236" />
        <path className="context-field-line is-soft" pathLength="1" d="M284 360c78 0 64 0 142 0h236" />
        <path className="context-field-line is-faint" pathLength="1" d="M284 360c78 0 64 150 142 150h236" />
        <circle className="context-field-particle" cx="284" cy="360" r="7" />
        <circle className="context-field-particle" cx="426" cy="210" r="5" />
        <circle className="context-field-particle" cx="426" cy="360" r="5" />
        <circle className="context-field-particle" cx="426" cy="510" r="5" />
      </>
    ),
  }

  return (
    <svg className="context-field" viewBox="0 0 720 720" aria-hidden="true">
      {fields[mode]}
    </svg>
  )
}

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
      <div className="context-panel-visual">
        <ContextField mode={context.visualMode} />
      </div>
      <p className="context-panel-caption">{context.caption}</p>
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

      media.add('(min-width: 992px) and (prefers-reduced-motion: no-preference)', () => {
        const panels = gsap.utils.toArray('.context-panel')
        if (!panels.length) return undefined

        panels.slice(1).forEach((panel) => gsap.set(panel, { yPercent: 100 }))
        gsap.set('.context-field-line', { strokeDashoffset: 1 })
        gsap.set('.context-field-particle', { scale: 0.64, opacity: 0.16, transformOrigin: '50% 50%' })

        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: trackRef.current,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.62,
            pin: stageRef.current,
            pinSpacing: false,
            anticipatePin: 1,
            invalidateOnRefresh: true,
          },
        })

        const firstPanel = panels[0]
        timeline
          .to(firstPanel.querySelectorAll('.context-field-line'), {
            strokeDashoffset: 0,
            duration: 0.42,
            stagger: 0.035,
            ease: 'none',
          })
          .to(
            firstPanel.querySelectorAll('.context-field-particle'),
            { scale: 1, opacity: 0.72, duration: 0.28, stagger: 0.025, ease: 'power2.out' },
            '<0.08',
          )
          .to({}, { duration: 0.34 })

        panels.slice(1).forEach((panel) => {
          const lines = panel.querySelectorAll('.context-field-line')
          const particles = panel.querySelectorAll('.context-field-particle')

          timeline
            .to(panel, { yPercent: 0, duration: 0.62, ease: 'none' })
            .to(lines, { strokeDashoffset: 0, duration: 0.36, stagger: 0.025, ease: 'none' }, '<0.18')

          if (particles.length) {
            timeline.to(
              particles,
              { scale: 1, opacity: 0.72, duration: 0.25, stagger: 0.022, ease: 'power2.out' },
              '<0.04',
            )
          }

          timeline.to({}, { duration: 0.38 })
        })

        return () => timeline.kill()
      })

      return () => media.revert()
    },
    { scope: sectionRef },
  )

  return (
    <section className="contexts" id="contexts" aria-labelledby="contexts-title" ref={sectionRef}>
      <div className="contexts-intro section-pad">
        <div className="contexts-head" data-reveal="rise">
          <h2 id="contexts-title">Одна технология. Разные контексты.</h2>
          <p>
            Мы показываем направления без выдуманных кейсов. Детали каждого сценария уточняются в диалоге.
          </p>
        </div>
      </div>

      <div className="contexts-track" ref={trackRef}>
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
