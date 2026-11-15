import type { Digest } from '../api/types'

export type Standing = 'need' | 'worth' | 'quiet'

export interface Holding {
  symbol: string
  standing: Standing
  move: boolean
  pledge: boolean
}

const RANK: Record<Standing, number> = { need: 0, worth: 1, quiet: 2 }

/**
 * Every holding and how loud it is today. With `portfolio.companies` the grid is the whole
 * portfolio; without it (an older API or saved copy), the companies the digest names, and a count
 * of the quiet rest.
 */
export function holdings(digest: Digest): { tiles: Holding[]; quietRest: number } {
  const need = new Set(digest.attention.map((i) => i.symbol))
  const worth = new Set(digest.worth.map((i) => i.symbol))
  const moves = new Set(digest.unexplained_moves.map((m) => m.symbol))
  const pledges = new Set(digest.portfolio.pledges.map((p) => p.symbol))
  const listed = digest.portfolio.companies?.map((c) => c.symbol)
  const symbols = listed ?? [...new Set([...need, ...worth, ...moves, ...pledges])].sort()
  const tiles = symbols.map((symbol) => ({
    symbol,
    standing: need.has(symbol) ? ('need' as const) : worth.has(symbol) ? ('worth' as const) : ('quiet' as const),
    move: moves.has(symbol),
    pledge: pledges.has(symbol),
  }))
  if (!listed) tiles.sort((a, b) => RANK[a.standing] - RANK[b.standing] || a.symbol.localeCompare(b.symbol))
  return { tiles, quietRest: listed ? 0 : Math.max(digest.portfolio.holdings - tiles.length, 0) }
}

const SAYS: Record<Standing, string> = { need: 'needs you', worth: 'worth knowing', quiet: 'quiet' }

function describe(h: Holding): string {
  return [SAYS[h.standing], h.move && 'a move without a filing', h.pledge && 'promoter pledge'].filter(Boolean).join(', ')
}

/** The portfolio at a glance: loud companies in ink, quiet ones faint. A tile narrows the page to it. */
export function Holdings({ digest, selected, onSelect }: { digest: Digest; selected: string | null; onSelect: (symbol: string | null) => void }) {
  const { tiles, quietRest } = holdings(digest)
  if (tiles.length === 0) return null
  return (
    <section className="holdings" aria-labelledby="holdings-heading">
      <div className="holdings__head">
        <h2 className="holdings__title" id="holdings-heading">
          Your portfolio today
        </h2>
        {selected && (
          <button type="button" className="holdings__all" onClick={() => onSelect(null)}>
            Show all
          </button>
        )}
      </div>
      <ul className="holdings__grid">
        {tiles.map((h) => (
          <li key={h.symbol}>
            <button
              type="button"
              className={`tile tile--${h.standing}${selected === h.symbol ? ' tile--selected' : ''}`}
              aria-pressed={selected === h.symbol}
              aria-label={`${h.symbol}: ${describe(h)}`}
              onClick={() => onSelect(selected === h.symbol ? null : h.symbol)}
            >
              <span className="tile__symbol">{h.symbol}</span>
              {(h.move || h.pledge) && (
                <span className="tile__marks" aria-hidden="true">
                  {h.move && <span className="tile__mark tile__mark--move" />}
                  {h.pledge && <span className="tile__mark tile__mark--pledge" />}
                </span>
              )}
            </button>
          </li>
        ))}
        {quietRest > 0 && <li className="holdings__rest">and {quietRest} quiet</li>}
      </ul>
      <p className="holdings__key" aria-hidden="true">
        <span className="tile-key tile-key--need" /> needs you <span className="tile-key tile-key--worth" /> worth knowing{' '}
        <span className="tile-key tile-key--quiet" /> quiet <span className="tile__mark tile__mark--move" /> move{' '}
        <span className="tile__mark tile__mark--pledge" /> pledge
      </p>
    </section>
  )
}

/** The digest narrowed to one company; the routine pile is not per company and stays as it is. */
export function forCompany(digest: Digest, symbol: string | null): Digest {
  if (!symbol) return digest
  const mine = <T extends { symbol: string }>(list: T[]) => list.filter((x) => x.symbol === symbol)
  return {
    ...digest,
    attention: mine(digest.attention),
    worth: mine(digest.worth),
    unexplained_moves: mine(digest.unexplained_moves),
    portfolio: { ...digest.portfolio, pledges: mine(digest.portfolio.pledges) },
  }
}
