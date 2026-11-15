// --- Controls --- "Tell me the moment", inside the app: the device remembers when the investor last
// opened the brief, and items published since then are marked new. No push notifications.

import type { Digest, Item } from '../api/types'
import { safeStorage } from './alerts'

export const LAST_SEEN_KEY = 'finn.lastSeen.v1'

/** When the brief was last opened on this device (epoch ms), or null on a first visit or bad storage. */
export function readLastSeen(storage: Pick<Storage, 'getItem'> | null = safeStorage()): number | null {
  try {
    const raw = storage?.getItem(LAST_SEEN_KEY)
    if (!raw) return null
    const ms = Number(raw)
    return Number.isFinite(ms) && ms > 0 ? ms : null
  } catch {
    return null
  }
}

export function writeLastSeen(ms: number, storage: Pick<Storage, 'setItem'> | null = safeStorage()): void {
  try {
    storage?.setItem(LAST_SEEN_KEY, String(Math.floor(ms)))
  } catch {
    // a device that will not remember just shows nothing as new next time
  }
}

/** The previous visit's time, read once per page load, and this visit recorded for next time. */
let previous: { value: number | null } | null = null
export function previousVisit(nowMs: number = Date.now()): number | null {
  if (previous === null) {
    previous = { value: readLastSeen() }
    writeLastSeen(nowMs)
  }
  return previous.value
}

/** For tests: forget the previous visit read at page load. */
export function resetPreviousVisit(): void {
  previous = null
}

export function isNew(item: Pick<Item, 'ts'>, lastSeenMs: number | null): boolean {
  return lastSeenMs !== null && Date.parse(item.ts) > lastSeenMs
}

/** The items published since the last visit, in the order the brief shows them (attention first). */
export function newItems(digest: Pick<Digest, 'attention' | 'worth'>, lastSeenMs: number | null): Item[] {
  if (lastSeenMs === null) return []
  return [...digest.attention, ...digest.worth].filter((i) => isNew(i, lastSeenMs))
}
