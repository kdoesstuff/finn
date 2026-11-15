import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Api } from '../api/client'
import type { Digest, Item } from '../api/types'
import { AttentionCard, itemAnchor, WorthLine } from '../brief/ItemEntry'
import { Pledges, UnexplainedMoves } from '../brief/Numbers'
import { Routine } from '../brief/Routine'
import { Loading, RateLimited, SavedCopyBanner, Unavailable, Waiting } from '../brief/States'
import { Summary, windowPhrase } from '../brief/Summary'
import { forCompany, Holdings } from '../brief/Holdings'
import { useBrief } from '../brief/useBrief'
import { storyCards, type StoryCard } from '../story/cards'
import { Story } from '../story/Story'
import { WindowSelector } from '../brief/WindowSelector'
import type { AppConfig } from '../config'
import { formatDay, formatStamp } from '../lib/time'
import { useNow } from '../lib/useNow'
import { Colophon, SectionNav, Wordmark } from './Chrome'
import { NETWORK_BUILD } from '../network/flag'
// --- Controls: the window (quick choices or "since" a date), alert settings, new since last visit ---
import { AlertSettingsSheet } from '../settings/AlertSettingsSheet'
import { clearSettings, loadSettings, saveSettings, settingsParams, type AlertSettings } from '../settings/alerts'
import { isNew, newItems, previousVisit } from '../settings/lastSeen'
import { hoursFor, sameWindow, searchFor, windowFromSearch, windowPhrase as phraseFor, type BriefWindow } from '../settings/window'

interface Props {
  api: Api
  config: AppConfig
  navigate: (to: string) => void
  /** Move focus to the heading on arrival (after a navigation, not on a fresh page load). */
  focusHeading: boolean
}

export function BriefScreen({ api, config, navigate, focusHeading }: Props) {
  // --- Controls ---
  const [view, setView] = useState(() => {
    const at = Date.now()
    const w = windowFromSearch(window.location.search, at)
    return { window: w, hours: hoursFor(w, at) }
  })
  const hours = view.hours
  const [settings, setSettings] = useState<AlertSettings | null>(() => loadSettings())
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [persistent, setPersistent] = useState(true)
  const [lastVisit] = useState(() => previousVisit())
  const { outcome, pending, progress, startedAt, retry } = useBrief(api, hours, settingsParams(settings))
  const now = useNow(30_000)
  const heading = useRef<HTMLHeadingElement>(null)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (focusHeading) heading.current?.focus()
  }, [focusHeading])

  const chooseWindow = (next: BriefWindow) => {
    if (sameWindow(next, view.window)) return
    window.history.replaceState(window.history.state, '', `/brief${searchFor(next)}`)
    setView({ window: next, hours: hoursFor(next, Date.now()) })
  }

  const shown: Digest | null =
    outcome?.kind === 'live' ? outcome.digest : outcome?.kind === 'snapshot' ? outcome.snapshot : null
  const updating = pending && shown !== null
  const windowLabel = phraseFor(view.window)

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
        <DigestView
          digest={outcome.kind === 'live' ? outcome.digest : outcome.snapshot}
          now={now}
          lastVisit={lastVisit}
          onPlay={() => setPlaying(true)}
        />
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
          {/* --- Network stream: full edition only --- */}
          {NETWORK_BUILD && config.networkEnabled && (
            <a
              className="action masthead__nav"
              href="/network"
              onClick={(event) => {
                event.preventDefault()
                navigate('/network')
              }}
            >
              Your network
            </a>
          )}
        </div>
        <SectionNav current="brief" navigate={navigate} />
        <h1 className="masthead__date" tabIndex={-1} ref={heading}>
          <span className="visually-hidden">Brief for </span>
          {formatDay(now)}
        </h1>
        {/* --- Controls: the window in plain words --- */}
        <p className="masthead__window">Filings {windowLabel}</p>
        {shown && (
          <p className="masthead__asof">
            Data as of <time dateTime={shown.data_as_of}>{formatStamp(shown.data_as_of)}</time> IST
          </p>
        )}
        <WindowSelector
          value={view.window}
          onChange={chooseWindow}
          nowMs={now}
          note={
            outcome?.kind === 'snapshot' && !pending
              ? `The saved copy covers ${windowPhrase(outcome.snapshot.window.hours)}; choosing a window asks FINN’s server again.`
              : null
          }
        />
        {/* --- Controls: the investor's alert settings --- */}
        <p className="masthead__alerts">
          <button className="action" type="button" aria-haspopup="dialog" onClick={() => setSettingsOpen(true)}>
            {settings ? 'Your alerts (custom)' : 'Your alerts'}
          </button>
        </p>
        {settingsOpen && (
          <AlertSettingsSheet
            current={settings}
            persistent={persistent}
            onClose={() => setSettingsOpen(false)}
            onSave={(next) => {
              setPersistent(saveSettings(next))
              setSettings(next)
              setSettingsOpen(false)
            }}
            onReset={() => {
              clearSettings()
              setSettings(null)
              setSettingsOpen(false)
            }}
          />
        )}
        {updating && (
          <div className="masthead__updating">
            {progress === null ? (
              <p className="waiting__message" role="status" aria-live="polite">
                Fetching filings {windowLabel}.
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
      {playing && shown && (
        <Story
          cards={storyCards(shown)}
          onClose={() => {
            setPlaying(false)
            requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.play')?.focus())
          }}
          onDigIn={(card: StoryCard) => {
            setPlaying(false)
            if (card.target.kind === 'research') {
              navigate(`/research/${card.target.symbol}`)
              return
            }
            const id = itemAnchor(card.target.id)
            requestAnimationFrame(() => {
              const target = document.getElementById(id)
              target?.scrollIntoView({ block: 'start' })
              target?.focus({ preventScroll: true })
            })
          }}
        />
      )}
    </div>
  )
}

function DigestView({
  digest,
  now,
  lastVisit,
  onPlay,
}: {
  digest: Digest
  now: number
  lastVisit: number | null
  onPlay: () => void
}) {
  // --- Controls: what is new since the investor last opened the brief ---
  const fresh = newItems(digest, lastVisit)
  useEffect(() => {
    const base = 'Your brief, FINN'
    document.title = fresh.length > 0 ? `(${fresh.length}) ${base}` : base
    return () => {
      document.title = document.title.replace(/^\(\d+\) /, '')
    }
  }, [fresh.length])
  // --- Design: the front page, optionally narrowed to one holding ---
  const [only, setOnly] = useState<string | null>(null)
  const view = forCompany(digest, only)
  const empty =
    only !== null &&
    view.attention.length + view.worth.length + view.unexplained_moves.length + view.portfolio.pledges.length === 0
  return (
    <>
      <Summary digest={digest} onPlay={onPlay} />
      {fresh.length > 0 && <NewSince items={fresh} lastVisit={lastVisit} />}
      <Holdings digest={digest} selected={only} onSelect={setOnly} />
      {only && (
        <p className="front__only" role="status">
          {empty ? `Nothing from ${only} in this window. Quiet is good.` : `Showing ${only} only.`}
        </p>
      )}
      <div className="front">
        {view.attention.length > 0 && (
          <section className="section section--attention front__lead" aria-labelledby="attention-heading">
            <h2 className="section__title" id="attention-heading">
              Needs your attention <span className="section__count">{view.attention.length}</span>
            </h2>
            <div className="cards">
              {view.attention.map((item) => (
                <NewMark key={item.id} item={item} lastVisit={lastVisit}>
                  <AttentionCard item={item} now={now} />
                </NewMark>
              ))}
            </div>
          </section>
        )}
        {(view.unexplained_moves.length > 0 || view.portfolio.pledges.length > 0) && (
          <aside className="front__side" aria-label="Moves and pledges">
            <UnexplainedMoves moves={view.unexplained_moves} />
            <Pledges pledges={view.portfolio.pledges} />
          </aside>
        )}
        {view.worth.length > 0 && (
          <section className="section section--worth front__worth" aria-labelledby="worth-heading">
            <h2 className="section__title" id="worth-heading">
              Worth knowing <span className="section__count">{view.worth.length}</span>
            </h2>
            <div className="lines">
              {view.worth.map((item) => (
                <NewMark key={item.id} item={item} lastVisit={lastVisit}>
                  <WorthLine item={item} now={now} />
                </NewMark>
              ))}
            </div>
          </section>
        )}
        {!only && (
          <div className="front__routine">
            <Routine routine={digest.routine} />
          </div>
        )}
      </div>
    </>
  )
}

// --- Controls: "new since you last looked" ---

function NewSince({ items, lastVisit }: { items: Item[]; lastVisit: number | null }) {
  const first = items[0]
  if (!first || lastVisit === null) return null
  return (
    <p className="new-since" role="status">
      <a href={`#${itemAnchor(first.id)}`}>
        {items.length} new since you last looked
      </a>{' '}
      <span className="new-since__when">({formatStamp(new Date(lastVisit).toISOString())} IST)</span>
    </p>
  )
}

function NewMark({ item, lastVisit, children }: { item: Item; lastVisit: number | null; children: ReactNode }) {
  const fresh = isNew(item, lastVisit)
  return (
    <div className={fresh ? 'seen-mark seen-mark--new' : 'seen-mark'}>
      {fresh && <span className="badge badge--new">New</span>}
      {children}
    </div>
  )
}
