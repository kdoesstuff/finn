// --- Controls --- The investor's alert settings: which announcement types are alerts, and what
// counts as an unusual day's move or volume. The demo investor is read-only on FINN's server, so the
// settings live on this device (one localStorage key) and travel with each digest request
// (docs/API.md, GET /v1/digest). Storage can be missing, full or edited by hand: every read is
// checked field by field and falls back to the defaults; nothing here ever throws.

export type MoveRule = 'pct' | 'sigma' | 'either'

export interface AlertSettings {
  alerts: string[]
  movePct: number
  volumeMultiple: number
  moveRule: MoveRule
}

/** The categories the classifier knows (pipeline/finn/taxonomy.py), with the investor's words for them. */
export const CATEGORIES: readonly { id: string; label: string; hint: string }[] = [
  { id: 'results', label: 'Results', hint: 'quarterly and annual financial results' },
  { id: 'M&A', label: 'Mergers and acquisitions', hint: 'deals, takeovers, schemes of arrangement' },
  { id: 'management_change', label: 'Management changes', hint: 'CEO, CFO, directors, auditors' },
  { id: 'litigation', label: 'Litigation and regulators', hint: 'orders, penalties, disputes' },
  { id: 'pledging', label: 'Promoter pledges', hint: 'shares pledged or released' },
  { id: 'governance', label: 'Governance', hint: 'related-party deals, fraud, delays' },
  { id: 'insider_trading', label: 'Insider trades', hint: 'buying and selling by insiders' },
  { id: 'fund_raise', label: 'Fund raising', hint: 'QIPs, rights issues, debt raised' },
  { id: 'capex', label: 'Capacity and capex', hint: 'new plants, capacity added' },
  { id: 'credit_rating', label: 'Credit ratings', hint: 'upgrades and downgrades' },
  { id: 'dividend', label: 'Dividends', hint: 'declarations and record dates' },
  { id: 'bonus_split', label: 'Bonus and splits', hint: 'bonus issues, stock splits' },
  { id: 'press_release', label: 'Press releases', hint: "the company's own announcements" },
  { id: 'earnings_call', label: 'Earnings calls', hint: 'call notices, recordings, transcripts' },
  { id: 'investor_meetings', label: 'Investor meetings', hint: 'analyst and investor meets' },
  { id: 'postal_ballot', label: 'Postal ballots', hint: 'shareholder votes by post' },
  { id: 'agm_egm', label: 'AGMs and EGMs', hint: 'general meetings' },
]

const KNOWN = new Set(CATEGORIES.map((c) => c.id))

export const DEFAULT_SETTINGS: AlertSettings = {
  alerts: ['results', 'M&A', 'management_change', 'litigation', 'pledging'],
  movePct: 5,
  volumeMultiple: 2,
  moveRule: 'either',
}

// The same ranges as finn.prefs and the API.
export const MOVE_PCT = { min: 0.5, max: 30, step: 0.5 }
export const VOLUME_MULTIPLE = { min: 1.1, max: 10, step: 0.1 }
export const MOVE_RULES: readonly { id: MoveRule; label: string; hint: string }[] = [
  { id: 'either', label: 'Either', hint: 'beyond the percentage, or unusually large for this stock' },
  { id: 'pct', label: 'Percentage only', hint: 'a day’s move beyond the percentage you set' },
  { id: 'sigma', label: 'Unusual for this stock', hint: 'beyond three standard deviations of its own daily moves' },
]

export const STORAGE_KEY = 'finn.alerts.v1'

function inRange(value: unknown, min: number, max: number): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const rounded = Math.round(value * 100) / 100
  return rounded >= min && rounded <= max ? rounded : null
}

/** A stored value, checked field by field; anything wrong in a field falls back to that field's default. */
export function parseSettings(raw: unknown): AlertSettings {
  const o = typeof raw === 'object' && raw !== null && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {}
  const alerts = Array.isArray(o.alerts)
    ? [...new Set(o.alerts.filter((a): a is string => typeof a === 'string' && KNOWN.has(a)))]
    : DEFAULT_SETTINGS.alerts
  return {
    alerts,
    movePct: inRange(o.movePct, MOVE_PCT.min, MOVE_PCT.max) ?? DEFAULT_SETTINGS.movePct,
    volumeMultiple: inRange(o.volumeMultiple, VOLUME_MULTIPLE.min, VOLUME_MULTIPLE.max) ?? DEFAULT_SETTINGS.volumeMultiple,
    moveRule: MOVE_RULES.some((r) => r.id === o.moveRule) ? (o.moveRule as MoveRule) : DEFAULT_SETTINGS.moveRule,
  }
}

/** The saved settings, or null when the investor has never saved any (the server's defaults then apply). */
export function loadSettings(storage: Pick<Storage, 'getItem'> | null = safeStorage()): AlertSettings | null {
  try {
    const raw = storage?.getItem(STORAGE_KEY)
    return raw ? parseSettings(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

/** Saves the settings; false when the device would not keep them (private mode, full, blocked). */
export function saveSettings(s: AlertSettings, storage: Pick<Storage, 'setItem'> | null = safeStorage()): boolean {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(parseSettings(s)))
    return storage !== null
  } catch {
    return false
  }
}

export function clearSettings(storage: Pick<Storage, 'removeItem'> | null = safeStorage()): void {
  try {
    storage?.removeItem(STORAGE_KEY)
  } catch {
    // nothing to clear
  }
}

/** The digest's query parameters for these settings; none when there are no saved settings. */
export function settingsParams(s: AlertSettings | null): Record<string, string> {
  if (s === null) return {}
  return {
    alerts: s.alerts.join(','),
    move_pct: String(s.movePct),
    volume_multiple: String(s.volumeMultiple),
    move_rule: s.moveRule,
  }
}

export function safeStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}
