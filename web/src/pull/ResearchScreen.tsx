import { type MouseEvent, type ReactNode, type RefObject, useEffect, useId, useRef, useState } from 'react'
import { ApiError, isAbort, type Api, type Progress, UnreachableError } from '../api/client'
import type { Cited, Company, CompanyMatch, Evidence, Promise_, QuarterRow, Results, Status } from '../api/pull'
import { WorthLine } from '../brief/ItemEntry'
import { SourceLink } from '../brief/Evidence'
import { Waiting } from '../brief/States'
import type { AppConfig } from '../config'
import { routineKinds } from '../lib/labels'
import { formatStamp } from '../lib/time'
import { useNow } from '../lib/useNow'
import { Colophon, SectionNav, Wordmark } from '../screens/Chrome'
import { NETWORK_BUILD } from '../network/flag'
import { QuarterBars, StackBar } from '../charts/Charts'

interface Props {
  api: Api
  config: AppConfig
  navigate: (to: string) => void
  /** "/research" (search) or "/research/SYMBOL" (a company). */
  path: string
  focusHeading: boolean
}

export function symbolFromPath(path: string): string | null {
  const match = /^\/research\/([A-Za-z0-9&-]{1,20})\/?$/.exec(decodeURIComponent(path))
  return match?.[1] ? match[1].toUpperCase() : null
}

function failureText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return error.message
    if (error.status === 429) return 'Too many requests for a moment. Try again in a minute.'
    return error.message
  }
  if (error instanceof UnreachableError) return error.message
  return 'Something went wrong reading this page.'
}

/** A same-app link that navigates in place (and still opens in a new tab when asked). */
function InPlace({ to, navigate, className, children }: { to: string; navigate: (to: string) => void; className?: string; children: ReactNode }) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to)
  }
  return (
    <a className={className} href={to} onClick={onClick}>
      {children}
    </a>
  )
}

export function ResearchScreen({ api, config, navigate, path, focusHeading }: Props) {
  const symbol = symbolFromPath(path)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (focusHeading) heading.current?.focus()
  }, [focusHeading, symbol])

  return (
    <div className="page page--research">
      <a className="skip-link" href="#research">
        Skip to the research
      </a>
      <header className="masthead">
        <div className="masthead__brand">
          <Wordmark onHome={() => navigate('/')} />
          <span className="tag">Demo portfolio</span>
        </div>
        <SectionNav current="research" navigate={navigate} />
      </header>
      <main id="research" className="research">
        <Search api={api} navigate={navigate} heading={symbol ? null : heading} />
        {symbol && (
          <CompanyView key={symbol} api={api} symbol={symbol} navigate={navigate} heading={heading} network={NETWORK_BUILD && config.networkEnabled} />
        )}
      </main>
      <Colophon networkEnabled={config.networkEnabled} onHome={() => navigate('/')} />
    </div>
  )
}

function Search({ api, navigate, heading }: { api: Api; navigate: (to: string) => void; heading: RefObject<HTMLHeadingElement | null> | null }) {
  const inputId = useId()
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<CompanyMatch[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const submit = async () => {
    const q = query.trim()
    if (!q) return
    controller.current?.abort()
    const mine = new AbortController()
    controller.current = mine
    setBusy(true)
    setError(null)
    try {
      const result = await api.companies(q, { signal: mine.signal })
      setFound(result.companies)
      const exact = result.companies.find((c) => c.symbol === q.toUpperCase())
      if (exact && result.companies.length === 1) navigate(`/research/${exact.symbol}`)
    } catch (e) {
      if (!isAbort(e)) setError(failureText(e))
    } finally {
      if (controller.current === mine) setBusy(false)
    }
  }

  return (
    <section className="search" aria-labelledby="search-heading">
      {heading ? (
        <h1 className="research__title" id="search-heading" tabIndex={-1} ref={heading}>
          Research a company
        </h1>
      ) : (
        <h2 className="section__title" id="search-heading">
          Research another company
        </h2>
      )}
      {heading && (
        <p className="research__lede">
          Any NSE company: its prices and filings, and for the companies FINN covers, nine quarters of results and what
          management promised against what it delivered, every claim with its source.
        </p>
      )}
      <form className="search__form" role="search" onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}>
        <label className="search__label" htmlFor={inputId}>
          Company name or NSE symbol
        </label>
        <div className="search__row">
          <input
            id={inputId}
            className="search__input"
            type="search"
            value={query}
            maxLength={60}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button className="button" type="submit" disabled={busy}>
            Find
          </button>
        </div>
      </form>
      <div aria-live="polite">
        {error && <p className="note">{error}</p>}
        {found && found.length === 0 && <p className="note">No NSE company matches that.</p>}
        {found && found.length > 0 && (
          <ul className="matches" aria-label="Matches">
            {found.map((c) => (
              <li key={c.symbol} className="match">
                <InPlace className="match__link" to={`/research/${c.symbol}`} navigate={navigate}>
                  <span className="match__name">{c.name || c.symbol}</span> <span className="company__symbol">{c.symbol}</span>
                </InPlace>
                {c.covered && <span className="tag tag--small">Covered</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

type Load = { kind: 'loading'; progress: Progress | null; startedAt: number } | { kind: 'ready'; company: Company } | { kind: 'failed'; message: string }

function CompanyView({ api, symbol, navigate, heading, network }: { api: Api; symbol: string; navigate: (to: string) => void; heading: RefObject<HTMLHeadingElement | null>; network: boolean }) {
  const [load, setLoad] = useState<Load>(() => ({ kind: 'loading', progress: null, startedAt: Date.now() }))
  const [attempt, setAttempt] = useState(0)
  const now = useNow(60_000)

  useEffect(() => {
    // The view is keyed by symbol and a retry resets the state first, so it starts as "loading".
    const controller = new AbortController()
    api
      .company(symbol, {
        signal: controller.signal,
        onProgress: (progress) => setLoad((l) => (l.kind === 'loading' ? { ...l, progress } : l)),
      })
      .then((company) => {
        setLoad({ kind: 'ready', company })
        document.title = `${company.name}, FINN`
      })
      .catch((error: unknown) => {
        if (!isAbort(error)) setLoad({ kind: 'failed', message: failureText(error) })
      })
    return () => controller.abort()
  }, [api, symbol, attempt])

  if (load.kind === 'loading') {
    return (
      <div className="company company--loading" aria-busy="true">
        <h1 className="research__title" tabIndex={-1} ref={heading}>
          {symbol}
        </h1>
        <Waiting progress={load.progress} startedAt={load.startedAt} />
      </div>
    )
  }
  if (load.kind === 'failed') {
    return (
      <div className="company">
        <h1 className="research__title" tabIndex={-1} ref={heading}>
          {symbol}
        </h1>
        <p className="note">{load.message}</p>
        <button
          className="button"
          type="button"
          onClick={() => {
            setLoad({ kind: 'loading', progress: null, startedAt: Date.now() })
            setAttempt((n) => n + 1)
          }}
        >
          Try again
        </button>
      </div>
    )
  }
  const c = load.company
  return (
    <article className="company" aria-labelledby="company-heading">
      <header className="company__head">
        <h1 className="research__title" id="company-heading" tabIndex={-1} ref={heading}>
          {c.name} <span className="company__symbol">{c.symbol}</span>
        </h1>
        {c.industry && <p className="company__industry">{c.industry}</p>}
        {c.price && <PriceLine company={c} />}
        {c.data_as_of && (
          <p className="masthead__asof">
            Filings as of <time dateTime={c.data_as_of}>{formatStamp(c.data_as_of)}</time> IST
          </p>
        )}
        {/* --- Network: full edition only (the core build drops this branch) --- */}
        {NETWORK_BUILD && network && (
          <p className="company__network">
            <InPlace to={`/network?q=${encodeURIComponent(`Who can explain ${c.name}?`)}`} navigate={navigate}>
              Who in your network knows {c.name}?
            </InPlace>
          </p>
        )}
      </header>
      {c.coverage.missing.length > 0 && (
        <div className={c.coverage.level === 'basic' ? 'coverage coverage--basic' : 'coverage'}>
          {c.coverage.missing.map((m) => (
            <p key={m}>{m}</p>
          ))}
        </div>
      )}
      {c.analyses.ledger && <LedgerSection company={c} />}
      {c.results && <ResultsSection results={c.results} company={c.name} />}
      {c.analyses.snapshot && <CitedSection title="The business" points={c.analyses.snapshot.points} company={c.name} id="snapshot" />}
      {c.analyses.bull_bear && (
        <div className="cases">
          <CitedSection title="The bull case" points={c.analyses.bull_bear.bull} company={c.name} id="bull" />
          <CitedSection title="The bear case" points={c.analyses.bull_bear.bear} company={c.name} id="bear" />
        </div>
      )}
      <FilingsSection company={c} now={now} />
      {c.documents.length > 0 && (
        <section className="section" aria-labelledby="documents-heading">
          <h2 className="section__title" id="documents-heading">
            Documents read
          </h2>
          <ul className="documents">
            {c.documents.map((d) => (
              <li key={d.url}>
                <SourceLink url={d.url} company={c.name} label={d.title || d.kind} />
                {d.published && <span className="documents__date"> {d.published}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="research__back">
        <InPlace to="/research" navigate={navigate} className="action">
          Research another company
        </InPlace>
      </p>
    </article>
  )
}

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const crore = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function signedPct(value: number | null): string {
  if (value === null) return '–'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(1)}%`
}

function PriceLine({ company }: { company: Company }) {
  const p = company.price
  if (!p) return null
  const parts = [`₹${inr.format(p.close)} at the close on ${p.day}`]
  if (p.change_1d_pct !== null) parts.push(`${signedPct(p.change_1d_pct)} on the day`)
  if (p.change_1m_pct !== null) parts.push(`${signedPct(p.change_1m_pct)} in a month`)
  if (p.change_since_pct !== null) parts.push(`${signedPct(p.change_since_pct)} since ${p.since}`)
  return <p className="company__price">{parts.join(' · ')}</p>
}

const STATUS_LABEL: Record<Status, string> = {
  kept: 'Kept',
  missed: 'Missed',
  partly: 'Partly kept',
  too_early: 'Too early to tell',
  not_measurable: 'Not measurable',
}

function EvidenceLine({ evidence, company }: { evidence: Evidence | null; company: string }) {
  if (!evidence) return <p className="note">Nothing in the later filings measures this.</p>
  if (evidence.kind === 'numbers') {
    return (
      <p className="promise__evidence">
        Delivered: {evidence.metric}, {evidence.value} (quarter to {evidence.period_end}).{' '}
        <SourceLink url={evidence.url} company={company} label="The results filing" />
      </p>
    )
  }
  return (
    <div className="promise__evidence">
      <blockquote className="quote">{evidence.quote}</blockquote>
      <SourceLink url={evidence.url} company={company} label={`Later call, page ${evidence.page}`} />
    </div>
  )
}

function PromiseEntry({ promise, company }: { promise: Promise_; company: string }) {
  return (
    <li className={`promise promise--${promise.status}`}>
      <p className="promise__head">
        <span className="promise__status">{STATUS_LABEL[promise.status]}</span>
        <span className="promise__metric">
          {promise.metric}
          {promise.target ? `: ${promise.target}` : ''}
          {promise.horizon ? `, by ${promise.horizon}` : ''}
        </span>
      </p>
      <blockquote className="quote">{promise.quote}</blockquote>
      <SourceLink url={promise.url} company={company} label={`Call for the quarter to ${promise.said_in}, page ${promise.page}`} />
      <EvidenceLine evidence={promise.evidence} company={company} />
    </li>
  )
}

function LedgerSection({ company }: { company: Company }) {
  const ledger = company.analyses.ledger
  if (!ledger) return null
  return (
    <section className="section section--ledger" aria-labelledby="ledger-heading">
      <h2 className="section__title" id="ledger-heading">
        Promised and delivered
      </h2>
      <Scorecard counts={ledger.counts} />
      <p className="ledger__summary">{ledger.summary}</p>
      {ledger.statements.length > 0 && (
        <ol className="promises">
          {ledger.statements.map((s, i) => (
            <PromiseEntry key={`${s.url}-${s.page}-${i}`} promise={s} company={company.name} />
          ))}
        </ol>
      )}
      {ledger.gaps.map((g) => (
        <p key={g} className="note">
          {g}
        </p>
      ))}
      <Provenance generatedAt={ledger.generated_at} model={ledger.model} />
    </section>
  )
}

const SCORE_ORDER: Status[] = ['kept', 'partly', 'missed', 'too_early', 'not_measurable']

/** The ledger at a glance: one bar, then each verdict counted. */
function Scorecard({ counts }: { counts: Record<string, number> }) {
  const parts = SCORE_ORDER.map((status) => ({ key: status, count: counts[status] ?? 0, className: `score__${status}` }))
  if (parts.every((p) => p.count === 0)) return null
  return (
    <div className="scorecard">
      <StackBar parts={parts} />
      <ul className="scorecard__chips" aria-label="Promises by verdict">
        {parts
          .filter((p) => p.count > 0)
          .map((p) => (
            <li key={p.key} className={`chip chip--${p.key}`}>
              <span className="chip__count">{p.count}</span> {STATUS_LABEL[p.key].toLowerCase()}
            </li>
          ))}
      </ul>
    </div>
  )
}

function Provenance({ generatedAt, model }: { generatedAt: string | null; model: string }) {
  return (
    <p className="provenance">
      Read from the company’s own documents{model ? ` by ${model}` : ''}
      {generatedAt ? `, ${formatStamp(generatedAt)}` : ''}. Every quote above was checked against its source.
    </p>
  )
}

function CitedSection({ title, points, company, id }: { title: string; points: Cited[]; company: string; id: string }) {
  if (points.length === 0) return null
  return (
    <section className="section" aria-labelledby={`${id}-heading`}>
      <h2 className="section__title" id={`${id}-heading`}>
        {title}
      </h2>
      <ul className="points">
        {points.map((p, i) => (
          <li key={`${p.url}-${p.page}-${i}`} className="point">
            <p className="point__text">{p.text}</p>
            <blockquote className="quote">{p.quote}</blockquote>
            <SourceLink url={p.url} company={company} label={`Page ${p.page}`} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function money(value: number | undefined): string {
  return value === undefined ? '–' : crore.format(value)
}

function margin(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${value.toFixed(1)}%`
}

function quarterLabel(periodEnd: string): string {
  const [year, month] = periodEnd.split('-').map(Number)
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${names[(month ?? 1) - 1] ?? ''} ${year ?? ''}`
}

const STANDARD: { key: keyof QuarterRow; label: string; kind: 'money' | 'margin' }[] = [
  { key: 'revenue', label: 'Revenue', kind: 'money' },
  { key: 'ebitda', label: 'EBITDA', kind: 'money' },
  { key: 'ebitda_margin', label: 'EBITDA margin', kind: 'margin' },
  { key: 'pat', label: 'PAT', kind: 'money' },
  { key: 'pat_margin', label: 'PAT margin', kind: 'margin' },
]
const BANK: { key: keyof QuarterRow; label: string; kind: 'money' | 'margin' }[] = [
  { key: 'nii', label: 'Net interest income', kind: 'money' },
  { key: 'operating_profit', label: 'Operating profit', kind: 'money' },
  { key: 'provisions', label: 'Provisions', kind: 'money' },
  { key: 'pat', label: 'PAT', kind: 'money' },
]

function ResultsSection({ results, company }: { results: Results; company: string }) {
  const rows = results.template === 'bank' ? BANK : STANDARD
  const quarters = results.quarters
  return (
    <section className="section section--results" aria-labelledby="results-heading">
      <h2 className="section__title" id="results-heading">
        Results, quarter to {results.latest.period_end}
      </h2>
      <table className="figures">
        <caption className="visually-hidden">Latest quarter, {results.basis}, {results.unit}</caption>
        <thead>
          <tr>
            <th scope="col">{results.unit}</th>
            <th scope="col">Quarter</th>
            <th scope="col">QoQ</th>
            <th scope="col">YoY</th>
          </tr>
        </thead>
        <tbody>
          {results.latest.rows.map((r) => (
            <tr key={r.metric}>
              <th scope="row">{r.metric}</th>
              <td>{crore.format(r.value)}</td>
              <td>{r.qoq.pct === null ? r.qoq.note || '–' : signedPct(r.qoq.pct)}</td>
              <td>{r.yoy.pct === null ? r.yoy.note || '–' : signedPct(r.yoy.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="figures__basis">
        {results.basis === 'consolidated' ? 'Consolidated' : 'Standalone'}, from the company’s XBRL filing.{' '}
        <SourceLink url={results.latest.source} company={company} label="The filing" />
      </p>
      {quarters.length > 1 && <QuarterChart quarters={quarters} bank={results.template === 'bank'} unit={results.unit} />}
      {quarters.length > 1 && (
        <div className="figures__scroll" role="region" aria-label="Quarter by quarter" tabIndex={0}>
          <table className="figures figures--quarters">
            <caption className="visually-hidden">Quarter by quarter, {results.unit}</caption>
            <thead>
              <tr>
                <th scope="col">{results.unit}</th>
                {quarters.map((q) => (
                  <th scope="col" key={q.period_end}>
                    {quarterLabel(q.period_end)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  <th scope="row">{row.label}</th>
                  {quarters.map((q) => (
                    <td key={q.period_end}>
                      {row.kind === 'money' ? money(q[row.key] as number | undefined) : margin(q[row.key] as number | null | undefined)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {results.notes.map((n) => (
        <p key={n} className="note">
          {n}
        </p>
      ))}
    </section>
  )
}

/** Nine quarters as bars (revenue, or NII for a bank) with PAT inside each, oldest on the left. */
function QuarterChart({ quarters, bank, unit }: { quarters: QuarterRow[]; bank: boolean; unit: string }) {
  const ordered = [...quarters].sort((a, b) => a.period_end.localeCompare(b.period_end))
  const points = ordered.map((q) => ({
    label: q.period_end,
    value: (bank ? q.nii : q.revenue) ?? 0,
    inner: q.pat,
  }))
  if (points.every((p) => p.value <= 0)) return null
  const first = ordered[0]
  const last = ordered[ordered.length - 1]
  if (!first || !last) return null
  return (
    <figure className="quarter-chart">
      <QuarterBars points={points} />
      <figcaption className="quarter-chart__caption">
        <span>{quarterLabel(first.period_end)}</span>
        <span className="quarter-chart__key">
          <span className="quarter-chart__swatch quarter-chart__swatch--bar" aria-hidden="true" /> {bank ? 'Net interest income' : 'Revenue'}
          <span className="quarter-chart__swatch quarter-chart__swatch--inner" aria-hidden="true" /> PAT, {unit}
        </span>
        <span>{quarterLabel(last.period_end)}</span>
      </figcaption>
    </figure>
  )
}

function FilingsSection({ company, now }: { company: Company; now: number }) {
  const f = company.filings
  const routine = routineKinds(f.routine.by_kind)
  return (
    <section className="section section--worth" aria-labelledby="filings-heading">
      <h2 className="section__title" id="filings-heading">
        Filings in the last {f.days} days
      </h2>
      {f.items.length === 0 ? (
        <p className="note">Nothing beyond routine filings in the last {f.days} days.</p>
      ) : (
        <div className="lines">
          {f.items.map((item) => (
            <WorthLine key={item.id} item={item} now={now} />
          ))}
        </div>
      )}
      {f.more > 0 && <p className="note">{f.more} more of lesser weight not shown.</p>}
      {f.routine.count > 0 && (
        <p className="note">
          {f.routine.count} routine {f.routine.count === 1 ? 'filing' : 'filings'} set aside
          {routine.length > 0 ? `: ${routine.map((r) => r.phrase).join(', ')}` : ''}.
        </p>
      )}
    </section>
  )
}
