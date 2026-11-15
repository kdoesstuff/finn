import '@fontsource/castoro/latin-400.css'
import '@fontsource/castoro/latin-400-italic.css'
import '@fontsource/mukta/latin-400.css'
import '@fontsource/mukta/latin-600.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/brief.css'
import './styles/pull.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createApi } from './api/client'
import { App } from './App'
import { readConfig } from './config'
import { initMonitoring, reportError } from './monitoring'

const config = readConfig()
void initMonitoring(config.sentryDsn, __FINN_RELEASE__)

const api = createApi({ baseUrl: config.apiUrl })

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root element.')

// The app shell works offline once visited; the service worker caches nothing from the API.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch((error: unknown) => {
      reportError(error)
    })
  })
}

createRoot(root).render(
  <StrictMode>
    <App api={api} config={config} />
  </StrictMode>,
)
