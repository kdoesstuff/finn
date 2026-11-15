import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { parseCompany } from '../api/pull'
import type { Company } from '../api/pull'
import type { AppConfig } from '../config'
import { fakeApi, json, type Routes } from '../test/fakeServer'
import { asianPaints, health, liveDigest, NOW, session } from '../test/fixtures/contract'
import { signedPct, symbolFromPath } from './ResearchScreen'

// TEST FIXTURES ONLY: shaped like docs/API.md "Company research"; URLs are made up.
const XBRL = 'https://nsearchives.nseindia.com/corporate/xbrl/TCS_test.xml'
const CALL = 'https://nsearchives.nseindia.com/corporate/TCS_call_test.pdf'

export const tcs: Company = {
  symbol: 'TCS',
  name: 'Tata Consultancy Services Limited',
  isin: 'INE467B01029',
  industry: 'Computers - Software & Consulting',
  data_as_of: '2026-11-15T15:35:17+05:30',
  coverage: { level: 'deep', reason: 'holding', missing: ['Not built yet: bull and bear case.'] },
  price: {
    day: '2026-11-13', close: 2407.5, change_1d_pct: -1.4, change_1m_pct: 3.1, change_since_pct: 6.2,
    since: '2026-06-25', volume: 2104567, avg_volume_20d: 2400311,
  },
  results: {
    template: 'standard', basis: 'consolidated', unit: '₹ crore',
    latest: {
      template: 'standard', period_end: '2026-09-30', basis: 'consolidated', unit: '₹ crore',
      rows: [{ metric: 'Revenue', value: 73188, qoq: { pct: 2.1, note: '' }, yoy: { pct: 11.2, note: '' } }],
      notes: [], source: XBRL,
    },
    quarters: [
      { period_end: '2026-09-30', revenue: 73188, ebitda: 19554, ebitda_margin: 26.7, pbt: 18120, pat: 13410, pat_margin: 18.3, source: XBRL },
      { period_end: '2026-06-30', revenue: 71680, ebitda: 18900, ebitda_margin: 26.4, pbt: 17500, pat: 12900, pat_margin: 18.0, source: XBRL },
    ],
    notes: ['EBITDA = profit before tax and exceptional items + finance costs + depreciation - other income.'],
  },
  filings: { days: 90, items: [asianPaints], more: 0, routine: { count: 3, by_kind: { earnings_call: 3 } } },
  documents: [{ kind: 'transcript', title: 'Earnings call, quarter to 30 Jun 2026', period: '2026-06-30', published: '2026-07-14', url: CALL, pages: 18 }],
  analyses: {
    ledger: {
      summary: 'kept 1 of 2 measurable promises',
      counts: { kept: 1, missed: 1 },
      statements: [
        {
          said_in: '2026-06-30', quote: 'We expect double-digit revenue growth this year.', page: 4, url: CALL,
          metric: 'Revenue growth', target: 'double digit', horizon: 'FY27', status: 'kept',
          evidence: { kind: 'numbers', metric: 'Revenue YoY', value: '+11.2%', period_end: '2026-09-30', url: XBRL },
        },
      ],
      gaps: ['The call for the quarter to 31 Mar 2026 could not be read.'],
      sources: [{ kind: 'transcript', title: 'Earnings call', url: CALL }],
      model: 'gemini-3.5-flash-lite',
      generated_at: '2026-11-15T18:00:00+05:30',
    },
    snapshot: null,
    bull_bear: null,
  },
}

const config: AppConfig = { apiUrl: 'https://api.finn.test', networkEnabled: false, sentryDsn: null }

function renderAt(path: string, routes: Routes) {
  window.history.replaceState(null, '', path)
  const { api, server } = fakeApi({ 'GET /health': json(health), 'POST /v1/session/demo': json(session), ...routes }, { now: () => performance.now() })
  const user = userEvent.setup()
  render(<App api={api} config={config} />)
  return { server, user }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: NOW })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('research', () => {
  it('finds a company and opens its page', async () => {
    const { server, user } = renderAt('/research', {
      'GET /v1/companies': json({ query: 'tata', companies: [{ symbol: 'TCS', name: tcs.name, covered: true }, { symbol: 'TATAMOTORS', name: 'Tata Motors Limited', covered: false }] }),
      'GET /v1/company/TCS': json(tcs),
    })
    expect(screen.getByRole('heading', { level: 1, name: 'Research a company' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Research' })).toHaveAttribute('aria-current', 'page')
    await user.type(screen.getByLabelText('Company name or NSE symbol'), 'tata')
    await user.click(screen.getByRole('button', { name: 'Find' }))
    const list = await screen.findByRole('list', { name: 'Matches' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(within(list).getByText('Covered')).toBeInTheDocument()
    expect(server.callsTo('GET /v1/companies')[0]?.url.searchParams.get('q')).toBe('tata')
    expect(server.callsTo('GET /v1/companies')[0]?.headers.get('authorization')).toBe('Bearer test-token-1')

    await user.click(within(list).getByRole('link', { name: /Tata Consultancy/ }))
    expect(await screen.findByRole('heading', { level: 1, name: /Tata Consultancy Services Limited/ })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/research/TCS')
  })

  it('shows the ledger first, with each promise, its quote and what decided it', async () => {
    renderAt('/research/TCS', { 'GET /v1/company/TCS': json(tcs) })
    const ledger = await screen.findByRole('region', { name: 'Promised and delivered' })
    expect(within(ledger).getByText('kept 1 of 2 measurable promises')).toBeInTheDocument()
    expect(within(ledger).getByText('Kept')).toBeInTheDocument()
    expect(within(ledger).getByText('We expect double-digit revenue growth this year.')).toBeInTheDocument()
    expect(within(ledger).getByText(/Delivered: Revenue YoY, \+11.2%/)).toBeInTheDocument()
    expect(within(ledger).getByText('The call for the quarter to 31 Mar 2026 could not be read.')).toBeInTheDocument()
    const sections = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(sections.indexOf('Promised and delivered')).toBeLessThan(sections.indexOf('Results, quarter to 2026-09-30'))
    expect(screen.getByText(/₹2,407.5 at the close on 2026-11-13 · −1.4% on the day/)).toBeInTheDocument()
    expect(screen.getByText('Not built yet: bull and bear case.')).toBeInTheDocument()
    const results = screen.getByRole('region', { name: /Results, quarter to/ })
    expect(within(results).getByRole('row', { name: /Revenue 73,188 \+2.1% \+11.2%/ })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Quarter by quarter' })).toBeInTheDocument()
    expect(screen.getByText(/3 routine filings set aside/)).toBeInTheDocument()
  })

  it('says plainly what a company outside coverage lacks', async () => {
    const basic: Company = {
      ...tcs, symbol: 'DABUR', name: 'Dabur India Limited', results: null, documents: [],
      analyses: { ledger: null, snapshot: null, bull_bear: null },
      coverage: { level: 'basic', reason: null, missing: ['FINN does not cover this company yet, so this page shows only its prices and filings from NSE: no quarterly results, documents or analyses.'] },
    }
    renderAt('/research/dabur', { 'GET /v1/company/DABUR': json(basic) })
    expect(await screen.findByText(/does not cover this company yet/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Promised and delivered' })).not.toBeInTheDocument()
  })

  it('reports an unknown symbol and can try again', async () => {
    const { user, server } = renderAt('/research/NOSUCH', {
      'GET /v1/company/NOSUCH': json({ error: { code: 'not_found', message: 'FINN knows no NSE company with the symbol NOSUCH.' } }, 404),
    })
    expect(await screen.findByText('FINN knows no NSE company with the symbol NOSUCH.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await vi.waitFor(() => expect(server.callsTo('GET /v1/company/NOSUCH')).toHaveLength(2))
  })

  it('links the brief and research both ways', async () => {
    const { user } = renderAt('/brief', { 'GET /v1/digest': json(liveDigest), 'GET /snapshot.json': new Response('', { status: 404 }) })
    expect(screen.getByRole('link', { name: 'Brief' })).toHaveAttribute('aria-current', 'page')
    await user.click(screen.getByRole('link', { name: 'Research' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Research a company' })).toBeInTheDocument()
  })
})

describe('research parsing', () => {
  it('reads the contract and keeps the page when one analysis is malformed', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const broken = { ...tcs, analyses: { ...tcs.analyses, ledger: { summary: 7 } } }
    const page = parseCompany(JSON.parse(JSON.stringify(broken)))
    expect(page.analyses.ledger).toBeNull()
    expect(page.results?.quarters).toHaveLength(2)
    expect(warn).toHaveBeenCalledOnce()
    expect(parseCompany(JSON.parse(JSON.stringify(tcs)))).toEqual(tcs)
    expect(() => parseCompany({ ...tcs, coverage: { level: 'deepest', reason: null, missing: [] } })).toThrow(/coverage.level/)
    warn.mockRestore()
  })

  it('refuses a ledger quote linked anywhere but https', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const ledger = tcs.analyses.ledger!
    const evil = { ...tcs, analyses: { ...tcs.analyses, ledger: { ...ledger, statements: [{ ...ledger.statements[0], url: 'javascript:alert(1)' }] } } }
    expect(parseCompany(JSON.parse(JSON.stringify(evil))).analyses.ledger).toBeNull()
    warn.mockRestore()
  })

  it('reads symbols from paths and signs percentages', () => {
    expect(symbolFromPath('/research/tcs')).toBe('TCS')
    expect(symbolFromPath('/research/M%26M')).toBe('M&M')
    expect(symbolFromPath('/research')).toBeNull()
    expect(symbolFromPath('/research/<script>')).toBeNull()
    expect(signedPct(2.04)).toBe('+2.0%')
    expect(signedPct(-1.45)).toBe('−1.4%')
    expect(signedPct(null)).toBe('–')
  })
})
