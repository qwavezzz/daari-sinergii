import { useEffect, useRef, useState } from 'react'
import App from './App.jsx'
import { assetPath } from './assetPath.js'
import { documents, topics, documentUrl } from './materials.js'
import './materials.css'

export function Arrow() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d="M3 9h11M10 4l5 5-5 5" /></svg>
}

function DocumentRow({ document }) {
  return <article className="material-document">
    <div><p className="material-meta">{document.type} · PDF · {document.pages} стр.</p><h3>{document.title}</h3><p>{document.description}</p></div>
    <div className="material-document-actions"><a href={documentUrl(document)} target="_blank" rel="noreferrer" aria-label={`Открыть «${document.title}» (PDF, новая вкладка)`}>Открыть PDF <Arrow /></a><a href={documentUrl(document)} download>Скачать</a></div>
  </article>
}

export function HandbookFeature() {
  const handbook = documents.find(document => document.id === 'handbook')
  return <div className="handbook-feature"><div><h3>Вся тема — в одном справочнике.</h3><p>Масла, кремы, водные процедуры, ветеринария и ограничения применения.</p></div><a href={documentUrl(handbook)} target="_blank" rel="noreferrer">Открыть справочник <span>PDF · 9 страниц · новая вкладка</span><Arrow /></a></div>
}

function MaterialsPage({ slug }) {
  const topic = topics.find(item => item.id === slug)
  const missing = Boolean(slug && !topic)
  const [filter, setFilter] = useState('all')
  const title = missing ? 'Материал не найден' : topic?.title || 'Материалы о технологии и применении'
  useEffect(() => { document.title = `${title} — Дары Синергии`; window.scrollTo({ top: 0, behavior: 'instant' }) }, [title])
  const selected = topic ? documents.filter(doc => topic.docs.includes(doc.id)) : filter === 'all' ? documents : documents.filter(doc => topics.find(item => item.id === filter)?.docs.includes(doc.id) || doc.id === 'handbook')
  return <div className="materials-page">
    <a className="skip-link" href="#material-content">Перейти к содержанию</a>
    <header className="materials-header"><a className="materials-brand" href="#top"><img src={assetPath('assets/brand-mark-navy.png')} alt="" />Дары Синергии</a><nav aria-label="Навигация материалов"><a href="#/materials">Все материалы</a><a href="#return">Вернуться к сайту</a><a href="#contact">Связаться</a></nav></header>
    <main id="material-content">
      <section className={`materials-hero ${topic?.image ? 'has-image' : ''}`}>
        <div><a className="material-back" href={topic ? '#/materials' : '#top'}>{topic ? 'Все материалы' : 'На главную'}</a><h1>{title}</h1><p>{missing ? 'Проверьте адрес или откройте каталог материалов.' : topic?.intro || 'Презентации, справочные материалы и документы компании. Выберите своё направление или познакомьтесь с технологией.'}</p></div>
        {topic?.image && <figure><img src={assetPath(`assets/photos/optimized/${topic.image}-bg-768.webp`)} alt="" /><figcaption>Концептуальная визуализация</figcaption></figure>}
      </section>
      {missing ? <div className="materials-body"><a href="#/materials">Открыть каталог материалов</a></div> : <>
        {!topic && <nav className="topic-directory" aria-label="Материалы по направлениям">{topics.map(item => <a key={item.id} href={`#/materials/${item.id}`}><span>{item.title}</span><Arrow /></a>)}</nav>}
        <div className="materials-body">
          {topic && <section className="material-overview" aria-label="О подборке">{topic.sections.map(([heading, copy]) => <div key={heading}><h2>{heading}</h2><p>{copy}</p></div>)}</section>}
          <section aria-labelledby="library-title"><div className="library-heading"><h2 id="library-title">{topic ? 'Материалы по теме' : 'Библиотека документов'}</h2>{!topic && <label>Направление<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">Все направления</option>{topics.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}</div>
            <div aria-live="polite"><p className="material-meta">Документов: {selected.length}</p>{selected.map(document => <DocumentRow key={document.id} document={document} />)}</div>
          </section>
          <HandbookFeature />
          {topic?.chapter && <p className="handbook-chapter"><a target="_blank" rel="noreferrer" href={`${documentUrl(documents.find(doc => doc.id === 'handbook'))}#page=${topic.chapter}`}>Раздел по теме в справочнике — со страницы {topic.chapter} (PDF, новая вкладка)</a></p>}
          <section className="material-evidence"><h2>Что подтверждают материалы</h2><div><p>Презентации знакомят с предлагаемыми сценариями. Справочные материалы помогают разобраться в теме. В этой библиотеке пока нет опубликованных отчётов об испытаниях конкретной продукции компании.</p><p>Декларации соответствия доступны отдельно. Они относятся к продукции и требованиям соответствия; заявленные эффекты процедур требуют собственных исследований.</p><a href="#documents">Смотреть декларации <Arrow /></a></div></section>
          <section className="material-contact"><h2>Обсудим вашу задачу.</h2><p>Поможем сориентироваться в направлениях и уточнить документы для вашего объекта.</p><a href={`mailto:sintez2016@gmail.com?subject=${encodeURIComponent(topic ? `Вопрос: ${topic.title}` : 'Вопрос о материалах компании')}`}>Написать в компанию <Arrow /></a><a href="tel:+79060104066">+7 (906) 010-40-66</a></section>
        </div>
      </>}
    </main><footer className="materials-footer"><p>© 2026 Дары Синергии · ИП Бобко Роман Викторович</p><a href="#top">Вернуться на главную</a></footer>
  </div>
}

export default function SiteRouter() {
  const [hash, setHash] = useState(window.location.hash)
  const homeScroll = useRef(0)
  useEffect(() => {
    const remember = event => {
      if (!window.location.hash.startsWith('#/materials') && event.target.closest('a[href^="#/materials"]')) homeScroll.current = window.scrollY
    }
    const update = () => setHash(window.location.hash)
    document.addEventListener('click', remember, true)
    window.addEventListener('hashchange', update)
    return () => { window.removeEventListener('hashchange', update); document.removeEventListener('click', remember, true) }
  }, [])
  const materialRoute = hash === '#/materials' || hash.startsWith('#/materials/')
  useEffect(() => {
    if (materialRoute) return
    document.title = 'Дары Синергии — системы озонирования воды, масла и гидролаты'
    const timer = setTimeout(() => {
      const target = document.getElementById(hash.slice(1))
      if (target) target.scrollIntoView({ behavior: 'instant' })
      else if (hash === '#return' || !hash) window.scrollTo({ top: homeScroll.current, behavior: 'instant' })
    }, 150)
    return () => clearTimeout(timer)
  }, [materialRoute, hash])
  return materialRoute ? <MaterialsPage key={hash} slug={hash.slice('#/materials'.length).replace(/^\//, '')} /> : <App />
}
