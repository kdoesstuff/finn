// Runtime checks on everything the app reads from the network. The API is ours, but a response is
// still input: a shape the app does not expect is refused here, with the path that failed, rather
// than rendered half-broken.

import type {
  Change,
  DemoSession,
  Digest,
  Health,
  Item,
  Move,
  Pledge,
  RelatedFiling,
  Results,
  ResultsRow,
  Snapshot,
} from './types'
import { NETWORK_BUILD } from '../network/flag'
import { parseWhoToCall } from '../network/api'

export class ContractError extends Error {
  override name = 'ContractError'
  constructor(readonly path: string, expected: string) {
    super(`Response does not match the contract at ${path}: expected ${expected}.`)
  }
}

type Json = unknown

export function obj(value: Json, path: string): Record<string, Json> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ContractError(path, 'an object')
  }
  return value as Record<string, Json>
}

export function str(value: Json, path: string): string {
  if (typeof value !== 'string') throw new ContractError(path, 'a string')
  return value
}

export function bool(value: Json, path: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(path, 'true or false')
  return value
}

function num(value: Json, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new ContractError(path, 'a number')
  return value
}

export function int(value: Json, path: string, min: number, max: number): number {
  const n = num(value, path)
  if (!Number.isInteger(n) || n < min || n > max) {
    throw new ContractError(path, `a whole number from ${min} to ${max}`)
  }
  return n
}

/** ISO 8601 with an offset, as the contract promises (2026-11-06T22:06:58+05:30). */
function time(value: Json, path: string): string {
  const s = str(value, path)
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.test(s) || Number.isNaN(Date.parse(s))) {
    throw new ContractError(path, 'an ISO 8601 time with an offset')
  }
  return s
}

function nullable<T>(value: Json, path: string, each: (v: Json, p: string) => T): T | null {
  return value === null ? null : each(value, path)
}

/** A calendar date, 2026-09-30. */
function day(value: Json, path: string): string {
  const s = str(value, path)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || Number.isNaN(Date.parse(s))) throw new ContractError(path, 'a date')
  return s
}

export function arr<T>(value: Json, path: string, each: (v: Json, p: string) => T): T[] {
  if (!Array.isArray(value)) throw new ContractError(path, 'a list')
  return value.map((v, i) => each(v, `${path}[${i}]`))
}

function related(value: Json, path: string): RelatedFiling {
  const o = obj(value, path)
  return {
    id: str(o.id, `${path}.id`),
    ts: time(o.ts, `${path}.ts`),
    label: str(o.label, `${path}.label`),
    headline: str(o.headline, `${path}.headline`),
    url: str(o.url, `${path}.url`),
  }
}

function change(value: Json, path: string): Change {
  const o = obj(value, path)
  return {
    pct: nullable(o.pct, `${path}.pct`, num),
    note: str(o.note, `${path}.note`),
    margin_bps: nullable(o.margin_bps, `${path}.margin_bps`, num),
  }
}

function resultsRow(value: Json, path: string): ResultsRow {
  const o = obj(value, path)
  return {
    metric: str(o.metric, `${path}.metric`),
    value: num(o.value, `${path}.value`),
    margin: nullable(o.margin, `${path}.margin`, num),
    qoq: change(o.qoq, `${path}.qoq`),
    yoy: change(o.yoy, `${path}.yoy`),
  }
}

function results(value: Json, path: string): Results {
  const o = obj(value, path)
  return {
    quarter: str(o.quarter, `${path}.quarter`),
    period_end: day(o.period_end, `${path}.period_end`),
    basis: str(o.basis, `${path}.basis`),
    template: str(o.template, `${path}.template`),
    unit: str(o.unit, `${path}.unit`),
    rows: arr(o.rows, `${path}.rows`, resultsRow),
    notes: arr(o.notes, `${path}.notes`, str),
    source: str(o.source, `${path}.source`),
  }
}

function move(value: Json, path: string): Move {
  const o = obj(value, path)
  return {
    symbol: str(o.symbol, `${path}.symbol`),
    company: str(o.company, `${path}.company`),
    day: day(o.day, `${path}.day`),
    kind: str(o.kind, `${path}.kind`),
    value: num(o.value, `${path}.value`),
    threshold: num(o.threshold, `${path}.threshold`),
    sigma: nullable(o.sigma, `${path}.sigma`, num),
    fired_by: str(o.fired_by, `${path}.fired_by`),
    detail: str(o.detail, `${path}.detail`),
  }
}

function pledge(value: Json, path: string): Pledge {
  const o = obj(value, path)
  return {
    symbol: str(o.symbol, `${path}.symbol`),
    company: str(o.company, `${path}.company`),
    pct_of_promoter: num(o.pct_of_promoter, `${path}.pct_of_promoter`),
    promoter_stake_pct: num(o.promoter_stake_pct, `${path}.promoter_stake_pct`),
    as_of: day(o.as_of, `${path}.as_of`),
    published: time(o.published, `${path}.published`),
    change_pct_points: nullable(o.change_pct_points, `${path}.change_pct_points`, num),
  }
}

function item(value: Json, path: string): Item {
  const o = obj(value, path)
  return {
    id: str(o.id, `${path}.id`),
    symbol: str(o.symbol, `${path}.symbol`),
    company: str(o.company, `${path}.company`),
    ts: time(o.ts, `${path}.ts`),
    headline: str(o.headline, `${path}.headline`),
    label: str(o.label, `${path}.label`),
    url: str(o.url, `${path}.url`),
    category: str(o.category, `${path}.category`),
    subtype: str(o.subtype, `${path}.subtype`),
    role: str(o.role, `${path}.role`),
    action: str(o.action, `${path}.action`),
    detail_in_document: bool(o.detail_in_document, `${path}.detail_in_document`),
    tier: int(o.tier, `${path}.tier`, 1, 4),
    score: num(o.score, `${path}.score`),
    alert: bool(o.alert, `${path}.alert`),
    reasons: arr(o.reasons, `${path}.reasons`, str),
    related: arr(o.related, `${path}.related`, related),
    results: nullable(o.results, `${path}.results`, results),
    moves: arr(o.moves, `${path}.moves`, move),
    // --- Network stream: present only on the full edition ---
    // (only the full build reads it: in the core build this branch, and the parser, are dropped)
    ...(NETWORK_BUILD && o.who_to_call !== undefined
      ? { who_to_call: arr(o.who_to_call, `${path}.who_to_call`, parseWhoToCall) }
      : {}),
  }
}

function counts(value: Json, path: string): Record<string, number> {
  const o = obj(value, path)
  const out: Record<string, number> = {}
  for (const [kind, count] of Object.entries(o)) out[kind] = int(count, `${path}.${kind}`, 0, 1_000_000)
  return out
}

export function parseDigest(value: Json, path = 'digest'): Digest {
  const o = obj(value, path)
  const w = obj(o.window, `${path}.window`)
  const portfolio = obj(o.portfolio, `${path}.portfolio`)
  const routine = obj(o.routine, `${path}.routine`)
  return {
    window: {
      hours: int(w.hours, `${path}.window.hours`, 1, 744),
      from: time(w.from, `${path}.window.from`),
      to: time(w.to, `${path}.window.to`),
    },
    data_as_of: time(o.data_as_of, `${path}.data_as_of`),
    summary: str(o.summary, `${path}.summary`),
    portfolio: {
      holdings: int(portfolio.holdings, `${path}.portfolio.holdings`, 0, 10_000),
      pledges: arr(portfolio.pledges, `${path}.portfolio.pledges`, pledge),
    },
    attention: arr(o.attention, `${path}.attention`, item),
    worth: arr(o.worth, `${path}.worth`, item),
    routine: {
      count: int(routine.count, `${path}.routine.count`, 0, 1_000_000),
      by_kind: counts(routine.by_kind, `${path}.routine.by_kind`),
    },
    unexplained_moves: arr(o.unexplained_moves, `${path}.unexplained_moves`, move),
  }
}

export function parseSnapshot(value: Json): Snapshot {
  const o = obj(value, 'snapshot')
  if (o.snapshot !== true) throw new ContractError('snapshot.snapshot', 'true')
  return { ...parseDigest(o, 'snapshot'), snapshot: true, generated_at: time(o.generated_at, 'snapshot.generated_at') }
}

export function parseSession(value: Json): DemoSession {
  const o = obj(value, 'session')
  const investor = obj(o.investor, 'session.investor')
  const token = str(o.token, 'session.token')
  if (token === '') throw new ContractError('session.token', 'a non-empty token')
  return {
    token,
    expires_at: time(o.expires_at, 'session.expires_at'),
    investor: {
      name: str(investor.name, 'session.investor.name'),
      demo: bool(investor.demo, 'session.investor.demo'),
      network: bool(investor.network, 'session.investor.network'),
    },
  }
}

export function parseHealth(value: Json): Health {
  const o = obj(value, 'health')
  return {
    ok: bool(o.ok, 'health.ok'),
    db: bool(o.db, 'health.db'),
    data_as_of: str(o.data_as_of, 'health.data_as_of'),
    version: str(o.version, 'health.version'),
  }
}

/** The contract's error shape, or null when the body is something else (a proxy's page). */
export function parseErrorBody(value: Json): { code: string; message: string } | null {
  if (typeof value !== 'object' || value === null) return null
  const error = (value as Record<string, Json>).error
  if (typeof error !== 'object' || error === null) return null
  const { code, message } = error as Record<string, Json>
  if (typeof code !== 'string' || typeof message !== 'string') return null
  return { code, message }
}

// Shared with the other response parsers (api/pull.ts).
export { counts, item, num, time }
