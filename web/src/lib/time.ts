// Every time in FINN is shown in Indian Standard Time, whatever the device's own clock says.

const ZONE = 'Asia/Kolkata'
const LOCALE = 'en-IN'

function parts(iso: string | number, options: Intl.DateTimeFormatOptions): Record<string, string> {
  const out: Record<string, string> = {}
  for (const part of new Intl.DateTimeFormat(LOCALE, { timeZone: ZONE, ...options }).formatToParts(new Date(iso))) {
    out[part.type] = part.value
  }
  return out
}

/** "Sunday 15 November" */
export function formatDay(at: string | number): string {
  const p = parts(at, { weekday: 'long', day: 'numeric', month: 'long' })
  return `${p.weekday} ${p.day} ${p.month}`
}

/** "22:06" */
export function formatClock(at: string | number): string {
  const p = parts(at, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  return `${p.hour}:${p.minute}`
}

/** "6 Nov" */
export function formatShortDate(at: string | number): string {
  const p = parts(at, { day: 'numeric', month: 'short' })
  return `${p.day} ${p.month}`
}

/** "6 Nov, 22:06" */
export function formatStamp(at: string | number): string {
  return `${formatShortDate(at)}, ${formatClock(at)}`
}

/** "6 November 2026, 22:06 IST" */
export function formatFull(at: string | number): string {
  const p = parts(at, { day: 'numeric', month: 'long', year: 'numeric' })
  return `${p.day} ${p.month} ${p.year}, ${formatClock(at)} IST`
}

/** The calendar date in India, as a day number, for counting days between two times. */
function indianDayNumber(at: number): number {
  const p = parts(at, { year: 'numeric', month: '2-digit', day: '2-digit' })
  return Math.floor(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day)) / 86_400_000)
}

const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

/** "just now", "12 minutes ago", "3 hours ago", "yesterday", "9 days ago" (calendar days in India). */
export function formatRelative(iso: string, nowMs: number): string {
  const at = Date.parse(iso)
  const seconds = Math.round((nowMs - at) / 1000)
  if (seconds < 0) return 'just now'
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return relative.format(-minutes, 'minute')
  const days = indianDayNumber(nowMs) - indianDayNumber(at)
  if (days === 0) return relative.format(-Math.floor(minutes / 60), 'hour')
  return relative.format(-days, 'day')
}
