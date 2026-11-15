import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Routes } from './test/fakeServer'
import { after, fakeApi, hang, json, networkError } from './test/fakeServer'
import { digestFor, errorBody, health, liveDigest, NOW, quietDigest, session, snapshot } from './test/fixtures/contract'
import { App } from './App'
import type { Timing } from './api/client'
import type { AppConfig } from './config'

const SESSION = 'POST /v1/session/demo'
const DIGEST = 'GET /v1/digest'
const HEALTH = 'GET /health'
const SNAPSHOT = 'GET /snapshot.json'

const config: AppConfig = { apiUrl: 'https://api.finn.test', networkEnabled: false, sentryDsn: null }
const noSnapshot = new Response('Not found', { status: 404 })

function renderAt(path: string, routes: Routes, options: { timing?: Partial<Timing>; config?: AppConfig } = {}) {
  window.history.replaceState(null, '', path)
  // The page's clock is fixed (Date is faked); the client's deadlines run on a real clock.
  const { api, server } = fakeApi(
    { [HEALTH]: json(health), ...routes },
    { now: () => performance.now(), ...(options.timing ? { timing: options.timing } : {}) },
  )
  const user = userEvent.setup()
  render(<App api={api} config={options.config ?? config} />)
  return { server, user }
}

const live: Routes = { [SESSION]: json(session), [DIGEST]: json(liveDigest) }

beforeEach(() => {
  // Only the clock is fixed; timers stay real so the waking paths run.
  vi.useFakeTimers({ toFake: ['Date'], now: NOW })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('entry', () => {
  it('says what FINN is and that this is a demo, with one way in', async () => {
    const { server, user } = renderAt('/', live)
    expect(screen.getByRole('heading', { level: 1, name: 'FINN' })).toBeInTheDocument()
    expect(screen.getByText(/reads every filing your companies make on NSE/)).toBeInTheDocument()
    expect(screen.getByText(/demo portfolio of 18 NSE companies/)).toHaveTextContent(/holdings are\s+fictional/)
    // The server is woken while the reader reads.
    await vi.waitFor(() => expect(server.callsTo(HEALTH)).toHaveLength(1))
    expect(server.callsTo(SESSION)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Open today’s brief' }))
    expect(window.location.pathname).toBe('/brief')
    await screen.findByText(liveDigest.summary)
    expect(server.callsTo(SESSION)).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus()
  })

  it('shows the edition from the build', () => {
    renderAt('/', live, { config: { ...config, networkEnabled: true } })
    expect(screen.getByText('Full edition, with Network.')).toBeInTheDocument()
  })
})

describe('the brief', () => {
  it('shows a loading state first', () => {
    renderAt('/brief', { [SESSION]: hang })
    expect(screen.getByRole('status')).toHaveTextContent('Fetching your brief.')
  })

  it("shows the waking message and its progress when the server is slow to answer, then the brief", async () => {
    renderAt('/brief', { [SESSION]: after(250, () => json(session)), [DIGEST]: json(liveDigest) }, { timing: { slowAfterMs: 30 } })
    await screen.findByText(/Waking FINN’s server\. Free hosting sleeps when idle; this takes up to a minute\./)
    expect(screen.getByRole('progressbar', { name: 'Time spent waking the server' })).toBeInTheDocument()
    await screen.findByText(liveDigest.summary)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('shows the live brief: date, data as of, sections and routine line', async () => {
    renderAt('/brief', live)
    await screen.findByText(liveDigest.summary)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Brief for Sunday 15 November')
    expect(screen.getByText(/Data as of/)).toHaveTextContent('Data as of 15 Nov, 15:07 IST')
    expect(screen.getByText(/18 holdings, the 24 hours to/)).toHaveTextContent('18 holdings, the 24 hours to 15 Nov, 15:07 IST.')

    const attention = screen.getByRole('region', { name: /Needs your attention/ })
    const card = within(attention).getByRole('article', { name: /Elgi Equipments/ })
    expect(card).toHaveTextContent('Q2 FY27 results: revenue ₹980 cr, up 11.4% YoY; PAT ₹104 cr')
    expect(card).toHaveTextContent('Results')
    // The quarter's numbers from the XBRL: each line with its margin, QoQ and YoY.
    const table = within(card).getByRole('table', { name: 'Q2 FY27, consolidated, ₹ crore' })
    const ebitda = within(table).getByRole('row', { name: /EBITDA/ })
    expect(ebitda).toHaveTextContent('₹150 15.3%')
    expect(ebitda).toHaveTextContent('+13.6%')
    expect(within(table).getByRole('row', { name: /PAT/ })).toHaveTextContent('—') // no year-ago figure
    expect(card).toHaveTextContent('From Elgi Equipments’s XBRL filing.')
    // The move this filing may explain sits on its card.
    expect(within(card).getByRole('list', { name: 'Price and volume moves around this filing' })).toHaveTextContent(
      '15 Nov: Closed up 9.0%, a 4.1 sigma day against its last 60 sessions',
    )

    // A move no filing explains, and the promoter pledge NSE published.
    const moves = screen.getByRole('region', { name: /Moves without a filing/ })
    expect(moves).toHaveTextContent('ABB India ABB')
    expect(moves).toHaveTextContent('14 Nov: Closed down 7.0%')
    const pledges = screen.getByRole('region', { name: /Promoter pledges/ })
    expect(pledges).toHaveTextContent('24.85% of the promoters’ 62.85% stake is pledged.')
    expect(pledges).toHaveTextContent('As published by NSE on 9 Nov, for shareholding at 30 Sept.')
    expect(card).toHaveTextContent('On your alert list')
    // Relative and absolute Indian time.
    expect(within(card).getByText('2 hours ago')).toHaveAttribute('datetime', '2026-11-15T13:05:00+05:30')
    expect(card).toHaveTextContent('15 Nov, 13:05')

    const worth = screen.getByRole('region', { name: /Worth knowing/ })
    expect(within(worth).getAllByRole('article')).toHaveLength(3)
    const asian = within(worth).getByRole('article', { name: /Asian Paints/ })
    expect(asian).toHaveTextContent('Appointment of Mr Leo Puri as Independent Director')
    expect(asian).toHaveTextContent('Management change, 9 days ago')
    expect(asian).toHaveTextContent('6 Nov')
    expect(asian).toHaveTextContent('22:06')

    expect(screen.getByRole('button', { name: '18 routine filings set aside' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Core edition.')).toBeInTheDocument()
  })

  it('makes a quiet day a complete answer', async () => {
    renderAt('/brief', { [SESSION]: json(session), [DIGEST]: json(quietDigest) })
    await screen.findByText('Nothing material across your portfolio.')
    expect(screen.getByText(/No filings from your companies in this window\./)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Needs your attention/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Worth knowing/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /routine/ })).not.toBeInTheDocument()
  })

  it('keeps the routine line on a quiet day with paperwork', async () => {
    const quietWithRoutine = {
      ...quietDigest,
      summary: 'Nothing material across your portfolio. 1 routine filings set aside.',
      routine: { count: 1, by_kind: { newspaper: 1 } },
    }
    const { user } = renderAt('/brief', { [SESSION]: json(session), [DIGEST]: json(quietWithRoutine) })
    await user.click(await screen.findByRole('button', { name: '1 routine filing set aside' }))
    expect(screen.getByText('newspaper notice')).toBeInTheDocument()
  })
})

describe('evidence and reasons', () => {
  it('opens "Why am I seeing this" to the ranked reasons', async () => {
    const { user } = renderAt('/brief', live)
    const card = await screen.findByRole('article', { name: /Elgi Equipments/ })
    const why = within(card).getByRole('button', { name: 'Why am I seeing this' })
    const panel = document.getElementById(why.getAttribute('aria-controls')!)!
    expect(panel).not.toBeVisible()
    await user.click(why)
    expect(why).toHaveAttribute('aria-expanded', 'true')
    expect(panel).toBeVisible()
    const reasons = within(panel).getAllByRole('listitem').map((li) => li.textContent)
    expect(reasons).toEqual(['Quarterly results', 'Investor presentation filed on the same day'])
    expect(panel).toHaveTextContent('NSE’s label for this filing: Financial Result Updates')
  })

  it('links the source document safely, in a new tab', async () => {
    renderAt('/brief', live)
    const card = await screen.findByRole('article', { name: /Elgi Equipments/ })
    const link = within(card).getByRole('link', { name: /Read the filing/ })
    expect(link).toHaveAttribute('href', 'https://nsearchives.nseindia.com/corporate/TEST_ELGIEQUIP_results.pdf')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveAccessibleName('Read the filing, PDF, Elgi Equipments, on NSE, opens in a new tab')
  })

  it('shows a source that is not an NSE archive address as text, never as a link', async () => {
    renderAt('/brief', live)
    const line = await screen.findByRole('article', { name: /Manappuram Finance/ })
    expect(within(line).queryByRole('link')).not.toBeInTheDocument()
    expect(line).toHaveTextContent('https://evil.example.com/nsearchives.nseindia.com/corporate/file.pdf')
    expect(line).toHaveTextContent('not linked')
  })

  it('opens "+2 related filings", each with its own validated link', async () => {
    const { user } = renderAt('/brief', live)
    const card = await screen.findByRole('article', { name: /Elgi Equipments/ })
    await user.click(within(card).getByRole('button', { name: '+2 related filings' }))
    const related = within(card).getAllByRole('listitem').filter((li) => li.className === 'related__item')
    expect(related).toHaveLength(2)
    expect(within(related[0]!).getByRole('link', { name: /Read this filing/ })).toHaveAttribute(
      'href',
      'https://nsearchives.nseindia.com/corporate/TEST_ELGIEQUIP_deck.pdf',
    )
    expect(within(related[1]!).queryByRole('link')).not.toBeInTheDocument()
    expect(related[1]).toHaveTextContent('http://example.com/not-an-nse-document.pdf')
  })

  it('says honestly when only the document has the detail', async () => {
    renderAt('/brief', live)
    const line = await screen.findByRole('article', { name: /HDFC Bank/ })
    expect(line).toHaveTextContent('Change in Management')
    expect(line).toHaveTextContent('The filing does not say who; the document does.')
    const asian = screen.getByRole('article', { name: /Asian Paints/ })
    expect(asian).not.toHaveTextContent('the document does')
  })

  it('expands routine filings to counts by kind in plain words', async () => {
    const { user } = renderAt('/brief', live)
    const toggle = await screen.findByRole('button', { name: '18 routine filings set aside' })
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const items = screen.getAllByRole('listitem').filter((li) => li.closest('.routine__list'))
    expect(items.map((li) => li.textContent)).toEqual([
      '8 earnings call notices',
      '4 newspaper notices',
      '3 other filings',
      '3 not broken down by kind',
    ])
  })
})

describe('window', () => {
  it('asks for the chosen window and remembers it in the address', async () => {
    const { server, user } = renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: [json(liveDigest), json(digestFor(72)), json(digestFor(168))],
    })
    await screen.findByText(liveDigest.summary)
    expect(screen.getByRole('radio', { name: '24 hours' })).toBeChecked()

    await user.click(screen.getByRole('radio', { name: '3 days' }))
    await screen.findByText(/the 3 days to/)
    expect(window.location.search).toBe('?window=3d')

    await user.click(screen.getByRole('radio', { name: '7 days' }))
    await screen.findByText(/the 7 days to/)
    expect(server.callsTo(DIGEST).map((c) => c.url.searchParams.get('hours'))).toEqual(['24', '72', '168'])
    expect(server.callsTo(SESSION)).toHaveLength(1)
  })

  it('reads the window from the address', async () => {
    const { server } = renderAt('/brief?window=7d', { [SESSION]: json(session), [DIGEST]: json(digestFor(168)) })
    await screen.findByText(/the 7 days to/)
    expect(screen.getByRole('radio', { name: '7 days' })).toBeChecked()
    expect(server.callsTo(DIGEST)[0]!.url.searchParams.get('hours')).toBe('168')
  })

  it('keeps the old brief on screen, marked busy, while the new window loads', async () => {
    const { user } = renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: [json(liveDigest), after(150, () => json(digestFor(72)))],
    })
    await screen.findByText(liveDigest.summary)
    await user.click(screen.getByRole('radio', { name: '3 days' }))
    expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText(liveDigest.summary)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Fetching the last 3 days.')
    await screen.findByText(/the 3 days to/)
    expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'false')
  })
})

describe('when the live brief cannot be had', () => {
  it('on 503 shows the saved copy, labelled with its time and the reason', async () => {
    renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: json(errorBody('unavailable', 'The database is unreachable.'), 503),
      [SNAPSHOT]: json(snapshot),
    })
    const banner = await screen.findByRole('complementary', { name: 'Saved copy from 15 Nov, 06:52 IST' })
    expect(banner).toHaveTextContent("FINN’s server is running but cannot reach its database.")
    expect(banner).toHaveTextContent('covering the 7 days to 15 Nov, 06:52')
    expect(screen.getByText(snapshot.summary)).toBeInTheDocument()
    expect(screen.getByText(/Data as of/)).toHaveTextContent('Data as of 15 Nov, 06:40 IST')
    expect(screen.getByText(/The saved copy covers 7 days/)).toBeInTheDocument()
  })

  it('shows the saved copy when the server never wakes', async () => {
    renderAt(
      '/brief',
      { [SESSION]: networkError, [HEALTH]: networkError, [SNAPSHOT]: json(snapshot) },
      { timing: { wakeBudgetMs: 150 } },
    )
    const banner = await screen.findByRole('complementary', { name: /Saved copy from/ })
    expect(banner).toHaveTextContent("FINN’s server did not answer within 90 seconds.")
  })

  it('shows the saved copy when the brief does not match the contract', async () => {
    renderAt('/brief', { [SESSION]: json(session), [DIGEST]: json({ summary: 'x' }), [SNAPSHOT]: json(snapshot) })
    const banner = await screen.findByRole('complementary', { name: /Saved copy from/ })
    expect(banner).toHaveTextContent('sent a brief this version of the app cannot read')
  })

  it('without a saved copy, says so and offers to try again, which can succeed', async () => {
    const { server, user } = renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: [json(errorBody('unavailable', 'The database is unreachable.'), 503), json(liveDigest)],
      [SNAPSHOT]: noSnapshot,
    })
    const heading = await screen.findByRole('heading', { name: 'The brief could not be loaded' })
    expect(heading).toHaveFocus()
    expect(screen.getByText(/no saved copy of the brief yet/)).toBeInTheDocument()
    expect(screen.queryByText(liveDigest.summary)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText(liveDigest.summary)
    expect(server.callsTo(DIGEST)).toHaveLength(2)
  })

  it('goes back to the live brief from the saved copy', async () => {
    const { user } = renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: [json(errorBody('unavailable', 'The database is unreachable.'), 503), json(quietDigest)],
      [SNAPSHOT]: json(snapshot),
    })
    await user.click(await screen.findByRole('button', { name: 'Try the live brief' }))
    await screen.findByText('Nothing material across your portfolio.')
    expect(screen.queryByRole('complementary', { name: /Saved copy/ })).not.toBeInTheDocument()
  })

  it('on 401 starts a new session and carries on', async () => {
    const { server } = renderAt('/brief', {
      [SESSION]: [json(session), json({ ...session, token: 'test-token-2' })],
      [DIGEST]: [json(errorBody('unauthorised', 'Sign in again: your session has expired.'), 401), json(liveDigest)],
    })
    await screen.findByText(liveDigest.summary)
    expect(server.callsTo(SESSION)).toHaveLength(2)
  })

  it('on 429 says how long to wait, then asks again by itself', async () => {
    const { server } = renderAt('/brief', {
      [SESSION]: json(session),
      [DIGEST]: [json(errorBody('rate_limited', 'Too many requests.'), 429, { 'Retry-After': '1' }), json(liveDigest)],
    })
    await screen.findByRole('heading', { name: 'Too many requests' })
    expect(screen.getByText(/FINN will ask again in 1 second\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again now' })).toBeInTheDocument()
    await act(async () => {
      vi.setSystemTime(NOW + 2_000)
      await new Promise((resolve) => setTimeout(resolve, 1_100))
    })
    await screen.findByText(liveDigest.summary)
    expect(server.callsTo(DIGEST)).toHaveLength(2)
  })
})
