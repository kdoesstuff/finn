// Company research (Pull): the shapes in docs/API.md, "Company research", and their runtime checks.
// An analysis this app cannot read is dropped (with a warning), never allowed to break the page:
// the numbers and filings are still worth showing.

import type { Item } from './types'
import { arr, bool, ContractError, counts, int, item, num, obj, str, time } from './validate'

type Json = unknown

export interface CompanyMatch {
  symbol: string
  name: string
  covered: boolean
}

export interface Companies {
  query: string
  companies: CompanyMatch[]
}

export interface Price {
  day: string
  close: number
  change_1d_pct: number | null
  change_1m_pct: number | null
  change_since_pct: number | null
  since: string
  volume: number
  avg_volume_20d: number | null
}

export interface Change {
  pct: number | null
  note: string
  margin_bps?: number
}

export interface CardRow {
  metric: string
  value: number
  margin?: number | null
  qoq: Change
  yoy: Change
}

export interface ResultsCard {
  template: string
  period_end: string
  basis: string
  unit: string
  rows: CardRow[]
  notes: string[]
  source: string
}

/** A quarter: revenue, EBITDA and PBT for most companies; NII, operating profit and provisions for banks. */
export interface QuarterRow {
  period_end: string
  pat: number
  source: string
  revenue?: number
  ebitda?: number
  ebitda_margin?: number | null
  pbt?: number
  pat_margin?: number | null
  nii?: number
  operating_profit?: number
  provisions?: number
}

export interface Results {
  template: 'standard' | 'bank'
  basis: string
  unit: string
  latest: ResultsCard
  quarters: QuarterRow[]
  notes: string[]
}

export interface Document {
  kind: string
  title: string
  period: string | null
  published: string | null
  url: string
  pages: number | null
}

export interface Source {
  kind: string
  title: string
  url: string
}

/** A sentence and the words of the source it rests on. */
export interface Cited {
  text: string
  quote: string
  page: number
  url: string
  topic?: string
}

export type Status = 'kept' | 'missed' | 'partly' | 'too_early' | 'not_measurable'

export type Evidence =
  | { kind: 'quote'; quote: string; page: number; url: string }
  | { kind: 'numbers'; metric: string; value: string; period_end: string; url: string }

export interface Promise_ {
  said_in: string
  quote: string
  page: number
  url: string
  metric: string
  target: string
  horizon: string
  status: Status
  evidence: Evidence | null
}

interface Built {
  sources: Source[]
  model: string
  generated_at: string | null
}

export interface Ledger extends Built {
  summary: string
  counts: Record<string, number>
  statements: Promise_[]
  gaps: string[]
}

export interface BusinessSnapshot extends Built {
  points: Cited[]
}

export interface BullBear extends Built {
  bull: Cited[]
  bear: Cited[]
}

export interface Company {
  symbol: string
  name: string
  isin: string | null
  industry: string | null
  data_as_of: string | null
  coverage: { level: 'deep' | 'basic'; reason: string | null; missing: string[] }
  price: Price | null
  results: Results | null
  filings: { days: number; items: Item[]; more: number; routine: { count: number; by_kind: Record<string, number> } }
  documents: Document[]
  analyses: { ledger: Ledger | null; snapshot: BusinessSnapshot | null; bull_bear: BullBear | null }
}

const STATUSES: readonly Status[] = ['kept', 'missed', 'partly', 'too_early', 'not_measurable']

function maybe<T>(value: Json, path: string, read: (v: Json, p: string) => T): T | null {
  return value === null || value === undefined ? null : read(value, path)
}

function link(value: Json, path: string): string {
  const s = str(value, path)
  if (!/^https:\/\//.test(s)) throw new ContractError(path, 'an https link')
  return s
}

function day(value: Json, path: string): string {
  const s = str(value, path)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new ContractError(path, 'a date (YYYY-MM-DD)')
  return s
}

function change(value: Json, path: string): Change {
  const o = obj(value, path)
  const out: Change = { pct: maybe(o.pct, `${path}.pct`, num), note: str(o.note, `${path}.note`) }
  if (o.margin_bps !== undefined) out.margin_bps = num(o.margin_bps, `${path}.margin_bps`)
  return out
}

function cardRow(value: Json, path: string): CardRow {
  const o = obj(value, path)
  const row: CardRow = {
    metric: str(o.metric, `${path}.metric`),
    value: num(o.value, `${path}.value`),
    qoq: change(o.qoq, `${path}.qoq`),
    yoy: change(o.yoy, `${path}.yoy`),
  }
  if (o.margin !== undefined) row.margin = maybe(o.margin, `${path}.margin`, num)
  return row
}

function card(value: Json, path: string): ResultsCard {
  const o = obj(value, path)
  return {
    template: str(o.template, `${path}.template`),
    period_end: day(o.period_end, `${path}.period_end`),
    basis: str(o.basis, `${path}.basis`),
    unit: str(o.unit, `${path}.unit`),
    rows: arr(o.rows, `${path}.rows`, cardRow),
    notes: arr(o.notes, `${path}.notes`, str),
    source: str(o.source, `${path}.source`),
  }
}

const QUARTER_NUMBERS = ['revenue', 'ebitda', 'pbt', 'nii', 'operating_profit', 'provisions'] as const
const QUARTER_MARGINS = ['ebitda_margin', 'pat_margin'] as const

function quarter(value: Json, path: string): QuarterRow {
  const o = obj(value, path)
  const q: QuarterRow = {
    period_end: day(o.period_end, `${path}.period_end`),
    pat: num(o.pat, `${path}.pat`),
    source: str(o.source, `${path}.source`),
  }
  for (const key of QUARTER_NUMBERS) if (o[key] !== undefined) q[key] = num(o[key], `${path}.${key}`)
  for (const key of QUARTER_MARGINS) if (o[key] !== undefined) q[key] = maybe(o[key], `${path}.${key}`, num)
  return q
}

function results(value: Json, path: string): Results {
  const o = obj(value, path)
  const template = str(o.template, `${path}.template`)
  if (template !== 'standard' && template !== 'bank') throw new ContractError(`${path}.template`, 'standard or bank')
  return {
    template,
    basis: str(o.basis, `${path}.basis`),
    unit: str(o.unit, `${path}.unit`),
    latest: card(o.latest, `${path}.latest`),
    quarters: arr(o.quarters, `${path}.quarters`, quarter),
    notes: arr(o.notes, `${path}.notes`, str),
  }
}

function price(value: Json, path: string): Price {
  const o = obj(value, path)
  return {
    day: day(o.day, `${path}.day`),
    close: num(o.close, `${path}.close`),
    change_1d_pct: maybe(o.change_1d_pct, `${path}.change_1d_pct`, num),
    change_1m_pct: maybe(o.change_1m_pct, `${path}.change_1m_pct`, num),
    change_since_pct: maybe(o.change_since_pct, `${path}.change_since_pct`, num),
    since: day(o.since, `${path}.since`),
    volume: num(o.volume, `${path}.volume`),
    avg_volume_20d: maybe(o.avg_volume_20d, `${path}.avg_volume_20d`, num),
  }
}

function document(value: Json, path: string): Document {
  const o = obj(value, path)
  return {
    kind: str(o.kind, `${path}.kind`),
    title: str(o.title, `${path}.title`),
    period: maybe(o.period, `${path}.period`, str),
    published: maybe(o.published, `${path}.published`, str),
    url: link(o.url, `${path}.url`),
    pages: maybe(o.pages, `${path}.pages`, num),
  }
}

function source(value: Json, path: string): Source {
  const o = obj(value, path)
  return { kind: str(o.kind, `${path}.kind`), title: str(o.title ?? '', `${path}.title`), url: link(o.url, `${path}.url`) }
}

function cited(value: Json, path: string): Cited {
  const o = obj(value, path)
  const c: Cited = {
    text: str(o.text, `${path}.text`),
    quote: str(o.quote, `${path}.quote`),
    page: int(o.page, `${path}.page`, 1, 100_000),
    url: link(o.url, `${path}.url`),
  }
  if (o.topic !== undefined) c.topic = str(o.topic, `${path}.topic`)
  return c
}

function evidence(value: Json, path: string): Evidence {
  const o = obj(value, path)
  if (o.kind === 'quote') {
    return { kind: 'quote', quote: str(o.quote, `${path}.quote`), page: int(o.page, `${path}.page`, 1, 100_000), url: link(o.url, `${path}.url`) }
  }
  if (o.kind === 'numbers') {
    return {
      kind: 'numbers',
      metric: str(o.metric, `${path}.metric`),
      value: str(o.value, `${path}.value`),
      period_end: day(o.period_end, `${path}.period_end`),
      url: link(o.url, `${path}.url`),
    }
  }
  throw new ContractError(`${path}.kind`, 'quote or numbers')
}

function promise(value: Json, path: string): Promise_ {
  const o = obj(value, path)
  const status = str(o.status, `${path}.status`) as Status
  if (!STATUSES.includes(status)) throw new ContractError(`${path}.status`, STATUSES.join(', '))
  return {
    said_in: day(o.said_in, `${path}.said_in`),
    quote: str(o.quote, `${path}.quote`),
    page: int(o.page, `${path}.page`, 1, 100_000),
    url: link(o.url, `${path}.url`),
    metric: str(o.metric, `${path}.metric`),
    target: str(o.target, `${path}.target`),
    horizon: str(o.horizon, `${path}.horizon`),
    status,
    evidence: maybe(o.evidence, `${path}.evidence`, evidence),
  }
}

function built(o: Record<string, Json>, path: string): Built {
  return {
    sources: arr(o.sources ?? [], `${path}.sources`, source),
    model: str(o.model ?? '', `${path}.model`),
    generated_at: maybe(o.generated_at, `${path}.generated_at`, time),
  }
}

function ledger(value: Json, path: string): Ledger {
  const o = obj(value, path)
  return {
    ...built(o, path),
    summary: str(o.summary, `${path}.summary`),
    counts: counts(o.counts ?? {}, `${path}.counts`),
    statements: arr(o.statements ?? [], `${path}.statements`, promise),
    gaps: arr(o.gaps ?? [], `${path}.gaps`, str),
  }
}

function businessSnapshot(value: Json, path: string): BusinessSnapshot {
  const o = obj(value, path)
  return { ...built(o, path), points: arr(o.points, `${path}.points`, cited) }
}

function bullBear(value: Json, path: string): BullBear {
  const o = obj(value, path)
  return { ...built(o, path), bull: arr(o.bull, `${path}.bull`, cited), bear: arr(o.bear, `${path}.bear`, cited) }
}

/** An analysis the app cannot read is left out, with a warning; the rest of the page stands. */
function lenient<T>(value: Json, path: string, read: (v: Json, p: string) => T): T | null {
  try {
    return maybe(value, path, read)
  } catch (error) {
    if (!(error instanceof ContractError)) throw error
    console.warn(`[finn] ${error.message}`)
    return null
  }
}

export function parseCompanies(value: Json, path = 'companies'): Companies {
  const o = obj(value, path)
  return {
    query: str(o.query, `${path}.query`),
    companies: arr(o.companies, `${path}.companies`, (v, p) => {
      const c = obj(v, p)
      return { symbol: str(c.symbol, `${p}.symbol`), name: str(c.name, `${p}.name`), covered: bool(c.covered, `${p}.covered`) }
    }),
  }
}

export function parseCompany(value: Json, path = 'company'): Company {
  const o = obj(value, path)
  const coverage = obj(o.coverage, `${path}.coverage`)
  const level = str(coverage.level, `${path}.coverage.level`)
  if (level !== 'deep' && level !== 'basic') throw new ContractError(`${path}.coverage.level`, 'deep or basic')
  const filings = obj(o.filings, `${path}.filings`)
  const routine = obj(filings.routine, `${path}.filings.routine`)
  const analyses = obj(o.analyses, `${path}.analyses`)
  return {
    symbol: str(o.symbol, `${path}.symbol`),
    name: str(o.name, `${path}.name`),
    isin: maybe(o.isin, `${path}.isin`, str),
    industry: maybe(o.industry, `${path}.industry`, str),
    data_as_of: maybe(o.data_as_of, `${path}.data_as_of`, time),
    coverage: {
      level,
      reason: maybe(coverage.reason, `${path}.coverage.reason`, str),
      missing: arr(coverage.missing, `${path}.coverage.missing`, str),
    },
    price: maybe(o.price, `${path}.price`, price),
    results: maybe(o.results, `${path}.results`, results),
    filings: {
      days: int(filings.days, `${path}.filings.days`, 1, 3650),
      items: arr(filings.items, `${path}.filings.items`, item),
      more: int(filings.more, `${path}.filings.more`, 0, 1_000_000),
      routine: {
        count: int(routine.count, `${path}.filings.routine.count`, 0, 1_000_000),
        by_kind: counts(routine.by_kind, `${path}.filings.routine.by_kind`),
      },
    },
    documents: arr(o.documents, `${path}.documents`, document),
    analyses: {
      ledger: lenient(analyses.ledger, `${path}.analyses.ledger`, ledger),
      snapshot: lenient(analyses.snapshot, `${path}.analyses.snapshot`, businessSnapshot),
      bull_bear: lenient(analyses.bull_bear, `${path}.analyses.bull_bear`, bullBear),
    },
  }
}
