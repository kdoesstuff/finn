import type { Change, Digest, Item, Move } from '../api/types'
import { changeText, moveValue } from '../brief/Numbers'
import { categoryLabel, shortCompany } from '../lib/labels'
import { formatShortDate } from '../lib/time'

/** One card of the story: a kind, a company, one big figure, one line, and where "Dig in" goes. */
export interface StoryCard {
  key: string
  kind: string
  company: string
  symbol: string
  figure: string
  tone: 'up' | 'down' | 'plain'
  figureNote: string
  line: string
  target: { kind: 'item'; id: string } | { kind: 'research'; symbol: string }
}

function tone(c: Change | undefined): 'up' | 'down' | 'plain' {
  if (!c || c.pct === null || c.pct === 0) return 'plain'
  return c.pct > 0 ? 'up' : 'down'
}

const crore = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

function itemCard(item: Item): StoryCard {
  const base = {
    key: `item-${item.id}`,
    kind: categoryLabel(item.category),
    company: shortCompany(item.company),
    symbol: item.symbol,
    line: item.headline,
    target: { kind: 'item', id: item.id } as const,
  }
  const top = item.results?.rows[0]
  if (item.results && top) {
    const pat = item.results.rows.find((r) => r.metric === 'PAT')
    return {
      ...base,
      figure: `₹${crore.format(top.value)} cr`,
      tone: tone(top.yoy),
      figureNote: `${top.metric}, ${changeText(top.yoy)} year on year${pat && pat !== top ? `; PAT ₹${crore.format(pat.value)} cr` : ''}`,
      line: `${item.results.quarter} results`,
    }
  }
  const [move] = item.moves
  if (move) {
    return { ...base, figure: moveValue(move), tone: move.value >= 0 ? 'up' : 'down', figureNote: `${formatShortDate(move.day)}, past your line` }
  }
  return { ...base, figure: categoryLabel(item.category), tone: 'plain', figureNote: item.alert ? 'On your alert list' : '' }
}

function moveCard(m: Move): StoryCard {
  return {
    key: `move-${m.symbol}-${m.day}-${m.kind}`,
    kind: 'Move without a filing',
    company: shortCompany(m.company),
    symbol: m.symbol,
    figure: moveValue(m),
    tone: m.value >= 0 ? 'up' : 'down',
    figureNote: formatShortDate(m.day),
    line: `${m.detail} No filing from the company explains it.`,
    target: { kind: 'research', symbol: m.symbol },
  }
}

/** The story: what needs attention first, then the moves no filing explains. */
export function storyCards(digest: Digest): StoryCard[] {
  return [...digest.attention.map(itemCard), ...digest.unexplained_moves.map(moveCard)]
}
