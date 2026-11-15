import { describe, expect, it } from 'vitest'
import { categoryLabel, detailInDocumentNote, kindPhrase, routineKinds, shortCompany } from './labels'
import { documentKind, nseDocumentUrl } from './links'
import { formatClock, formatDay, formatFull, formatRelative, formatStamp } from './time'

describe('source links', () => {
  it('links only https documents on NSE archives', () => {
    expect(nseDocumentUrl('https://nsearchives.nseindia.com/corporate/X_1.pdf')).toBe(
      'https://nsearchives.nseindia.com/corporate/X_1.pdf',
    )
    expect(nseDocumentUrl('https://archives.nseindia.com/corporate/X_1.pdf')).not.toBeNull()
    expect(nseDocumentUrl('https://nsearchives.nseindia.in/corporate/ABB_13112026174803_Q2.pdf')).not.toBeNull()
    expect(nseDocumentUrl('https://nsearchives.nseindia.in.evil.example/X.pdf')).toBeNull()
    for (const bad of [
      'http://nsearchives.nseindia.com/corporate/X.pdf',
      'https://nsearchives.nseindia.com.evil.example/X.pdf',
      'https://evil.example.com/nsearchives.nseindia.com/X.pdf',
      'https://user:pass@nsearchives.nseindia.com/X.pdf',
      'https://nsearchives.nseindia.com:8443/X.pdf',
      'javascript:alert(1)',
      'data:text/html,hi',
      '/corporate/X.pdf',
      '',
    ]) {
      expect(nseDocumentUrl(bad), bad).toBeNull()
    }
  })

  it('says when a link is a PDF', () => {
    expect(documentKind('https://nsearchives.nseindia.com/a/B.PDF')).toBe('PDF')
    expect(documentKind('https://nsearchives.nseindia.com/a/B.xml')).toBeNull()
  })
})

describe('Indian time', () => {
  // The test environment's clock is New York's (vite.config.ts), so these prove the zone is fixed.
  it('formats in IST whatever the device zone', () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('America/New_York')
    const ts = '2026-11-06T22:06:58+05:30'
    expect(formatClock(ts)).toBe('22:06')
    expect(formatStamp(ts)).toBe('6 Nov, 22:06')
    expect(formatFull(ts)).toBe('6 November 2026, 22:06 IST')
    expect(formatDay('2026-11-15T00:30:00+05:30')).toBe('Sunday 15 November')
  })

  it('counts days by the Indian calendar', () => {
    const now = Date.parse('2026-11-15T00:30:00+05:30')
    expect(formatRelative('2026-11-15T00:29:40+05:30', now)).toBe('just now')
    expect(formatRelative('2026-11-15T00:10:00+05:30', now)).toBe('20 minutes ago')
    // 2 hours earlier, but the day before in India:
    expect(formatRelative('2026-11-14T22:30:00+05:30', now)).toBe('yesterday')
    expect(formatRelative('2026-11-06T22:06:58+05:30', now)).toBe('9 days ago')
    expect(formatRelative('2026-11-15T03:30:00+05:30', Date.parse('2026-11-15T09:30:00+05:30'))).toBe('6 hours ago')
  })
})

describe('plain words', () => {
  it('names categories for people', () => {
    expect(categoryLabel('management_change')).toBe('Management change')
    expect(categoryLabel('M&A')).toBe('Merger or acquisition')
    expect(categoryLabel('some_new_kind')).toBe('Some new kind')
  })

  it('counts routine filings in words, largest first', () => {
    expect(kindPhrase('earnings_call', 8)).toBe('earnings call notices')
    expect(kindPhrase('newspaper', 1)).toBe('newspaper notice')
    expect(kindPhrase('unclassified', 3)).toBe('other filings')
    expect(kindPhrase('mystery_kind', 2)).toBe('mystery kind filings')
    expect(routineKinds({ newspaper: 4, unclassified: 3, earnings_call: 8, empty: 0 })).toEqual([
      { kind: 'earnings_call', count: 8, phrase: 'earnings call notices' },
      { kind: 'newspaper', count: 4, phrase: 'newspaper notices' },
      { kind: 'unclassified', count: 3, phrase: 'other filings' },
    ])
  })

  it('says honestly when the detail is only in the document', () => {
    expect(detailInDocumentNote('management_change')).toBe('The filing does not say who; the document does.')
    expect(detailInDocumentNote('results')).toBe('The filing does not give the numbers; the document does.')
    expect(detailInDocumentNote('litigation')).toBe('The filing does not say what happened; the document does.')
  })

  it('shortens company names', () => {
    expect(shortCompany('Asian Paints Limited')).toBe('Asian Paints')
    expect(shortCompany('Manappuram Finance Ltd.')).toBe('Manappuram Finance')
    expect(shortCompany('Larsen & Toubro Limited')).toBe('Larsen & Toubro')
    expect(shortCompany('Limited')).toBe('Limited')
  })
})

describe('build-time settings', () => {
  it('reads the API origin, the Network switch and the DSN', async () => {
    const { readConfig } = await import('../config')
    const env = { VITE_API_URL: 'https://finn-api-53vw.onrender.com/', VITE_NETWORK_ENABLED: 'true', VITE_SENTRY_DSN: ' ' }
    expect(readConfig(env as ImportMetaEnv)).toEqual({
      apiUrl: 'https://finn-api-53vw.onrender.com',
      networkEnabled: true,
      sentryDsn: null,
    })
    expect(readConfig({ VITE_API_URL: 'https://a.example' } as ImportMetaEnv).networkEnabled).toBe(false)
    expect(() => readConfig({} as ImportMetaEnv)).toThrow(/VITE_API_URL is not set/)
  })
})
