import { useId, useState } from 'react'
import type { Item } from '../api/types'
import { categoryLabel, detailInDocumentNote, shortCompany } from '../lib/labels'
import { formatFull, formatRelative, formatStamp } from '../lib/time'
import { DateColumn, SourceLink, Stamp } from './Evidence'

interface Props {
  item: Item
  now: number
}

/** "Needs your attention": a card with the whole story visible. */
export function AttentionCard({ item, now }: Props) {
  const headingId = useId()
  return (
    <article className="card" aria-labelledby={headingId}>
      <div className="card__head">
        <p className="kind">
          {categoryLabel(item.category)}
          {item.alert && <span className="kind__alert">On your alert list</span>}
        </p>
        <Stamp ts={item.ts} now={now} />
      </div>
      <h3 className="company" id={headingId}>
        {shortCompany(item.company)} <span className="company__symbol">{item.symbol}</span>
      </h3>
      <p className="headline">{item.headline}</p>
      {item.detail_in_document && <p className="note">{detailInDocumentNote(item.category)}</p>}
      <EntryActions item={item} />
    </article>
  )
}

/** "Worth knowing": a ledger line, date in the margin. */
export function WorthLine({ item, now }: Props) {
  const headingId = useId()
  return (
    <article className="line" aria-labelledby={headingId}>
      <DateColumn ts={item.ts} />
      <div className="line__body">
        <h3 className="line__company" id={headingId}>
          {shortCompany(item.company)} <span className="company__symbol">{item.symbol}</span>
        </h3>
        <p className="line__meta">
          {categoryLabel(item.category)}, {formatRelative(item.ts, now)}
          {item.alert && <span className="kind__alert">On your alert list</span>}
        </p>
        <p className="line__headline">{item.headline}</p>
        {item.detail_in_document && <p className="note">{detailInDocumentNote(item.category)}</p>}
        <EntryActions item={item} />
      </div>
    </article>
  )
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** The evidence and the reasons: the filing, why FINN ranked it, and the other filings about it. */
function EntryActions({ item }: { item: Item }) {
  const [whyOpen, setWhyOpen] = useState(false)
  const [relatedOpen, setRelatedOpen] = useState(false)
  const whyId = useId()
  const relatedId = useId()
  const company = shortCompany(item.company)

  return (
    <div className="actions">
      <div className="actions__row">
        <SourceLink url={item.url} company={company} />
        <button
          type="button"
          className="action toggle"
          aria-expanded={whyOpen}
          aria-controls={whyId}
          onClick={() => setWhyOpen((open) => !open)}
        >
          Why am I seeing this
        </button>
        {item.related.length > 0 && (
          <button
            type="button"
            className="action toggle"
            aria-expanded={relatedOpen}
            aria-controls={relatedId}
            onClick={() => setRelatedOpen((open) => !open)}
          >
            +{plural(item.related.length, 'related filing', 'related filings')}
          </button>
        )}
      </div>

      <div className="panel" id={whyId} hidden={!whyOpen}>
        {item.reasons.length > 0 ? (
          <ol className="reasons">
            {item.reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ol>
        ) : (
          <p className="reasons__none">FINN recorded no reason for this item.</p>
        )}
        <p className="panel__source">
          NSE’s label for this filing: <span className="panel__label">{item.label}</span>
        </p>
      </div>

      {item.related.length > 0 && (
        <div className="panel" id={relatedId} hidden={!relatedOpen}>
          <ul className="related">
            {item.related.map((filing) => (
              <li key={filing.id} className="related__item">
                <p className="related__headline">{filing.headline}</p>
                <p className="related__meta">
                  <time dateTime={filing.ts} title={formatFull(filing.ts)}>
                    {formatStamp(filing.ts)}
                  </time>
                  {filing.label !== filing.headline && <span className="related__label">{filing.label}</span>}
                </p>
                <SourceLink url={filing.url} company={company} label="Read this filing" />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
