import { useEffect, useRef, useState } from 'react'
import { assetPath } from './assetPath.js'
import ConceptPhoto from './ConceptPhoto.jsx'
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
    title: 'Спортивные объекты',
    caption:
      'Водоподготовка для бассейнов, купелей и душевых контуров. Состав системы определяем по схеме рециркуляции, качеству исходной воды и требованиям объекта.',
    visualMode: 'directed',
  },
  {
    id: 'veterinary',
    title: 'Ветеринарные объекты',
    caption:
      'Локальная водоподготовка для хозяйственных и технологических контуров. Без лечебных обещаний: сначала изучаем исходную воду и режим использования.',
    visualMode: 'concentric',
  },
  {
    id: 'sanatorium',
    title: 'Санатории',
    caption:
      'Дополнительная ступень водоподготовки для бассейнов, купелей и рекреационных водных зон. Интеграцию рассчитываем вместе с действующей фильтрацией и автоматикой.',
    visualMode: 'layered',
  },
  {
    id: 'family',
    title: 'Частные дома',
    caption:
      'Система для воды в доме, подобранная под источник, анализ воды и требуемый расход. Назначение обработанной воды подтверждается проектом и контрольными измерениями.',
    visualMode: 'local',
  },
  {
    id: 'agriculture',
    title: 'Сельское хозяйство',
    caption:
      'Вода для мойки продукции, тары и технологических контуров. Решение зависит от органической нагрузки, расхода и требований конкретного производства.',
    visualMode: 'branching',
  },
]

const complianceDocuments = [
  {
    title: 'Генераторы озона O3 1, O3 2 и O3 M',
    category: 'Оборудование',
    registration: 'ЕАЭС N RU Д-RU.РА02.В.86418/26',
    validUntil: 'Действует до 25 марта 2031 года',
    href: assetPath('documents/ozone-generator-declaration.pdf'),
  },
  {
    title: 'Косметические озонированные масла',
    category: 'Серийный выпуск',
    registration: 'ЕАЭС N RU Д-RU.РА12.В.18093/25',
    validUntil: 'Действует до 29 декабря 2030 года',
    href: assetPath('documents/ozonated-oils-declaration.pdf'),
  },
  {
    title: 'Гидролаты и травяные вытяжки',
    category: 'Серийный выпуск',
    registration: 'ЕАЭС N RU Д-RU.РА12.В.07428/25',
    validUntil: 'Действует до 29 декабря 2030 года',
    href: assetPath('documents/hydrolats-declaration.pdf'),
  },
]

function Brand({ full = false }) {
  if (full) {
    return (
      <img
        className="brand-full"
        src={assetPath('assets/brand-lockup-navy.png')}
        alt="Дары Синергии"
        width="1289"
        height="1043"
        loading="lazy"
        decoding="async"
      />
    )
  }

  return (
    <a className="brand" href="#top" aria-label="Дары Синергии — на главную">
      <span className="brand-mark" aria-hidden="true">
        <img src={assetPath('assets/brand-mark-navy.png')} alt="" width="848" height="848" decoding="async" />
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

function TextLink({ href, children, className = '', ...props }) {
  return (
    <a className={`text-link ${className}`} href={href} {...props}>
      <span>{children}</span>
      <ArrowMark />
    </a>
  )
}

function HeroVideo() {
  const videoRef = useRef(null)

  useEffect(() => {
    const video = videoRef.current
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let isVisible = true

    const syncPlayback = () => {
      const shouldPlay = isVisible && !document.hidden && !reduceMotion.matches

      if (!shouldPlay) {
        video.pause()
        return
      }

      video.play().catch(() => {
        // The poster remains visible when autoplay is unavailable.
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
    video.addEventListener('canplay', syncPlayback)
    syncPlayback()

    return () => {
      observer.disconnect()
      document.removeEventListener('visibilitychange', syncPlayback)
      reduceMotion.removeEventListener('change', syncPlayback)
      video.removeEventListener('canplay', syncPlayback)
      video.pause()
    }
  }, [])

  return (
    <video
      ref={videoRef}
      className="hero-video"
      autoPlay
      muted
      loop
      playsInline
      preload="metadata"
      poster={assetPath('assets/hero-ozone-water-poster.webp')}
      aria-hidden="true"
      tabIndex={-1}
      disablePictureInPicture
    >
      <source src={assetPath('assets/hero-ozone-water.webm')} type="video/webm" />
      <source src={assetPath('assets/hero-ozone-water.mp4')} type="video/mp4" />
    </video>
  )
}

function MenuMark() {
  return (
    <svg className="menu-mark" viewBox="0 0 26 20" aria-hidden="true">
      <path d="M1 2.5h24M1 10h24M1 17.5h24" />
    </svg>
  )
}

function CloseMark() {
  return (
    <svg className="close-mark" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 3l18 18M21 3L3 21" />
    </svg>
  )
}

function WaterSystemGraphic() {
  return (
    <ConceptPhoto
      className="system-graphic product-photo"
      src={assetPath('assets/photos/optimized/product-water-system-bg-1536.webp')}
      srcSet={`${assetPath('assets/photos/optimized/product-water-system-bg-768.webp')} 768w, ${assetPath('assets/photos/optimized/product-water-system-bg-1536.webp')} 1536w`}
      sizes="100vw"
      mobileSrcSet={`${assetPath('assets/photos/optimized/product-water-system-bg-mobile-720.webp')} 720w`}
      width="1536"
      height="864"
    />
  )
}

function SystemExplainer() {
  const stages = [
    {
      title: 'Подготовка газа',
      copy: 'К генератору подают очищенный и осушенный воздух либо кислород. Газовая часть подбирается под производительность и условия объекта.',
    },
    {
      title: 'Получение озона',
      copy: 'Электрический разряд преобразует часть кислорода O₂ в озон O₃. Озон получают на месте — непосредственно перед вводом в воду.',
    },
    {
      title: 'Ввод и контакт',
      copy: 'Газовую смесь передают в рассчитанный узел смешения. Контактный участок обеспечивает перенос озона в воду и необходимое время реакции.',
    },
    {
      title: 'Контроль и безопасность',
      copy: 'В проекте предусматривают контроль рабочих параметров, вентиляцию и обработку остаточного газа — в составе конкретной схемы объекта.',
    },
  ]

  return (
    <section
      className="system-explainer section-pad"
      aria-labelledby="system-explainer-title"
      data-scroll-snap
      data-text-emergence
    >
      <div className="system-explainer-head">
        <h3 id="system-explainer-title" data-emergence-title>Как формируется система озонирования</h3>
        <p data-emergence-copy>
          Озон работает внутри рассчитанного технологического контура. Поэтому система — это не только
          генератор, а последовательность взаимосвязанных узлов.
        </p>
      </div>

      <ol className="system-flow" data-reveal="rise">
        {stages.map((stage, index) => (
          <li key={stage.title}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <h4>{stage.title}</h4>
            <p>{stage.copy}</p>
          </li>
        ))}
      </ol>

      <div className="system-inputs" data-reveal="rise">
        <p>Для подбора нужны</p>
        <ul>
          <li>назначение контура</li>
          <li>анализ исходной воды</li>
          <li>расход и режим работы</li>
          <li>существующая фильтрация</li>
          <li>требования объекта</li>
        </ul>
        <small>
          Это принципиальная схема. Состав оборудования и контрольные параметры определяются после
          знакомства с задачей.
        </small>
      </div>
    </section>
  )
}

function OilGraphic() {
  return (
    <ConceptPhoto
      className="oil-graphic product-photo"
      src={assetPath('assets/photos/optimized/product-ozonated-oils-bg-1536.webp')}
      srcSet={`${assetPath('assets/photos/optimized/product-ozonated-oils-bg-768.webp')} 768w, ${assetPath('assets/photos/optimized/product-ozonated-oils-bg-1536.webp')} 1536w`}
      sizes="100vw"
      mobileSrcSet={`${assetPath('assets/photos/optimized/product-ozonated-oils-bg-mobile-720.webp')} 720w`}
      width="1536"
      height="864"
    />
  )
}

function HydrolatGraphic() {
  return (
    <ConceptPhoto
      className="hydrolat-graphic product-photo"
      src={assetPath('assets/photos/optimized/product-hydrolats-bg-1536.webp')}
      srcSet={`${assetPath('assets/photos/optimized/product-hydrolats-bg-768.webp')} 768w, ${assetPath('assets/photos/optimized/product-hydrolats-bg-1536.webp')} 1536w`}
      sizes="100vw"
      mobileSrcSet={`${assetPath('assets/photos/optimized/product-hydrolats-bg-mobile-720.webp')} 720w`}
      width="1536"
      height="864"
    />
  )
}

function ProcessDiagram() {
  return (
    <ConceptPhoto
      className="process-diagram process-photo"
      src={assetPath('assets/photos/optimized/process-installation-bg-1536.webp')}
      srcSet={`${assetPath('assets/photos/optimized/process-installation-bg-768.webp')} 768w, ${assetPath('assets/photos/optimized/process-installation-bg-1536.webp')} 1536w`}
      sizes="100vw"
      mobileSrcSet={`${assetPath('assets/photos/optimized/process-installation-bg-mobile-720.webp')} 720w`}
      width="1536"
      height="864"
    />
  )
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const pageRef = useRef(null)
  const menuRef = useRef(null)
  const menuToggleRef = useRef(null)
  const previousFocusRef = useRef(null)
  const restoreFocusRef = useRef(true)

  usePageMotion(pageRef)

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
    <div className="site-shell" id="top" ref={pageRef}>
      <a className="skip-link" href="#main-content" data-menu-background>
        Перейти к содержанию
      </a>

      <header className="site-header" data-menu-background>
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
          aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          onClick={() => setMenuOpen((value) => !value)}
        >
          <MenuMark />
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
          <button className="mobile-menu-close" type="button" aria-label="Закрыть меню" onClick={closeMenu}>
            <CloseMark />
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
        <section className="hero" aria-labelledby="hero-title" data-scroll-snap>
          <HeroVideo />
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

        <section className="opening-statement section-pad" data-scroll-snap data-text-emergence>
          <div className="opening-title">
            <h2 data-emergence-title>Мы работаем с озоном — как с технологией.</h2>
            <p data-emergence-copy>От собственного производства до монтажа на объекте.</p>
          </div>
          <div className="opening-flow" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </section>

        <section className="products" id="products" aria-labelledby="products-title">
          <header className="section-lead section-pad transition-scene" data-scroll-snap data-text-emergence>
            <h2 id="products-title" data-transition-content data-emergence-title>
              Три направления. Один подход к производству.
            </h2>
            <p data-emergence-copy>
              Оборудование, масла и гидролаты выпускаем как отдельные направления — каждое со своей
              задачей и подтверждающими документами. Изображения оборудования, процессов и отраслевых
              сценариев ниже — концептуальные визуализации.
            </p>
            <div className="transition-current" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </header>

          <SystemExplainer />

          <article className="product product-system section-pad" data-scroll-snap data-text-emergence>
            <WaterSystemGraphic />
            <div className="product-copy">
              <h3 data-emergence-title>Системы озонирования воды</h3>
              <p data-emergence-copy>
                Производим оборудование и монтируем его на объектах. Конфигурацию и
                параметры будущей системы обсуждаем под конкретную задачу.
              </p>
              <TextLink href="#contact" data-emergence-copy>Получить консультацию</TextLink>
            </div>
          </article>

          <article className="product product-oil section-pad" data-scroll-snap data-text-emergence>
            <div className="product-copy">
              <h3 data-emergence-title>Озонированные масла</h3>
              <p data-emergence-copy>
                Производим косметические озонированные масла на растительной основе. Серийный
                выпуск задекларирован по требованиям к парфюмерно-косметической продукции.
              </p>
              <TextLink href="#documents" data-emergence-copy>Смотреть декларацию</TextLink>
            </div>
            <OilGraphic />
          </article>

          <article className="product product-hydrolat section-pad" data-scroll-snap data-text-emergence>
            <HydrolatGraphic />
            <div className="product-copy">
              <h3 data-emergence-title>Гидролаты</h3>
              <p data-emergence-copy>
                Производим гидролаты — цветочную воду и травяные вытяжки из растительного сырья.
                Серийный выпуск продукции подтверждён декларацией соответствия.
              </p>
              <TextLink href="#documents" data-emergence-copy>Смотреть декларацию</TextLink>
            </div>
          </article>
        </section>

        <ContextsStory contexts={contexts} />

        <section className="process section-pad" id="process" aria-labelledby="process-title" data-scroll-snap data-text-emergence>
          <header className="process-head">
            <h2 id="process-title" data-emergence-title>От производства — к вашему объекту.</h2>
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

        <section className="evidence section-pad" id="documents" aria-labelledby="evidence-title" data-scroll-snap data-text-emergence>
          <div className="evidence-inner">
            <h2 id="evidence-title" data-emergence-title>Технология — вместо обещаний.</h2>
            <p data-emergence-copy>
              Показываем только то, что можно проверить. Генераторы озона, косметические масла и
              гидролаты имеют действующие декларации соответствия Евразийского экономического
              союза.
            </p>
            <div className="evidence-documents" aria-label="Документы о соответствии">
              {complianceDocuments.map((document) => (
                <a className="evidence-document" href={document.href} key={document.href}>
                  <div className="evidence-document-title">
                    <span>{document.category}</span>
                    <h3>{document.title}</h3>
                  </div>
                  <div className="evidence-document-meta">
                    <p>{document.registration}</p>
                    <span>{document.validUntil}</span>
                  </div>
                  <span className="evidence-document-action">
                    <span>Открыть PDF</span>
                    <ArrowMark />
                  </span>
                </a>
              ))}
            </div>
          </div>
        </section>

        <section className="contact section-pad" id="contact" aria-labelledby="contact-title" data-scroll-snap data-text-emergence>
          <div className="contact-top">
            <h2 id="contact-title" data-emergence-title>
              Получить
              <br />
              консультацию
            </h2>
            <Brand full />
          </div>
          <div className="contact-actions">
            <div className="contact-company">
              <span>Компания</span>
              <p>«Дары Синергии»</p>
              <small>ИП Бобко Роман Викторович</small>
            </div>
            <a href="mailto:sintez2016@gmail.com">
              <span>Электронная почта</span>
              <p>sintez2016@gmail.com</p>
            </a>
            <a href="tel:+79060104066">
              <span>Телефон</span>
              <p>+7 (906) 010-40-66</p>
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer" data-menu-background>
        <p>© 2026 «Дары Синергии» · ИП Бобко Роман Викторович</p>
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
