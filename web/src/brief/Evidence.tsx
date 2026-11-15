import { documentKind, nseDocumentUrl } from '../lib/links'
import { formatClock, formatFull, formatRelative, formatShortDate, formatStamp } from '../lib/time'

/** The source document: a link only when it is an https document on NSE's archive. */
export function SourceLink({ url, company, label = 'Read the filing' }: { url: string; company: string; label?: string }) {
  const href = nseDocumentUrl(url)
  if (!href) {
    return (
      <span className="source source--unlinked">
        {url.trim() === '' ? (
          'No source document was given.'
        ) : (
          <>
            Source, not linked because it is not an NSE archive address: <span className="source__raw">{url}</span>
          </>
        )}
      </span>
    )
  }
  const kind = documentKind(href)
  return (
    <a className="action source" href={href} target="_blank" rel="noopener noreferrer">
      <span className="source__label">{label}</span>
      {kind && (
        <span className="source__kind" aria-hidden="true">
          {kind}
        </span>
      )}
      <span className="visually-hidden">{`${kind ? `, ${kind}` : ''}, ${company}, on NSE, opens in a new tab`}</span>
    </a>
  )
}

/** Relative and absolute Indian time, e.g. "9 days ago" and "6 Nov, 22:06". */
export function Stamp({ ts, now }: { ts: string; now: number }) {
  return (
    <p className="stamp">
      <time dateTime={ts} title={formatFull(ts)}>
        {formatRelative(ts, now)}
      </time>
      <span className="stamp__abs">{formatStamp(ts)}</span>
    </p>
  )
}

/** The ledger's date column: "6 Nov" over "22:06". */
export function DateColumn({ ts }: { ts: string }) {
  return (
    <p className="when">
      <time dateTime={ts} title={formatFull(ts)}>
        <span className="when__date">{formatShortDate(ts)}</span>
        <span className="when__clock">{formatClock(ts)}</span>
      </time>
    </p>
  )
}
