import L from 'leaflet'
import Supercluster from 'supercluster'
import 'leaflet/dist/leaflet.css'

export function createPickupMap(root, { tileUrl, attribution, onChoose, onTileState, onViewChange }) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const map = L.map(root, {
    scrollWheelZoom: true,
    attributionControl: false,
    zoomControl: false,
    minZoom: 2,
    maxZoom: 19,
    zoomAnimation: !reducedMotion,
    fadeAnimation: !reducedMotion,
  }).setView([57, 60], 3)
  L.control.zoom({ position: 'bottomright', zoomInTitle: 'Приблизить', zoomOutTitle: 'Отдалить' }).addTo(map)
  const credit = L.control({ position: 'bottomleft' })
  credit.onAdd = () => {
    const node = L.DomUtil.create('div', 'leaflet-control-attribution')
    const link = document.createElement('a')
    link.href = 'https://www.openstreetmap.org/copyright'
    link.target = '_blank'
    link.rel = 'noopener'
    link.textContent = '© OpenStreetMap contributors'
    link.setAttribute('hx-boost', 'false')
    node.append(link)
    if (attribution) node.append(document.createTextNode(` · ${attribution}`))
    L.DomEvent.disableClickPropagation(node)
    return node
  }
  credit.addTo(map)
  const tiles = L.tileLayer(tileUrl, {
    maxZoom: 19,
    minZoom: 2,
    keepBuffer: 0,
    updateWhenIdle: true,
    referrerPolicy: 'strict-origin-when-cross-origin',
  })
  let tileTimer,
    tileFailed = false
  tiles.on('loading', () => {
    tileFailed = false
    clearTimeout(tileTimer)
    tileTimer = setTimeout(() => onTileState(false), 12000)
  })
  tiles.on('load', () => {
    clearTimeout(tileTimer)
    onTileState(!tileFailed)
  })
  tiles.on('tileerror', () => {
    tileFailed = true
    clearTimeout(tileTimer)
    onTileState(false)
  })
  tiles.addTo(map)
  const layer = L.layerGroup().addTo(map)
  const markers = new Map()
  let indexVersion = 0
  let points = [],
    selected = '',
    index,
    userMarker
  const hasCoordinates = (point) => Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  const viewBounds = () => {
    const bounds = map.getBounds()
    const wrap = (lon) => ((((lon + 180) % 360) + 360) % 360) - 180
    const wholeWorld = bounds.getEast() - bounds.getWest() >= 360
    return {
      west: wholeWorld ? -180 : wrap(bounds.getWest()),
      east: wholeWorld ? 180 : wrap(bounds.getEast()),
      south: bounds.getSouth(),
      north: bounds.getNorth(),
    }
  }
  const makePopup = (offices, marker) => {
    const popup = document.createElement('div')
    popup.className = 'cdek-point-popup'
    for (const office of offices) {
      const item = document.createElement('div')
      const address = document.createElement('strong')
      address.textContent = [office.city, office.address].filter(Boolean).join(', ')
      const details = document.createElement('p')
      details.textContent = [`ПВЗ ${office.code}`, office.work_time].filter(Boolean).join(' · ')
      const choose = document.createElement('button')
      choose.type = 'button'
      choose.className = 'shop-button'
      choose.textContent = 'Выбрать этот пункт'
      choose.addEventListener('click', () => {
        map.closePopup()
        onChoose(office.code)
      })
      item.append(address, details, choose)
      popup.append(item)
    }
    marker.bindPopup(popup, { maxWidth: 280, autoPanPadding: [20, 20] }).openPopup()
    marker
      .getPopup()
      .getElement()
      .querySelector('.leaflet-popup-close-button')
      ?.setAttribute('aria-label', 'Закрыть карточку пункта')
    popup.querySelector('button')?.focus({ preventScroll: true })
  }
  const render = () => {
    if (!index) return
    const visible = new Set()
    const bounds = viewBounds()
    const features = index.getClusters(
      [bounds.west, bounds.south, bounds.east, bounds.north],
      Math.round(map.getZoom()),
    )
    for (const feature of features) {
      const properties = feature.properties
      const cluster = Boolean(properties.cluster)
      const office = cluster ? null : points[properties.position]
      const key = `${indexVersion}:${cluster ? `cluster-${properties.cluster_id}` : office.code}`
      visible.add(key)
      if (markers.has(key)) continue
      const isSelected = cluster ? properties.selected : office.code === selected
      const size = cluster ? (properties.point_count >= 100 ? 60 : 52) : 44
      const icon = document.createElement('span')
      icon.className = `cdek-pin${cluster ? ' cdek-pin-cluster' : ''}${isSelected ? ' is-selected' : ''}`
      icon.textContent = cluster ? properties.point_count_abbreviated : 'С'
      icon.style.width = `${size}px`
      icon.style.height = `${size}px`
      const title = cluster
        ? `Пунктов: ${properties.point_count}. Приблизить`
        : `ПВЗ ${office.code}: ${office.address}`
      const [longitude, latitude] = feature.geometry.coordinates
      const marker = L.marker([latitude, longitude], {
        icon: L.divIcon({
          className: 'cdek-marker',
          html: icon,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        }),
        title,
        keyboard: true,
        riseOnHover: true,
      }).addTo(layer)
      markers.set(key, marker)
      marker.getElement()?.setAttribute('aria-label', title)
      marker.on('click', () => {
        if (!cluster) {
          makePopup([office], marker)
          return
        }
        const zoom = index.getClusterExpansionZoom(properties.cluster_id)
        if (zoom <= 19) map.setView([latitude, longitude], zoom, { animate: !reducedMotion })
        else
          makePopup(
            index.getLeaves(properties.cluster_id, 50).map((item) => points[item.properties.position]),
            marker,
          )
      })
    }
    for (const [key, marker] of markers) {
      // Popup auto-pan must not remove the marker the customer is interacting with.
      if (!visible.has(key) && !marker.isPopupOpen()) {
        layer.removeLayer(marker)
        markers.delete(key)
      }
    }
  }
  const reindex = () => {
    indexVersion += 1
    index = new Supercluster({
      radius: 56,
      extent: 256,
      maxZoom: 19,
      map: (props) => ({ selected: props.selected }),
      reduce: (accumulated, props) => {
        accumulated.selected ||= props.selected
      },
    }).load(
      points.flatMap((point, position) =>
        hasCoordinates(point)
          ? [
              {
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [point.longitude, point.latitude] },
                properties: { position, selected: point.code === selected },
              },
            ]
          : [],
      ),
    )
    render()
  }
  map.on('moveend', () => {
    render()
    onViewChange?.(viewBounds())
  })
  return {
    setPoints(value, { selectedCode = '' } = {}) {
      points = value
      selected = selectedCode
      reindex()
      onViewChange?.(viewBounds())
    },
    fit(value) {
      const coordinates = value.filter(hasCoordinates).map((point) => [point.latitude, point.longitude])
      if (coordinates.length) map.fitBounds(coordinates, { padding: [45, 45], maxZoom: 15, animate: false })
    },
    select(code) {
      selected = code
      reindex()
    },
    locate(latitude, longitude) {
      userMarker?.remove()
      userMarker = L.circleMarker([latitude, longitude], {
        radius: 7,
        color: '#ffffff',
        weight: 3,
        fillColor: '#176ca4',
        fillOpacity: 1,
      }).addTo(map)
      userMarker.bindTooltip('Ваше приблизительное местоположение')
      map.setView([latitude, longitude], 13, { animate: false })
    },
    clearLocation() {
      userMarker?.remove()
      userMarker = null
    },
    retry() {
      tiles.redraw()
    },
    destroy() {
      clearTimeout(tileTimer)
      map.remove()
    },
  }
}
