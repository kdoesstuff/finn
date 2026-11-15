import { useEffect, useRef } from 'react'
import type { Api } from '../api/client'
import type { AppConfig } from '../config'
import { Colophon } from './Chrome'

interface Props {
  api: Api
  config: AppConfig
  onStart: () => void
  focusHeading: boolean
}

/** One calm screen: what FINN is, that this is a demo, and one way in. */
export function Entry({ api, config, onStart, focusHeading }: Props) {
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    // The free server sleeps when idle. Knock while the reader reads, so it is awake by the tap.
    api.prewarm()
  }, [api])

  useEffect(() => {
    if (focusHeading) heading.current?.focus()
  }, [focusHeading])

  return (
    <div className="page page--entry">
      <main className="entry">
        <h1 className="entry__mark" tabIndex={-1} ref={heading}>
          FINN
        </h1>
        <div className="total-rule total-rule--mark" aria-hidden="true" />
        <p className="entry__lede">What changed across your portfolio, and why it matters.</p>
        <div className="entry__about">
          <p>
            FINN reads every filing your companies make on NSE and keeps the few that bear on management, governance
            or the business. Each item says why it was chosen and links to the filing it came from.
          </p>
        </div>
        <button type="button" className="button button--primary" onClick={onStart}>
          Open today’s brief
        </button>
        <p className="entry__demo">
          This is a demo portfolio of 18 NSE companies. The companies and their filings are real; the holdings are
          fictional. Read-only, no sign-up, nothing saved.
        </p>
      </main>
      <Colophon networkEnabled={config.networkEnabled} />
    </div>
  )
}
