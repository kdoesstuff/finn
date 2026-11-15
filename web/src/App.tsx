import { useCallback, useEffect, useState } from 'react'
import type { Api } from './api/client'
import type { AppConfig } from './config'
import { BriefScreen } from './screens/BriefScreen'
import { Entry } from './screens/Entry'

interface Props {
  api: Api
  config: AppConfig
}

/** Two screens, two paths: "/" (the introduction) and "/brief". No router library is needed. */
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
    document.title = route.path === '/brief' ? 'Your brief, FINN' : 'FINN'
  }, [route.path])

  if (route.path === '/brief') {
    return <BriefScreen key="brief" api={api} config={config} navigate={navigate} focusHeading={route.navigated} />
  }
  return (
    <Entry key="entry" api={api} config={config} onStart={() => navigate('/brief')} focusHeading={route.navigated} />
  )
}
