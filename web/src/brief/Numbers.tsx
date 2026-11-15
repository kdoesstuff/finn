import type { Change, Move, Pledge, Results } from '../api/types'
import { shortCompany } from '../lib/labels'
import { formatShortDate } from '../lib/time'

const crore = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

/** "+11.4%", "−3.2%", or the note when a % would mislead ("turned positive"). */
export function changeText(c: Change): string {
  if (c.pct === null) return c.note === 'not available' || c.note === 'no base' ? '—' : c.note
  if (c.pct === 0) return '0.0%'
  return `${c.pct > 0 ? '+' : '−'}${Math.abs(c.pct).toFixed(1)}%`
}

function amount(value: number): string {
  return `${value < 0 ? '−' : ''}₹${crore.format(Math.abs(value))}`
}

/** A results filing's numbers, from its XBRL: the quarter, then each line with QoQ and YoY. */
export function ResultsTable({ results, company }: { results: Results; company: string }) {
  return (
    <figure className="results">
      <table className="results__table">
        <caption className="results__caption">
          {results.quarter}, {results.basis}, {results.unit}
        </caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="visually-hidden">Line</span>
            </th>
            <th scope="col">Quarter</th>
            <th scope="col">QoQ</th>
            <th scope="col">YoY</th>
          </tr>
        </thead>
        <tbody>
          {results.rows.map((row) => (
            <tr key={row.metric}>
              <th scope="row">{row.metric}</th>
              <td>
                {amount(row.value)}
                {row.margin !== null && <span className="results__margin"> {row.margin.toFixed(1)}%</span>}
              </td>
              <td>{changeText(row.qoq)}</td>
              <td>{changeText(row.yoy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <figcaption className="results__source">
        From {shortCompany(company)}’s XBRL filing.{' '}
        {results.notes.map((note) => (
          <span key={note} className="results__note">
            {note}.{' '}
          </span>
        ))}
      </figcaption>
    </figure>
  )
}

/** The moves a filing may explain, one line each. */
export function MovesNote({ moves }: { moves: Move[] }) {
  if (moves.length === 0) return null
  return (
    <ul className="moves" aria-label="Price and volume moves around this filing">
      {moves.map((m) => (
        <li key={`${m.day}-${m.kind}`} className="moves__item">
          {formatShortDate(m.day)}: {m.detail}
        </li>
      ))}
    </ul>
  )
}

/** "Moves without a filing": the window's moves no filing explains. */
export function UnexplainedMoves({ moves }: { moves: Move[] }) {
  if (moves.length === 0) return null
  return (
    <section className="section section--moves" aria-labelledby="moves-heading">
      <h2 className="section__title" id="moves-heading">
        Moves without a filing <span className="section__count">{moves.length}</span>
      </h2>
      <ul className="lines moves-list">
        {moves.map((m) => (
          <li key={`${m.symbol}-${m.day}-${m.kind}`} className="moves-list__item">
            <p className="line__company">
              {shortCompany(m.company)} <span className="company__symbol">{m.symbol}</span>
            </p>
            <p className="line__headline">
              {formatShortDate(m.day)}: {m.detail}
            </p>
          </li>
        ))}
      </ul>
      <p className="note">No filing from the company explains these. Worth a look before the market does.</p>
    </section>
  )
}

/** Promoter pledges on the holdings, as NSE published them. */
export function Pledges({ pledges }: { pledges: Pledge[] }) {
  const [first] = pledges
  if (first === undefined) return null
  return (
    <section className="section section--pledges" aria-labelledby="pledges-heading">
      <h2 className="section__title" id="pledges-heading">
        Promoter pledges <span className="section__count">{pledges.length}</span>
      </h2>
      <ul className="pledges">
        {pledges.map((p) => (
          <li key={p.symbol} className="pledges__item">
            <span className="line__company">
              {shortCompany(p.company)} <span className="company__symbol">{p.symbol}</span>
            </span>{' '}
            {p.pct_of_promoter.toFixed(2)}% of the promoters’ {p.promoter_stake_pct.toFixed(2)}% stake is pledged
            {p.change_pct_points !== null && p.change_pct_points !== 0 && (
              <>
                , {p.change_pct_points > 0 ? 'up' : 'down'} {Math.abs(p.change_pct_points).toFixed(2)} points since
                the previous disclosure
              </>
            )}
            .
          </li>
        ))}
      </ul>
      <p className="note">
        As published by NSE on {formatShortDate(first.published)}, for shareholding at {formatShortDate(first.as_of)}.
      </p>
    </section>
  )
}
