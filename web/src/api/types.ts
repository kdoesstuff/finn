// The shapes in docs/API.md (contract v1), exactly. Change the contract first, then these.

export type ErrorCode =
  | 'bad_request'
  | 'unauthorised'
  | 'forbidden'
  | 'not_found'
  | 'rate_limited'
  | 'unavailable'

/** Every error the API sends; `code` is one of ErrorCode (kept a string so a new code is not a crash). */
export interface ApiErrorBody {
  error: { code: string; message: string }
}

export interface Investor {
  name: string
  demo: boolean
  network: boolean
}

/** POST /v1/session/demo */
export interface DemoSession {
  token: string
  expires_at: string
  investor: Investor
}

/** GET /health */
export interface Health {
  ok: boolean
  db: boolean
  data_as_of: string
  version: string
}

export interface RelatedFiling {
  id: string
  ts: string
  label: string
  headline: string
  url: string
}

/** A change against the previous quarter or the year-ago quarter: a %, or a note when a % would mislead. */
export interface Change {
  pct: number | null
  note: string
  margin_bps: number | null
}

export interface ResultsRow {
  metric: string
  value: number
  margin: number | null
  qoq: Change
  yoy: Change
}

/** A results filing's numbers, from its XBRL (₹ crore). */
export interface Results {
  quarter: string
  period_end: string
  basis: string
  template: string
  unit: string
  rows: ResultsRow[]
  notes: string[]
  source: string
}

/** A session's price move or volume crossing the investor's thresholds. */
export interface Move {
  symbol: string
  company: string
  day: string
  kind: string
  value: number
  threshold: number
  sigma: number | null
  fired_by: string
  detail: string
}

/** Promoter shares pledged at a holding, as NSE published them. */
export interface Pledge {
  symbol: string
  company: string
  pct_of_promoter: number
  promoter_stake_pct: number
  as_of: string
  published: string
  change_pct_points: number | null
}

/** One event: the filing that best says what happened, plus every other filing about it. */
export interface Item {
  id: string
  symbol: string
  company: string
  ts: string
  headline: string
  label: string
  url: string
  category: string
  subtype: string
  role: string
  action: string
  detail_in_document: boolean
  tier: number
  score: number
  alert: boolean
  reasons: string[]
  related: RelatedFiling[]
  /** Null except on a results filing whose quarter is stored. */
  results: Results | null
  /** Price and volume moves this filing may explain. */
  moves: Move[]
  /** --- Network stream --- Full edition only: who in the investor's network can explain this. */
  who_to_call?: WhoToCall[]
}

export interface DigestWindow {
  hours: number
  from: string
  to: string
}

/** GET /v1/digest?hours=N */
export interface Digest {
  window: DigestWindow
  data_as_of: string
  summary: string
  portfolio: { holdings: number; pledges: Pledge[] }
  attention: Item[]
  worth: Item[]
  routine: { count: number; by_kind: Record<string, number> }
  /** Moves in the window that no filing explains, newest first. */
  unexplained_moves: Move[]
}

/** web/public/snapshot.json: the digest shape plus these two fields. */
export interface Snapshot extends Digest {
  snapshot: true
  generated_at: string
}

/** The windows the brief offers, in hours (the contract allows 1 to 744). */
export const WINDOWS = [
  { hours: 24, label: '24 hours', param: '24h' },
  { hours: 72, label: '3 days', param: '3d' },
  { hours: 168, label: '7 days', param: '7d' },
] as const

export type WindowHours = (typeof WINDOWS)[number]['hours']

// --- Network stream: the full edition's Network layer (docs/API.md, "Network") ---

export interface WhoToCall {
  person_id: string
  name: string
  why: string
  degree: number
  via: string | null
  caution: string | null
}

export interface NetworkStep {
  from: string
  to: string
  to_id: string
  kind: string
  strength: number
  context: string
}

export interface NetworkAnswer {
  person_id: string
  name: string
  headline: string
  degree: number
  why: string
  how: string
  via: string | null
  caution: string | null
  path: NetworkStep[]
}

export interface NetworkPerson {
  id: string
  name: string
  headline: string
  location: string
  degree: number
  synthetic: boolean
  career: string[]
  schools: string[]
  how: string
  path: NetworkStep[]
  overlaps: string[]
  what_to_ask: string[]
}

export interface NetworkCompany {
  symbol: string
  company: string
  sector: string
  synthetic: boolean
  you_worked_there: string[]
  worked_there: NetworkAnswer[]
  best_placed: NetworkAnswer[]
}

export type NetworkKind = 'company' | 'person' | 'expertise' | 'reconnect' | 'help'

/** GET /v1/network/ask?q= */
export interface NetworkReply {
  question: string
  kind: NetworkKind
  title: string
  answers: NetworkAnswer[]
  company?: NetworkCompany
  person?: NetworkPerson
  examples?: string[]
}
