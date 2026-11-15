// --- Controls --- The brief's window: a quick choice (24 hours, 3 days, 7 days) or "since" a date
// the investor picks, up to now. The API takes whole hours, 1 to 744 (31 days), so a date becomes the
// hours from that day's midnight in India to now.

import { WINDOWS, type WindowHours } from '../api/types'

export type BriefWindow = { kind: 'preset'; hours: WindowHours } | { kind: 'since'; date: string }

export const MAX_HOURS = 744
const HOUR_MS = 3_600_000
const IST_OFFSET_MS = 330 * 60_000 // India keeps no daylight saving
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/

export const DEFAULT_WINDOW: BriefWindow = { kind: 'preset', hours: 24 }

/** Midnight in India at the start of a calendar date, as epoch ms; null for anything not a real date. */
export function istMidnight(date: string): number | null {
  const m = DATE.exec(date)
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const utc = Date.UTC(y, mo - 1, d)
  const back = new Date(utc)
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) return null
  return utc - IST_OFFSET_MS
}

/** The calendar date in India at `ms`: "2026-11-15". */
export function istDate(ms: number): string {
  return new Date(ms + IST_OFFSET_MS).toISOString().slice(0, 10)
}

/** The earliest date the API can serve in full from `now` (its midnight is at most 744 hours back). */
export function earliestDate(nowMs: number): string {
  const first = istDate(nowMs - MAX_HOURS * HOUR_MS)
  const midnight = istMidnight(first) ?? 0
  return midnight < nowMs - MAX_HOURS * HOUR_MS ? istDate(midnight + 24 * HOUR_MS) : first
}

/** Whether `date` can be a "since" date now: a real date, not in the future, within 31 days. */
export function validSince(date: string, nowMs: number): boolean {
  return istMidnight(date) !== null && date <= istDate(nowMs) && date >= earliestDate(nowMs)
}

/** The window in whole hours up to now, as the API takes it. */
export function hoursFor(w: BriefWindow, nowMs: number): number {
  if (w.kind === 'preset') return w.hours
  const start = istMidnight(w.date) ?? nowMs - 24 * HOUR_MS
  return Math.min(MAX_HOURS, Math.max(1, Math.ceil((nowMs - start) / HOUR_MS)))
}

/** `?since=2026-11-01` wins over `?window=3d`; anything unknown or out of range is the default. */
export function windowFromSearch(search: string, nowMs: number): BriefWindow {
  const params = new URLSearchParams(search)
  const since = params.get('since')
  if (since !== null && validSince(since, nowMs)) return { kind: 'since', date: since }
  const preset = WINDOWS.find((w) => w.param === params.get('window'))
  return preset ? { kind: 'preset', hours: preset.hours } : DEFAULT_WINDOW
}

export function searchFor(w: BriefWindow): string {
  if (w.kind === 'since') return `?since=${w.date}`
  const param = WINDOWS.find((o) => o.hours === w.hours)?.param ?? '24h'
  return param === '24h' ? '' : `?window=${param}`
}

/** "1 Nov" for a since window. */
export function sinceLabel(date: string): string {
  const midnight = istMidnight(date)
  if (midnight === null) return date
  return new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' }).format(
    new Date(midnight),
  )
}

/** "the last 24 hours", "since 1 Nov": how the brief names its window in a sentence. */
export function windowPhrase(w: BriefWindow): string {
  if (w.kind === 'since') return `since ${sinceLabel(w.date)}`
  return `from the last ${WINDOWS.find((o) => o.hours === w.hours)?.label ?? `${w.hours} hours`}`
}

export function sameWindow(a: BriefWindow, b: BriefWindow): boolean {
  return a.kind === 'since' ? b.kind === 'since' && a.date === b.date : b.kind === 'preset' && a.hours === b.hours
}
