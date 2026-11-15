// --- Controls --- window ("since" a date), alert settings on the device, and "new since you last looked".
import { afterEach, describe, expect, it } from 'vitest'
import { asianPaints, elgiResults, liveDigest, NOW } from '../test/fixtures/contract'
import {
  DEFAULT_SETTINGS,
  STORAGE_KEY,
  clearSettings,
  loadSettings,
  parseSettings,
  saveSettings,
  settingsParams,
} from './alerts'
import { LAST_SEEN_KEY, isNew, newItems, previousVisit, readLastSeen, resetPreviousVisit } from './lastSeen'
import {
  MAX_HOURS,
  earliestDate,
  hoursFor,
  istDate,
  istMidnight,
  searchFor,
  sinceLabel,
  validSince,
  windowFromSearch,
  windowPhrase,
} from './window'

const HOUR = 3_600_000

function memoryStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial))
  return {
    store,
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  }
}

const throwing = {
  getItem: () => {
    throw new Error('SecurityError')
  },
  setItem: () => {
    throw new Error('QuotaExceededError')
  },
  removeItem: () => {
    throw new Error('SecurityError')
  },
}

afterEach(() => {
  window.localStorage.clear()
  resetPreviousVisit()
})

describe('the window: since a date, up to now', () => {
  // NOW is 15 Nov 2026, 15:20 IST.
  it('turns a date into whole hours from its midnight in India to now', () => {
    expect(istMidnight('2026-11-01')).toBe(Date.parse('2026-11-01T00:00:00+05:30'))
    expect(hoursFor({ kind: 'since', date: '2026-11-01' }, NOW)).toBe(14 * 24 + 16) // 14 days and 15h20m, rounded up
    expect(hoursFor({ kind: 'since', date: '2026-11-15' }, NOW)).toBe(16)
    expect(hoursFor({ kind: 'preset', hours: 72 }, NOW)).toBe(72)
  })

  it('counts at least one hour just after midnight', () => {
    const justAfter = Date.parse('2026-11-15T00:00:30+05:30')
    expect(hoursFor({ kind: 'since', date: '2026-11-15' }, justAfter)).toBe(1)
  })

  it('reads back 31 days at most, and never a day in the future', () => {
    const earliest = earliestDate(NOW)
    expect(earliest).toBe('2026-10-16')
    expect(hoursFor({ kind: 'since', date: earliest }, NOW)).toBeLessThanOrEqual(MAX_HOURS)
    expect(validSince(earliest, NOW)).toBe(true)
    expect(validSince('2026-10-15', NOW)).toBe(false)
    expect(validSince(istDate(NOW), NOW)).toBe(true)
    expect(validSince('2026-11-16', NOW)).toBe(false)
  })

  it('refuses dates that are not dates', () => {
    for (const bad of ['2026-02-30', '2026-13-01', '1 Nov', '', '2026-11-1']) {
      expect(istMidnight(bad)).toBeNull()
      expect(validSince(bad, NOW)).toBe(false)
    }
  })

  it('uses the date in India, not the device’s', () => {
    // 19:00 UTC on 14 Nov is already 00:30 on 15 Nov in India.
    expect(istDate(Date.parse('2026-11-14T19:00:00Z'))).toBe('2026-11-15')
  })

  it('round-trips through the address, and keeps ?window= working', () => {
    for (const w of [
      { kind: 'preset', hours: 24 },
      { kind: 'preset', hours: 72 },
      { kind: 'preset', hours: 168 },
      { kind: 'since', date: '2026-11-01' },
    ] as const) {
      expect(windowFromSearch(searchFor(w), NOW)).toEqual(w)
    }
    expect(searchFor({ kind: 'preset', hours: 24 })).toBe('')
    expect(searchFor({ kind: 'since', date: '2026-11-01' })).toBe('?since=2026-11-01')
    expect(windowFromSearch('?window=7d', NOW)).toEqual({ kind: 'preset', hours: 168 })
    expect(windowFromSearch('?since=2026-11-01&window=3d', NOW)).toEqual({ kind: 'since', date: '2026-11-01' })
  })

  it('falls back to the last 24 hours for anything it cannot serve', () => {
    for (const search of ['?since=2025-01-01', '?since=tomorrow', '?window=90d', '?since=2026-11-20']) {
      expect(windowFromSearch(search, NOW)).toEqual({ kind: 'preset', hours: 24 })
    }
  })

  it('names the window plainly', () => {
    expect(sinceLabel('2026-11-01')).toBe('1 Nov')
    expect(windowPhrase({ kind: 'since', date: '2026-11-01' })).toBe('since 1 Nov')
    expect(windowPhrase({ kind: 'preset', hours: 72 })).toBe('from the last 3 days')
  })
})

describe('alert settings on the device', () => {
  const custom = { alerts: ['results', 'dividend'], movePct: 2.5, volumeMultiple: 3, moveRule: 'pct' as const }

  it('saves, loads and clears under one key', () => {
    const storage = memoryStorage()
    expect(loadSettings(storage)).toBeNull()
    expect(saveSettings(custom, storage)).toBe(true)
    expect(JSON.parse(storage.store.get(STORAGE_KEY)!)).toEqual(custom)
    expect(loadSettings(storage)).toEqual(custom)
    clearSettings(storage)
    expect(loadSettings(storage)).toBeNull()
  })

  it('checks each field on its own and falls back to that field’s default', () => {
    expect(parseSettings({ ...custom, movePct: 31 })).toEqual({ ...custom, movePct: DEFAULT_SETTINGS.movePct })
    expect(parseSettings({ ...custom, movePct: '5' })).toEqual({ ...custom, movePct: DEFAULT_SETTINGS.movePct })
    expect(parseSettings({ ...custom, volumeMultiple: 1 })).toEqual({ ...custom, volumeMultiple: 2 })
    expect(parseSettings({ ...custom, moveRule: 'loud' })).toEqual({ ...custom, moveRule: 'either' })
    expect(parseSettings({ ...custom, alerts: 'results' })).toEqual({ ...custom, alerts: DEFAULT_SETTINGS.alerts })
    expect(parseSettings({ ...custom, alerts: ['results', 'results', 'gossip', 7] })).toEqual({
      ...custom,
      alerts: ['results'],
    })
    expect(parseSettings({ ...custom, movePct: 2.499999 }).movePct).toBe(2.5)
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS)
    expect(parseSettings([1, 2])).toEqual(DEFAULT_SETTINGS)
  })

  it('keeps an empty list: no announcement type is an alert', () => {
    expect(parseSettings({ ...custom, alerts: [] }).alerts).toEqual([])
    expect(settingsParams({ ...custom, alerts: [] }).alerts).toBe('')
  })

  it('survives bad JSON and storage that throws', () => {
    expect(loadSettings(memoryStorage({ [STORAGE_KEY]: '{not json' }))).toBeNull()
    expect(loadSettings(throwing)).toBeNull()
    expect(saveSettings(custom, throwing)).toBe(false)
    expect(saveSettings(custom, null)).toBe(false)
    expect(() => clearSettings(throwing)).not.toThrow()
  })

  it('sends nothing until the investor saves settings, so the server’s defaults apply', () => {
    expect(settingsParams(null)).toEqual({})
    expect(settingsParams(custom)).toEqual({
      alerts: 'results,dividend',
      move_pct: '2.5',
      volume_multiple: '3',
      move_rule: 'pct',
    })
  })
})

describe('new since you last looked', () => {
  it('marks items published after the last visit, attention first', () => {
    const last = Date.parse('2026-11-10T00:00:00+05:30')
    expect(isNew(elgiResults, last)).toBe(true)
    expect(isNew(asianPaints, last)).toBe(false)
    expect(newItems(liveDigest, last).map((i) => i.id)).toEqual([elgiResults.id])
  })

  it('marks nothing on a first visit', () => {
    expect(isNew(elgiResults, null)).toBe(false)
    expect(newItems(liveDigest, null)).toEqual([])
  })

  it('reads the previous visit once per page load and records this one', () => {
    window.localStorage.setItem(LAST_SEEN_KEY, String(NOW - 5 * HOUR))
    expect(previousVisit(NOW)).toBe(NOW - 5 * HOUR)
    expect(readLastSeen()).toBe(NOW)
    expect(previousVisit(NOW + HOUR)).toBe(NOW - 5 * HOUR)
  })

  it('treats junk in storage as a first visit', () => {
    expect(readLastSeen(memoryStorage({ [LAST_SEEN_KEY]: 'yesterday' }))).toBeNull()
    expect(readLastSeen(memoryStorage({ [LAST_SEEN_KEY]: '-4' }))).toBeNull()
    expect(readLastSeen(throwing)).toBeNull()
  })
})
