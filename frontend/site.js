import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import 'lenis/dist/lenis.css'
import './styles/landing.css'
import './styles/materials.css'
import './styles/site-blocks.css'
import Alpine from '@alpinejs/csp'
import { registerContentUI } from './shared/content-ui.js'
import { installNavigation, syncMetadata } from './shared/navigation.js'
import { registerLandingUI } from './landing/menu.js'
import { initLanding, destroyLanding } from './landing/loader.js'
import './styles/landing-fallbacks.css'
import './styles/site.css'
import './customer.css'

const legacy = location.hash.match(/^#\/materials(?:\/([a-z0-9-]+))?\/?$/)
if (legacy)
  location.replace(
    (document.documentElement.dataset.demoBase || '/') + 'materials/' + (legacy[1] ? legacy[1] + '/' : ''),
  )

registerLandingUI(Alpine)
registerContentUI(Alpine)
window.Alpine = Alpine
Alpine.start()
document.documentElement.classList.add('js')
installNavigation({
  beforePage: (root) => destroyLanding(root),
  afterPage: (root) => initLanding(root),
})
initLanding(document.getElementById('main-content'))
syncMetadata()
