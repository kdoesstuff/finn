import type { Digest } from '../api/types'
import { StackBar } from '../charts/Charts'
import { formatStamp } from '../lib/time'

export function windowPhrase(hours: number): string {
  if (hours % 24 === 0 && hours >= 48) return `${hours / 24} days`
  return hours === 1 ? '1 hour' : `${hours} hours`
}

/**
 * What FINN read in the window and where each filing went. `filings_read` (when the API sends it)
 * also counts related filings folded into an item; without it the three piles are the total.
 */
export function filterCounts(digest: Digest) {
  const need = digest.attention.length
  const worth = digest.worth.length
  const aside = digest.routine.count
  const placed = need + worth + aside
  const read = Math.max(digest.filings_read ?? placed, placed)
  return { read, need, worth, aside, grouped: read - placed }
}

function jumpTo(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  target.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
}

function Pile({ count, label, tone, target }: { count: number; label: string; tone: string; target?: string }) {
  const body = (
    <>
      <span className={`filter__swatch filter__swatch--${tone}`} aria-hidden="true" />
      <span className="filter__count">{count}</span> {label}
    </>
  )
  return (
    <li className={count === 0 ? 'filter__pile filter__pile--none' : 'filter__pile'}>
      {count > 0 && target ? (
        <a
          className="filter__link"
          href={`#${target}`}
          onClick={(event) => {
            event.preventDefault()
            jumpTo(target)
          }}
        >
          {body}
        </a>
      ) : (
        <span className="filter__link">{body}</span>
      )}
    </li>
  )
}

/**
 * The lede, then the filter made visible: how many filings FINN read for the reader and where they
 * went, as one slim bar. Most of the bar is the pile set aside, which is the point.
 */
export function Summary({ digest, onPlay }: { digest: Digest; onPlay?: () => void }) {
  const holdings = digest.portfolio.holdings
  const quietAll = digest.attention.length === 0 && digest.worth.length === 0 && digest.routine.count === 0
  const cards = digest.attention.length + digest.unexplained_moves.length
  const f = filterCounts(digest)
  return (
    <div className="summary">
      <p className="summary__sentence">{digest.summary}</p>
      <div className="total-rule" aria-hidden="true" />
      <p className="summary__coverage">
        {holdings} {holdings === 1 ? 'holding' : 'holdings'},{' '}
        {[24, 72, 168].includes(digest.window.hours) ? (
          <>the {windowPhrase(digest.window.hours)}</>
        ) : (
          <>
            from <time dateTime={digest.window.from}>{formatStamp(digest.window.from)}</time>
          </>
        )}{' '}
        to <time dateTime={digest.window.to}>{formatStamp(digest.window.to)}</time> IST.
        {quietAll && ' No filings from your companies in this window.'}
      </p>
      {!quietAll && (
        <section className="filter" aria-labelledby="filter-heading">
          <h2 className="filter__title" id="filter-heading">
            FINN read {f.read} {f.read === 1 ? 'filing' : 'filings'} for you
          </h2>
          <StackBar
            parts={[
              { key: 'need', count: f.need, className: 'filter__bar--need' },
              { key: 'worth', count: f.worth, className: 'filter__bar--worth' },
              { key: 'grouped', count: f.grouped, className: 'filter__bar--grouped' },
              { key: 'aside', count: f.aside, className: 'filter__bar--aside' },
            ]}
          />
          <ul className="filter__piles">
            <Pile count={f.need} label={f.need === 1 ? 'needs you' : 'need you'} tone="need" target="attention-heading" />
            <Pile count={f.worth} label="worth knowing" tone="worth" target="worth-heading" />
            {f.grouped > 0 && <Pile count={f.grouped} label="filed alongside those" tone="grouped" />}
            <Pile count={f.aside} label="set aside" tone="aside" target="routine-heading" />
          </ul>
        </section>
      )}
      {cards > 0 && onPlay && (
        <button type="button" className="play" onClick={onPlay}>
          <svg className="play__icon" viewBox="0 0 16 16" width={14} height={14} aria-hidden="true" focusable="false">
            <path d="M4 2.5v11l9-5.5z" />
          </svg>
          Read in 30 seconds
          <span className="play__time">
            {' · '}
            {cards} {cards === 1 ? 'card' : 'cards'}
          </span>
        </button>
      )}
    </div>
  )
}
