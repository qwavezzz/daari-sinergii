import { initHeroVideo } from './landing/hero.js'
import { applyRuntimePlatformClass } from '../src/platform.js'

const instances = new WeakMap()
let motionModule
const findLanding = (root) =>
  root?.matches?.('[data-page="landing"]') ? root : root?.querySelector?.('[data-page="landing"]')

export function initLanding(root = document) {
  const scope = findLanding(root)
  if (!scope) return
  if (instances.has(scope)) return instances.get(scope).ready
  applyRuntimePlatformClass()
  // Playback must not wait for the scene animation bundle.
  const instance = { stopVideo: initHeroVideo(scope), stopMotion: null, ready: null }
  instances.set(scope, instance)
  motionModule ||= import('./landing.js').catch((error) => {
    motionModule = null
    throw error
  })
  instance.ready = motionModule
    .then((module) => {
      if (instances.get(scope) === instance && scope.isConnected)
        instance.stopMotion = module.initLanding(scope)
    })
    .catch((error) => {
      // Server-rendered content and inline video remain available if motion fails to load.
      console.error('Не удалось загрузить анимацию страницы:', error)
    })
  return instance.ready
}

export function destroyLanding(root = document) {
  const scope = findLanding(root)
  const instance = scope && instances.get(scope)
  if (!instance) return
  instances.delete(scope)
  instance.stopMotion?.()
  instance.stopVideo()
}
