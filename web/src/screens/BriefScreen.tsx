import { useEffect, useRef, useState } from 'react'
import type { Api } from '../api/client'
import { WINDOWS, type Digest, type WindowHours } from '../api/types'
import { AttentionCard, WorthLine } from '../brief/ItemEntry'
import { Routine } from '../brief/Routine'
import { Loading, RateLimited, SavedCopyBanner, Unavailable, Waiting } from '../brief/States'
import { Summary, windowPhrase } from '../brief/Summary'
import { useBrief } from '../brief/useBrief'
import { WindowSelector } from '../brief/WindowSelector'
import type { AppConfig } from '../config'
import { formatDay, formatStamp } from '../lib/time'
import { useNow } from '../lib/useNow'
import { Colophon, Wordmark } from './Chrome'

export function hoursFromSearch(search: string): WindowHours {
  const param = new URLSearchParams(search).get('window')
  return WINDOWS.find((w) => w.param === param)?.hours ?? 24
}

function searchFor(hours: WindowHours): string {
  const param = WINDOWS.find((w) => w.hours === hours)?.param ?? '24h'
  return param === '24h' ? '' : `?window=${param}`
}

interface Props {
  api: Api
  config: AppConfig
  navigate: (to: string) => void
  /** Move focus to the heading on arrival (after a navigation, not on a fresh page load). */
  focusHeading: boolean
}

export function BriefScreen({ api, config, navigate, focusHeading }: Props) {
  const [hours, setHours] = useState<WindowHours>(() => hoursFromSearch(window.location.search))
  const { outcome, pending, progress, startedAt, retry } = useBrief(api, hours)
  const now = useNow(30_000)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (focusHeading) heading.current?.focus()
  }, [focusHeading])

  const chooseWindow = (next: WindowHours) => {
    window.history.replaceState(window.history.state, '', `/brief${searchFor(next)}`)
    setHours(next)
  }

  const shown: Digest | null =
    outcome?.kind === 'live' ? outcome.digest : outcome?.kind === 'snapshot' ? outcome.snapshot : null
  const updating = pending && shown !== null
  const windowLabel = WINDOWS.find((w) => w.hours === hours)?.label ?? windowPhrase(hours)

  let body
  if (outcome === null || (pending && shown === null)) {
    body = <Loading progress={progress} startedAt={startedAt} />
  } else if (outcome.kind === 'rate_limited') {
    body = <RateLimited retryAt={outcome.retryAt} onRetry={retry} />
  } else if (outcome.kind === 'unavailable') {
    body = <Unavailable reason={outcome.reason} onRetry={retry} />
  } else {
    body = (
      <>
        {outcome.kind === 'snapshot' && !pending && (
          <SavedCopyBanner snapshot={outcome.snapshot} reason={outcome.reason} onRetry={retry} />
        )}
        <DigestView digest={outcome.kind === 'live' ? outcome.digest : outcome.snapshot} now={now} />
      </>
    )
  }

  return (
    <div className="page page--brief">
      <a className="skip-link" href="#brief">
        Skip to the brief
      </a>
      <header className="masthead">
        <div className="masthead__brand">
          <Wordmark onHome={() => navigate('/')} />
          <span className="tag">Demo portfolio</span>
        </div>
        <h1 className="masthead__date" tabIndex={-1} ref={heading}>
          <span className="visually-hidden">Brief for </span>
          {formatDay(now)}
        </h1>
        {shown && (
          <p className="masthead__asof">
            Data as of <time dateTime={shown.data_as_of}>{formatStamp(shown.data_as_of)}</time> IST
          </p>
        )}
        <WindowSelector
          hours={hours}
          onChange={chooseWindow}
          note={
            outcome?.kind === 'snapshot' && !pending
              ? `The saved copy covers ${windowPhrase(outcome.snapshot.window.hours)}; choosing a window asks FINN’s server again.`
              : null
          }
        />
        {updating && (
          <div className="masthead__updating">
            {progress === null ? (
              <p className="waiting__message" role="status" aria-live="polite">
                Fetching the last {windowLabel}.
              </p>
            ) : (
              <Waiting progress={progress} startedAt={startedAt} />
            )}
          </div>
        )}
      </header>
      <main id="brief" className={updating ? 'brief brief--updating' : 'brief'} aria-busy={pending}>
        {body}
      </main>
      <Colophon networkEnabled={config.networkEnabled} onHome={() => navigate('/')} />
    </div>
  )
}

function DigestView({ digest, now }: { digest: Digest; now: number }) {
  return (
    <>
      <Summary digest={digest} />
      {digest.attention.length > 0 && (
        <section className="section section--attention" aria-labelledby="attention-heading">
          <h2 className="section__title" id="attention-heading">
            Needs your attention <span className="section__count">{digest.attention.length}</span>
          </h2>
          <div className="cards">
            {digest.attention.map((item) => (
              <AttentionCard key={item.id} item={item} now={now} />
            ))}
          </div>
        </section>
      )}
      {digest.worth.length > 0 && (
        <section className="section section--worth" aria-labelledby="worth-heading">
          <h2 className="section__title" id="worth-heading">
            Worth knowing <span className="section__count">{digest.worth.length}</span>
          </h2>
          <div className="lines">
            {digest.worth.map((item) => (
              <WorthLine key={item.id} item={item} now={now} />
            ))}
          </div>
        </section>
      )}
      <Routine routine={digest.routine} />
    </>
  )
}
