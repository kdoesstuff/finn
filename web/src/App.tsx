import { useCallback, useEffect, useState } from 'react'
import type { Api } from './api/client'
import type { AppConfig } from './config'
import { ResearchScreen } from './pull/ResearchScreen'
import { BriefScreen } from './screens/BriefScreen'
import { Entry } from './screens/Entry'
// --- Network stream: the full edition's network screen; dropped from the core build ---
import { NETWORK_BUILD } from './network/flag'
import { NetworkScreen } from './network/NetworkScreen'

interface Props {
  api: Api
  config: AppConfig
}

/** Three screens: "/" (the introduction), "/brief" and "/research[/SYMBOL]". No router library is needed. */
export function App({ api, config }: Props) {
  const [route, setRoute] = useState(() => ({ path: window.location.pathname, navigated: false }))

  useEffect(() => {
    const onPop = () => setRoute({ path: window.location.pathname, navigated: true })
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string) => {
    window.history.pushState(null, '', to)
    window.scrollTo(0, 0)
    setRoute({ path: new URL(to, window.location.origin).pathname, navigated: true })
  }, [])

  useEffect(() => {
    document.title = route.path === '/brief'
      ? 'Your brief, FINN'
      : route.path.startsWith('/research')
        ? 'Research, FINN'
        : route.path === '/network'
          ? 'Your network, FINN'
          : 'FINN'
  }, [route.path])

  if (route.path === '/research' || route.path.startsWith('/research/')) {
    return (
      <ResearchScreen key="research" api={api} config={config} navigate={navigate} path={route.path} focusHeading={route.navigated} />
    )
  }

  // --- Network stream ---
  if (NETWORK_BUILD && config.networkEnabled && route.path === '/network') {
    return <NetworkScreen key="network" api={api} config={config} navigate={navigate} focusHeading={route.navigated} />
  }

  if (route.path === '/brief') {
    return <BriefScreen key="brief" api={api} config={config} navigate={navigate} focusHeading={route.navigated} />
  }
  return (
    <Entry key="entry" api={api} config={config} onStart={() => navigate('/brief')} focusHeading={route.navigated} />
  )
}
