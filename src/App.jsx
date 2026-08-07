import { useEffect, useRef, useState } from 'react'
import ContextsStory from './ContextsStory.jsx'
import { usePageMotion } from './motion.js'

const navItems = [
  ['Решения', '#products'],
  ['Применение', '#contexts'],
  ['Производство', '#process'],
  ['Контакты', '#contact'],
]

const contexts = [
  {
    id: 'sport',
    title: 'Спортивные клубы',
    caption: 'Спортивная инфраструктура',
    visualMode: 'directed',
  },
  {
    id: 'veterinary',
    title: 'Ветеринария',
    caption: 'Вода и уходовые процессы',
    visualMode: 'concentric',
  },
  {
    id: 'sanatorium',
    title: 'Санатории',
    caption: 'Инфраструктура объектов',
    visualMode: 'layered',
  },
  {
    id: 'family',
    title: 'Для всей семьи',
    caption: 'Частные сценарии использования',
    visualMode: 'local',
  },
  {
    id: 'agriculture',
    title: 'Сельское хозяйство',
    caption: 'Вода и хозяйственные процессы',
    visualMode: 'branching',
  },
]

function Brand({ full = false }) {
  if (full) {
    return (
      <img
        className="brand-full"
        src="/assets/brand-lockup-navy.png"
        alt="Дары Синергии"
      />
    )
  }

  return (
    <a className="brand" href="#top" aria-label="Дары Синергии — на главную">
      <span className="brand-mark" aria-hidden="true">
        <img src="/assets/brand-mark-navy.png" alt="" />
      </span>
      <span>Дары Синергии</span>
    </a>
  )
}

function ArrowMark() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true">
      <path d="M3 9h11M10 4l5 5-5 5" />
    </svg>
  )
}

function TextLink({ href, children, className = '' }) {
  return (
    <a className={`text-link ${className}`} href={href}>
      <span>{children}</span>
      <ArrowMark />
    </a>
  )
}

function OzoneWaterCanvas({ scrollProgressRef }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d', { alpha: false })
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let animationFrame = 0
    let isVisible = true
    let width = 0
    let height = 0
    let dpr = 1
    let bubbles = []

    const randomBubble = (initial = true) => ({
      t: initial ? Math.random() : 0,
      lane: (Math.random() + Math.random() + Math.random() - 1.5) / 1.5,
      wobble: Math.random() * Math.PI * 2,
      radius: 0.6 + Math.random() * 1.7,
      speed: 0.0012 + Math.random() * 0.002,
      opacity: 0.22 + Math.random() * 0.58,
    })

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = rect.width
      height = rect.height
      dpr = Math.min(window.devicePixelRatio || 1, 1.6)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.min(260, Math.max(120, Math.floor(width / 5)))
      bubbles = Array.from({ length: count }, () => randomBubble(true))
      draw(0)
    }

    const drawWaterField = (sourceX, sourceY, time) => {
      ctx.save()
      ctx.globalCompositeOperation = 'screen'
      ctx.lineWidth = 1

      for (let i = 0; i < 7; i += 1) {
        const fieldY = height * (0.12 + i * 0.13)
        const phase = time * 0.00018 + i * 0.82
        const lift = Math.sin(phase) * 7
        ctx.strokeStyle = `rgba(137, 191, 226, ${0.035 + (i % 3) * 0.018})`
        ctx.beginPath()
        ctx.moveTo(-width * 0.05, fieldY + lift)
        ctx.bezierCurveTo(
          width * 0.22,
          fieldY - 14 + lift,
          width * 0.5,
          fieldY + 18 * Math.sin(phase * 1.3),
          width * 0.72,
          fieldY - 9 + lift,
        )
        ctx.bezierCurveTo(
          width * 0.84,
          fieldY - 18 * Math.cos(phase),
          width * 1.05,
          fieldY + 12 + lift,
          width * 1.08,
          fieldY + lift,
        )
        ctx.stroke()
      }

      for (let i = 0; i < 6; i += 1) {
        const wakeY = sourceY + (i - 2.5) * 13
        const turbulence = Math.sin(time * 0.00055 + i * 1.7) * 10
        ctx.strokeStyle = `rgba(177, 223, 246, ${0.08 + i * 0.012})`
        ctx.beginPath()
        ctx.moveTo(sourceX + 5, wakeY)
        ctx.bezierCurveTo(
          sourceX + width * 0.12,
          wakeY + turbulence,
          sourceX + width * 0.3,
          wakeY - turbulence * 0.7 + (i - 2.5) * 15,
          sourceX + width * 0.47,
          wakeY + turbulence * 0.45 + (i - 2.5) * 28,
        )
        ctx.stroke()
      }
      ctx.restore()
    }

    const drawDiffuser = (sourceX, sourceY) => {
      const glow = ctx.createRadialGradient(sourceX, sourceY, 2, sourceX, sourceY, 34)
      glow.addColorStop(0, 'rgba(217,243,255,.3)')
      glow.addColorStop(0.45, 'rgba(137,191,226,.12)')
      glow.addColorStop(1, 'rgba(137,191,226,0)')
      ctx.fillStyle = glow
      ctx.fillRect(sourceX - 38, sourceY - 38, 76, 76)

      ctx.save()
      ctx.translate(sourceX, sourceY)
      ctx.rotate(-0.1)
      ctx.fillStyle = 'rgba(4,16,31,.9)'
      ctx.strokeStyle = 'rgba(177,223,246,.72)'
      ctx.lineWidth = 1.2
      ctx.beginPath()
      ctx.roundRect(-22, -30, 24, 60, 9)
      ctx.fill()
      ctx.stroke()
      ctx.strokeStyle = 'rgba(137,191,226,.4)'
      for (let y = -18; y <= 18; y += 9) {
        ctx.beginPath()
        ctx.moveTo(-16, y)
        ctx.lineTo(-5, y + 1.5)
        ctx.stroke()
      }
      ctx.beginPath()
      ctx.moveTo(-34, 0)
      ctx.lineTo(-22, 0)
      ctx.stroke()
      ctx.restore()
    }

    const draw = (time) => {
      const scrollProgress = scrollProgressRef?.current ?? 0
      const sourceX = width * (width < 600 ? 0.42 : 0.31) + width * scrollProgress * 0.012
      const sourceY = height * 0.54

      const base = ctx.createLinearGradient(0, 0, width, height)
      base.addColorStop(0, '#04101f')
      base.addColorStop(0.48, '#06182e')
      base.addColorStop(1, '#082041')
      ctx.fillStyle = base
      ctx.fillRect(0, 0, width, height)

      const waterGlow = ctx.createLinearGradient(sourceX, sourceY, width, sourceY)
      waterGlow.addColorStop(0, 'rgba(137,191,226,.04)')
      waterGlow.addColorStop(0.42, 'rgba(137,191,226,.16)')
      waterGlow.addColorStop(1, 'rgba(4,16,31,0)')
      ctx.fillStyle = waterGlow
      ctx.fillRect(0, 0, width, height)

      drawWaterField(sourceX, sourceY, time)
      drawDiffuser(sourceX, sourceY)

      ctx.save()
      ctx.globalCompositeOperation = 'screen'
      for (let i = 0; i < bubbles.length; i += 1) {
        const bubble = bubbles[i]
        if (!reduceMotion.matches) bubble.t += bubble.speed
        if (bubble.t > 1.05) bubbles[i] = randomBubble(false)

        const t = Math.min(bubble.t, 1)
        const eased = t * (1.18 - t * 0.18)
        const x = sourceX + 4 + eased * (width * 0.74)
        const spread = t ** 1.35 * height * 0.2
        const y =
          sourceY +
          bubble.lane * spread +
          Math.sin(bubble.wobble + time * 0.00075 + t * 9) * (2 + t * 8) -
          t * height * 0.045
        const radius = Math.max(0.45, bubble.radius * (1.15 - t * 0.64))
        const alpha = bubble.opacity * (0.92 - t * 0.58)

        ctx.beginPath()
        ctx.arc(x, y, radius, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(137, 191, 226, ${alpha * 0.28})`
        ctx.fill()
        ctx.strokeStyle = `rgba(217, 243, 255, ${alpha})`
        ctx.lineWidth = Math.max(0.45, radius * 0.34)
        ctx.stroke()
      }
      ctx.restore()

      if (scrollProgress > 0) {
        ctx.fillStyle = `rgba(4, 16, 31, ${scrollProgress * 0.16})`
        ctx.fillRect(0, 0, width, height)
      }
    }

    const loop = (time) => {
      if (isVisible) draw(time)
      animationFrame = requestAnimationFrame(loop)
    }

    const observer = new IntersectionObserver(([entry]) => {
      isVisible = entry.isIntersecting
    })
    observer.observe(canvas)
    window.addEventListener('resize', resize)
    resize()
    animationFrame = requestAnimationFrame(loop)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(animationFrame)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="ozone-canvas"
      aria-hidden="true"
      data-video-placeholder="public/media/hero-ozone-water.webm"
    />
  )
}

function WaterSystemGraphic() {
  return (
    <div className="system-graphic" aria-hidden="true">
      <svg viewBox="0 0 760 540">
        <defs>
          <radialGradient id="systemGlow">
            <stop offset="0" stopColor="#f7fbfd" />
            <stop offset=".28" stopColor="#b1dff6" stopOpacity=".9" />
            <stop offset="1" stopColor="#89bfe2" stopOpacity="0" />
          </radialGradient>
        </defs>
        <path className="system-line" d="M56 273h225c70 0 80-116 150-116h268" />
        <path className="system-line soft" d="M56 273h225c70 0 80 116 150 116h268" />
        <circle className="system-ring" cx="290" cy="273" r="88" />
        <circle className="system-ring soft" cx="290" cy="273" r="52" />
        <circle cx="290" cy="273" r="64" fill="url(#systemGlow)" />
        <circle className="system-node" cx="290" cy="273" r="7" />
        <circle className="system-node" cx="432" cy="157" r="5" />
        <circle className="system-node" cx="432" cy="389" r="5" />
        {Array.from({ length: 28 }).map((_, index) => (
          <circle
            key={index}
            className="system-bubble"
            cx={430 + ((index * 47) % 250)}
            cy={210 + ((index * 83) % 150)}
            r={2 + (index % 4)}
          />
        ))}
      </svg>
    </div>
  )
}

function OilGraphic() {
  return (
    <div className="oil-graphic" aria-hidden="true">
      <svg viewBox="0 0 620 620">
        <defs>
          <clipPath id="oilDropClip">
            <path d="M310 58C246 164 132 280 132 397c0 98 80 165 178 165s178-67 178-165C488 280 374 164 310 58Z" />
          </clipPath>
          <linearGradient id="oilFillGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#89bfe2" stopOpacity=".24" />
            <stop offset="1" stopColor="#0b2b5a" stopOpacity=".48" />
          </linearGradient>
        </defs>
        <g clipPath="url(#oilDropClip)">
          <rect className="oil-fill" x="120" y="48" width="380" height="524" fill="url(#oilFillGradient)" />
        </g>
        <path
          className="oil-drop"
          d="M310 58C246 164 132 280 132 397c0 98 80 165 178 165s178-67 178-165C488 280 374 164 310 58Z"
        />
        <path className="oil-wave" d="M166 399c58-34 101 47 164 10 66-39 91 32 128 8" />
        <path className="oil-wave delay" d="M176 443c54-30 93 36 151 9 61-29 86 23 121 10" />
        <circle className="oil-orbit" cx="310" cy="310" r="238" />
      </svg>
    </div>
  )
}

function HydrolatGraphic() {
  return (
    <div className="hydrolat-graphic" aria-hidden="true">
      <svg viewBox="0 0 760 540">
        <path className="steam-path" d="M120 430c0-116 86-107 86-207 0-70-50-81-50-153" />
        <path className="steam-path second" d="M284 430c0-101 78-119 78-208 0-61-34-96-34-152" />
        <path className="steam-path third" d="M448 430c0-115 73-112 73-202 0-64-34-95-34-158" />
        <path className="condenser" d="M100 430h485c42 0 70-30 70-68V236" />
        <circle className="hydro-drop" cx="655" cy="220" r="12" />
        <circle className="hydro-drop small" cx="655" cy="185" r="7" />
        <path className="hydro-surface" d="M104 465c83-24 151 21 229 0 74-20 149 20 232 0" />
      </svg>
    </div>
  )
}

function ProcessDiagram() {
  return (
    <div className="process-diagram" aria-hidden="true">
      <svg viewBox="0 0 900 380">
        <path className="process-path" d="M64 190h300c48 0 60-92 108-92h356" />
        <path className="process-path dim" d="M64 190h300c48 0 60 92 108 92h356" />
        <circle className="process-halo" cx="422" cy="190" r="114" />
        <circle className="process-core" cx="422" cy="190" r="9" />
        <rect className="process-terminal" x="62" y="151" width="88" height="78" />
        <rect className="process-terminal" x="752" y="151" width="76" height="78" />
      </svg>
    </div>
  )
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const pageRef = useRef(null)
  const heroProgressRef = useRef(0)
  const menuRef = useRef(null)
  const menuToggleRef = useRef(null)
  const previousFocusRef = useRef(null)
  const restoreFocusRef = useRef(true)

  usePageMotion(pageRef, heroProgressRef)

  useEffect(() => {
    const nodes = document.querySelectorAll('[data-reveal]')
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
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const backgroundNodes = document.querySelectorAll('[data-menu-background]')

    if (!menuOpen) {
      document.body.classList.remove('menu-lock')
      return undefined
    }

    previousFocusRef.current = document.activeElement
    document.body.classList.add('menu-lock')
    backgroundNodes.forEach((node) => {
      node.inert = true
      node.setAttribute('aria-hidden', 'true')
    })

    const focusFrame = requestAnimationFrame(() => {
      menuRef.current?.querySelector('button')?.focus()
    })

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        restoreFocusRef.current = true
        setMenuOpen(false)
        return
      }

      if (event.key !== 'Tab' || !menuRef.current) return
      const focusable = Array.from(
        menuRef.current.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
      ).filter((element) => element.getClientRects().length > 0)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      cancelAnimationFrame(focusFrame)
      document.body.classList.remove('menu-lock')
      backgroundNodes.forEach((node) => {
        node.inert = false
        node.removeAttribute('aria-hidden')
      })
      window.removeEventListener('keydown', onKeyDown)
      if (restoreFocusRef.current) {
        requestAnimationFrame(() => {
          const target = previousFocusRef.current?.isConnected
            ? previousFocusRef.current
            : menuToggleRef.current
          target?.focus()
        })
      }
      restoreFocusRef.current = true
    }
  }, [menuOpen])

  const closeMenu = (restoreFocus = true) => {
    restoreFocusRef.current = restoreFocus
    setMenuOpen(false)
  }

  return (
    <div className="site-shell" ref={pageRef}>
      <a className="skip-link" href="#main-content" data-menu-background>
        Перейти к содержанию
      </a>

      <header className="site-header" id="top" data-menu-background>
        <Brand />
        <nav className="desktop-nav" aria-label="Основная навигация">
          {navItems.map(([label, href]) => (
            <a key={href} href={href}>
              {label}
            </a>
          ))}
        </nav>
        <button
          ref={menuToggleRef}
          className="menu-toggle"
          type="button"
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          onClick={() => setMenuOpen((value) => !value)}
        >
          {menuOpen ? 'Закрыть' : 'Меню'}
        </button>
      </header>

      <div
        ref={menuRef}
        className={`mobile-menu ${menuOpen ? 'is-open' : ''}`}
        id="mobile-menu"
        role="dialog"
        aria-modal="true"
        aria-label="Навигация"
        aria-hidden={!menuOpen}
      >
        <div className="mobile-menu-top">
          <Brand />
          <button type="button" onClick={closeMenu}>
            Закрыть
          </button>
        </div>
        <nav aria-label="Мобильная навигация">
          {navItems.map(([label, href]) => (
            <a key={href} href={href} onClick={() => closeMenu(false)}>
              {label}
            </a>
          ))}
        </nav>
        <p>Производим. Монтируем. Работаем с озоном без лишних обещаний.</p>
      </div>

      <main id="main-content" data-menu-background>
        <section className="hero" aria-labelledby="hero-title">
          <OzoneWaterCanvas scrollProgressRef={heroProgressRef} />
          <div className="hero-vignette" aria-hidden="true" />
          <div className="hero-content">
            <h1 id="hero-title">
              Озон —
              <br />
              сила природы.
            </h1>
            <p>
              Производим и монтируем системы озонирования воды. Создаём озонированные
              масла и гидролаты.
            </p>
            <TextLink href="#products">Смотреть решения</TextLink>
          </div>
          <div className="hero-products" aria-label="Направления компании">
            <span>Системы для воды</span>
            <span>Озонированные масла</span>
            <span>Гидролаты</span>
          </div>
          <p className="hero-caption" aria-hidden="true">
            O₃ + H₂O
          </p>
        </section>

        <section className="opening-statement section-pad">
          <div className="opening-title" data-reveal="clip">
            <h2>Мы работаем с озоном — как с технологией.</h2>
            <p>От собственного производства до монтажа на объекте.</p>
          </div>
          <div className="opening-flow" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </section>

        <section className="products" id="products" aria-labelledby="products-title">
          <header className="section-lead section-pad" data-reveal="rise">
            <h2 id="products-title">Три направления. Один подход к производству.</h2>
            <p>Каждый продукт раскрываем отдельно — без смешения задач и обещаний.</p>
          </header>

          <article className="product product-system section-pad">
            <WaterSystemGraphic />
            <div className="product-copy" data-reveal="clip">
              <h3>Системы озонирования воды</h3>
              <p>
                Производим оборудование и монтируем его на объектах. Конфигурацию и
                параметры будущей системы обсуждаем под конкретную задачу.
              </p>
              <TextLink href="#contact">Обсудить объект</TextLink>
            </div>
          </article>

          <article className="product product-oil section-pad">
            <div className="product-copy" data-reveal="rise">
              <h3>Озонированные масла</h3>
              <p>
                Производим отдельную линейку озонированных масел. Состав, форматы и
                подтверждённые сценарии появятся здесь после согласования продуктовых данных.
              </p>
              <span className="quiet-note">Описание готовится</span>
            </div>
            <OilGraphic />
          </article>

          <article className="product product-hydrolat section-pad">
            <HydrolatGraphic />
            <div className="product-copy" data-reveal="clip">
              <h3>Гидролаты</h3>
              <p>
                Водные продукты паровой или гидродистилляции растительного сырья. Производим
                гидролаты и готовим подробное описание линейки.
              </p>
              <a
                className="source-link"
                href="https://ru.wikipedia.org/wiki/Гидролат"
                target="_blank"
                rel="noreferrer"
              >
                Что такое гидролат
              </a>
            </div>
          </article>
        </section>

        <ContextsStory contexts={contexts} />

        <section className="process section-pad" id="process" aria-labelledby="process-title">
          <header className="process-head" data-reveal="clip">
            <h2 id="process-title">От производства — к вашему объекту.</h2>
          </header>
          <ProcessDiagram />
          <div className="process-acts">
            <article>
              <h3>Производим</h3>
              <p>
                Собственное производство — отправная точка систем озонирования воды и
                продуктовых направлений компании.
              </p>
            </article>
            <article>
              <h3>Монтируем</h3>
              <p>
                Устанавливаем системы непосредственно на объектах. Подробности проекта
                фиксируются после знакомства с задачей.
              </p>
            </article>
          </div>
        </section>

        <section className="evidence section-pad" aria-labelledby="evidence-title">
          <div className="evidence-inner">
            <h2 id="evidence-title">Технология — вместо обещаний.</h2>
            <p>
              Мы не подменяем инженерную работу громкими словами. Характеристики, режимы,
              документы и эффекты публикуются только тогда, когда для них есть подтверждённые
              данные.
            </p>
          </div>
        </section>

        <section className="contact section-pad" id="contact" aria-labelledby="contact-title">
          <div className="contact-top">
            <h2 id="contact-title" data-reveal="clip">
              Обсудим
              <br />
              вашу задачу?
            </h2>
            <Brand full />
          </div>
          <div className="contact-actions">
            <div>
              <span>Электронная почта</span>
              <p aria-label="Адрес электронной почты будет добавлен">Будет добавлена</p>
            </div>
            <div>
              <span>Телефон</span>
              <p aria-label="Номер телефона будет добавлен">Будет добавлен</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer" data-menu-background>
        <p>© Дары Синергии</p>
        <nav aria-label="Навигация в подвале">
          {navItems.slice(0, 3).map(([label, href]) => (
            <a key={href} href={href}>
              {label}
            </a>
          ))}
        </nav>
        <a href="#top">Наверх</a>
      </footer>
    </div>
  )
}

export default App
