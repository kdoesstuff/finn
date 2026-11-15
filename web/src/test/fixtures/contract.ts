// TEST FIXTURES ONLY. Never imported by the app, never shown to anyone.
//
// Payloads shaped exactly like docs/API.md (contract v1). The Asian Paints item, the session, the
// health body and the routine counts are the contract's own examples, verbatim. The other items
// follow the same shape, built around events recorded in docs/DECISIONS.md; their URLs and IDs
// are made up for the tests and are not real NSE documents.

import type { DemoSession, Digest, Health, Item, Snapshot } from '../../api/types'

export const session: DemoSession = {
  token: 'test-token-1',
  expires_at: '2026-11-16T03:07:00+05:30',
  investor: { name: 'Demo investor', demo: true, network: false },
}

export const health: Health = { ok: true, db: true, data_as_of: '2026-11-15T15:07:41+05:30', version: 'bf56e5f' }

/** The contract's Item example, verbatim. */
export const asianPaints: Item = {
  id: '106851770',
  symbol: 'ASIANPAINT',
  company: 'Asian Paints Limited',
  ts: '2026-11-06T22:06:58+05:30',
  headline: 'Appointment of Mr Leo Puri as Independent Director of the company w.e.f. September 07, 2026',
  label: 'Appointment',
  url: 'https://nsearchives.nseindia.com/corporate/ASIANPAINT_06112026220521_SE_intimation.pdf',
  category: 'management_change',
  subtype: '',
  role: 'director',
  action: 'appointment',
  detail_in_document: false,
  tier: 1,
  score: 55,
  alert: false,
  reasons: ['Board change below the top team'],
  related: [
    {
      id: '106851762',
      ts: '2026-11-06T22:02:45+05:30',
      label: 'Change in Director(s)',
      headline: 'Change in Director(s)',
      url: 'https://nsearchives.nseindia.com/corporate/...',
    },
  ],
}

export const elgiResults: Item = {
  id: 'test-elgi-1',
  symbol: 'ELGIEQUIP',
  company: 'Elgi Equipments Limited',
  ts: '2026-11-15T13:05:00+05:30',
  headline: 'Financial results for the quarter ended September 30, 2026',
  label: 'Financial Result Updates',
  url: 'https://nsearchives.nseindia.com/corporate/TEST_ELGIEQUIP_results.pdf',
  category: 'results',
  subtype: 'filing',
  role: '',
  action: '',
  detail_in_document: false,
  tier: 2,
  score: 85,
  alert: true,
  reasons: ['Quarterly results', 'Investor presentation filed on the same day'],
  related: [
    {
      id: 'test-elgi-2',
      ts: '2026-11-15T13:20:00+05:30',
      label: 'Investor Presentation',
      headline: 'Investor presentation on the results for the quarter ended September 30, 2026',
      url: 'https://nsearchives.nseindia.com/corporate/TEST_ELGIEQUIP_deck.pdf',
    },
    {
      id: 'test-elgi-3',
      ts: '2026-11-15T13:24:00+05:30',
      label: 'Press Release',
      headline: 'Press release on the results',
      url: 'http://example.com/not-an-nse-document.pdf',
    },
  ],
}

/** detail_in_document: the summary only restates NSE's label. */
export const hdfcBank: Item = {
  id: 'test-hdfc-1',
  symbol: 'HDFCBANK',
  company: 'HDFC Bank Limited',
  ts: '2026-11-06T19:40:00+05:30',
  headline: 'Change in Management',
  label: 'Change in Management',
  url: 'https://nsearchives.nseindia.com/corporate/TEST_HDFCBANK_change.pdf',
  category: 'management_change',
  subtype: '',
  role: '',
  action: '',
  detail_in_document: true,
  tier: 1,
  score: 60,
  alert: false,
  reasons: ['Management change; the summary does not say who, the filing does'],
  related: [],
}

/** A source that is not an NSE archive address: shown as text, never as a link. */
export const manappuram: Item = {
  id: 'test-manappuram-1',
  symbol: 'MANAPPURAM',
  company: 'Manappuram Finance Ltd.',
  ts: '2026-11-07T11:15:00+05:30',
  headline: 'Resignation of the Group Chief Technology Officer',
  label: 'Resignation',
  url: 'https://evil.example.com/nsearchives.nseindia.com/corporate/file.pdf',
  category: 'management_change',
  subtype: '',
  role: 'senior',
  action: 'resignation',
  detail_in_document: false,
  tier: 1,
  score: 70,
  alert: false,
  reasons: ['Senior management exit below the top team', 'Second resignation filing the same day'],
  related: [],
}

/** The contract's digest example, with items behind each count. */
export const liveDigest: Digest = {
  window: { hours: 24, from: '2026-11-14T15:07:00+05:30', to: '2026-11-15T15:07:00+05:30' },
  data_as_of: '2026-11-15T15:07:41+05:30',
  summary: '1 item needs your attention. 3 worth knowing; 18 routine filings set aside.',
  portfolio: { holdings: 18 },
  attention: [elgiResults],
  worth: [asianPaints, manappuram, hdfcBank],
  // Verbatim from the contract, where the kinds add up to 15 of the 18: the app shows the remainder.
  routine: { count: 18, by_kind: { earnings_call: 8, newspaper: 4, unclassified: 3 } },
  unexplained_moves: [],
}

export function digestFor(hours: number): Digest {
  const to = '2026-11-15T15:07:00+05:30'
  const from = new Date(Date.parse(to) - hours * 3_600_000).toISOString().replace('.000Z', '+00:00')
  return { ...liveDigest, window: { hours, from, to } }
}

/** A quiet day: nothing material, nothing worth knowing, no paperwork. */
export const quietDigest: Digest = {
  window: { hours: 24, from: '2026-11-14T15:07:00+05:30', to: '2026-11-15T15:07:00+05:30' },
  data_as_of: '2026-11-15T15:07:41+05:30',
  summary: 'Nothing material across your portfolio.',
  portfolio: { holdings: 18 },
  attention: [],
  worth: [],
  routine: { count: 0, by_kind: {} },
  unexplained_moves: [],
}

/** web/public/snapshot.json's shape: a 7-day digest plus snapshot and generated_at. */
export const snapshot: Snapshot = {
  ...liveDigest,
  window: { hours: 168, from: '2026-11-08T06:52:00+05:30', to: '2026-11-15T06:52:00+05:30' },
  data_as_of: '2026-11-15T06:40:12+05:30',
  summary: '1 item needs your attention. 3 worth knowing; 18 routine filings set aside.',
  snapshot: true,
  generated_at: '2026-11-15T06:52:00+05:30',
}

export const errorBody = (code: string, message: string) => ({ error: { code, message } })

/** "Now" for the tests: shortly after the window closes. */
export const NOW = Date.parse('2026-11-15T15:20:00+05:30')
