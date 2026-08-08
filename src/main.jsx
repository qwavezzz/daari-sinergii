import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import 'lenis/dist/lenis.css'
import App from './App.jsx'
import { applyRuntimePlatformClass } from './platform.js'
import './styles.css'

applyRuntimePlatformClass()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
