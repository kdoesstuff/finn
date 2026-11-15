import type { Digest } from '../api/types'
import { formatStamp } from '../lib/time'

export function windowPhrase(hours: number): string {
  if (hours % 24 === 0 && hours >= 48) return `${hours / 24} days`
  return hours === 1 ? '1 hour' : `${hours} hours`
}

/**
 * The day's total: one sentence, closed with a bookkeeper's double rule, then what it covers.
 * A quiet day is this sentence alone, and it is a good answer.
 */
export function Summary({ digest }: { digest: Digest }) {
  const holdings = digest.portfolio.holdings
  const quietAll = digest.attention.length === 0 && digest.worth.length === 0 && digest.routine.count === 0
  return (
    <div className="summary">
      <p className="summary__sentence">{digest.summary}</p>
      <div className="total-rule" aria-hidden="true" />
      <p className="summary__coverage">
        {holdings} {holdings === 1 ? 'holding' : 'holdings'}, the {windowPhrase(digest.window.hours)} to{' '}
        <time dateTime={digest.window.to}>{formatStamp(digest.window.to)}</time> IST.
        {quietAll && ' No filings from your companies in this window.'}
      </p>
    </div>
  )
}
