import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { digestFor, errorBody, liveDigest, quietDigest, session } from '../src/test/fixtures/contract'
import { mockApi, snapshot, startClock, watchConsole } from './api'

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([])
}

async function expectNoSidewaysScroll(page: Page) {
  const { scroll, width } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }))
  expect(scroll).toBeLessThanOrEqual(width)
}

let problems: string[]

test.beforeEach(async ({ page }) => {
  problems = watchConsole(page)
  await startClock(page)
})

test.afterEach(() => {
  expect(problems, 'console errors or CSP violations').toEqual([])
})

test('from the introduction to the brief, under the production security headers', async ({ page }) => {
  const api = await mockApi(page)
  const response = await page.goto('/')
  const headers = response!.headers()
  expect(headers['content-security-policy']).toContain("script-src 'self'")
  expect(headers['x-content-type-options']).toBe('nosniff')

  await expect(page.getByRole('heading', { level: 1, name: 'FINN' })).toBeVisible()
  await expect(page.getByText(/demo portfolio of 18 NSE companies/)).toBeVisible()
  await expectAccessible(page)
  await expectNoSidewaysScroll(page)

  await page.getByRole('button', { name: 'Open today’s brief' }).click()
  await expect(page).toHaveURL(/\/brief$/)
  await expect(page.getByText(liveDigest.summary)).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Brief for Sunday 15 November')
  await expect(page.getByText(/^Data as of/)).toHaveText('Data as of 15 Nov, 15:07 IST')
  await expect(page.getByRole('region', { name: /Needs your attention/ }).getByRole('article')).toHaveCount(1)
  await expect(page.getByRole('region', { name: /Worth knowing/ }).getByRole('article')).toHaveCount(3)
  await expect(page.getByRole('button', { name: '18 routine filings set aside' })).toBeVisible()
  // Indian time, though the browser's zone is London.
  await expect(page.getByRole('article', { name: /Elgi Equipments/ })).toContainText('15 Nov, 13:05')
  expect(api.sessions()).toBe(1)
  // The token travels in a header, never in the address.
  const read = api.requests.find((r) => r.method() === 'GET' && r.url().includes('/v1/digest'))!
  expect(read.headers().authorization).toBe('Bearer test-token-1')
  expect(read.url()).not.toContain('token')
  await expectAccessible(page)
  await expectNoSidewaysScroll(page)
})

test('the window selector sets hours, by pointer and by keyboard', async ({ page }) => {
  const api = await mockApi(page, { digest: (hours) => ({ body: digestFor(hours) }) })
  await page.goto('/brief')
  await expect(page.getByText(/the 24 hours to/)).toBeVisible()

  await page.getByRole('radio', { name: '3 days' }).click()
  await expect(page.getByText(/the 3 days to/)).toBeVisible()
  await expect(page).toHaveURL(/\?window=3d$/)

  await page.getByRole('radio', { name: '3 days' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByText(/the 7 days to/)).toBeVisible()
  expect(api.digestHours()).toEqual([24, 72, 168])
})

test('reasons, related filings and routine counts open from the keyboard', async ({ page }) => {
  await mockApi(page)
  await page.goto('/brief')
  const card = page.getByRole('article', { name: /Elgi Equipments/ })
  const why = card.getByRole('button', { name: 'Why am I seeing this' })
  await why.focus()
  await page.keyboard.press('Enter')
  await expect(why).toHaveAttribute('aria-expanded', 'true')
  await expect(card.getByRole('listitem').filter({ hasText: /^Quarterly results$/ })).toBeVisible()

  const related = card.getByRole('button', { name: '+2 related filings' })
  await related.focus()
  await page.keyboard.press('Space')
  await expect(card.getByRole('link', { name: /Read this filing/ })).toHaveAttribute(
    'href',
    'https://nsearchives.nseindia.com/corporate/TEST_ELGIEQUIP_deck.pdf',
  )
  await expect(card.getByText('http://example.com/not-an-nse-document.pdf')).toBeVisible()

  const routine = page.getByRole('button', { name: '18 routine filings set aside' })
  await routine.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('earnings call notices')).toBeVisible()
  await expect(page.getByText('not broken down by kind')).toBeVisible()
  await expectAccessible(page)
})

test('source documents open on NSE in a new tab; anything else is text', async ({ page }) => {
  await mockApi(page)
  await page.goto('/brief')
  const link = page.getByRole('article', { name: /Elgi Equipments/ }).getByRole('link', { name: /Read the filing/ })
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  await expect(link).toHaveAttribute('href', /^https:\/\/nsearchives\.nseindia\.com\//)
  const manappuram = page.getByRole('article', { name: /Manappuram Finance/ })
  await expect(manappuram.getByRole('link')).toHaveCount(0)
  await expect(manappuram).toContainText('not linked')
})

test('a sleeping server: the waking message, then the brief', async ({ page }) => {
  await mockApi(page, { session: { body: session, delayMs: 4_500 } })
  await page.goto('/brief')
  await expect(page.getByRole('status')).toHaveText(
    "Waking FINN’s server. Free hosting sleeps when idle; this takes up to a minute.",
  )
  await expect(page.getByRole('progressbar', { name: 'Time spent waking the server' })).toBeVisible()
  await expectAccessible(page)
  await expect(page.getByText(liveDigest.summary)).toBeVisible({ timeout: 10_000 })
})

test('the database is down: the saved copy, clearly labelled', async ({ page }) => {
  await mockApi(page, {
    digest: () => ({ status: 503, body: errorBody('unavailable', 'The database is unreachable.') }),
    snapshot,
  })
  await page.goto('/brief')
  const banner = page.getByRole('complementary', { name: 'Saved copy from 15 Nov, 06:52 IST' })
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('cannot reach its database')
  await expect(page.getByText(snapshot.summary)).toBeVisible()
  await expectAccessible(page)
})

test('no saved copy yet: an honest error, and Try again works', async ({ page }) => {
  await mockApi(page, {
    digest: (_hours, call) =>
      call === 0 ? { status: 503, body: errorBody('unavailable', 'The database is unreachable.') } : { body: liveDigest },
    snapshot: 'none',
  })
  await page.goto('/brief')
  await expect(page.getByRole('heading', { name: 'The brief could not be loaded' })).toBeFocused()
  await expectAccessible(page)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText(liveDigest.summary)).toBeVisible()
})

test('a quiet day', async ({ page }) => {
  await mockApi(page, { digest: () => ({ body: quietDigest }) })
  await page.goto('/brief')
  await expect(page.getByText('Nothing material across your portfolio.')).toBeVisible()
  await expect(page.getByText(/No filings from your companies in this window\./)).toBeVisible()
  await expect(page.getByRole('region', { name: /Needs your attention/ })).toHaveCount(0)
  await expectAccessible(page)
})

test('dark theme: the ink pot', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await mockApi(page)
  await page.goto('/brief')
  await expect(page.getByText(liveDigest.summary)).toBeVisible()
  const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  expect(background).toBe('rgb(18, 23, 34)')
  await page.getByRole('button', { name: '18 routine filings set aside' }).click()
  await expectAccessible(page)
})

test('reduced motion: the double rule is simply there', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockApi(page)
  await page.goto('/brief')
  await expect(page.getByText(liveDigest.summary)).toBeVisible()
  const animation = await page.locator('.summary .total-rule').evaluate((el) => getComputedStyle(el).animationName)
  expect(animation).toBe('none')
})

test('every control is at least 44 px tall and wide', async ({ page }) => {
  await mockApi(page)
  await page.goto('/brief')
  await expect(page.getByText(liveDigest.summary)).toBeVisible()
  await page.getByRole('button', { name: '+2 related filings' }).click()
  const small = await page.evaluate(() => {
    const controls = [...document.querySelectorAll<HTMLElement>('a[href], button, .window__option')]
    return controls
      .filter((el) => el.offsetParent !== null && !el.classList.contains('skip-link'))
      .map((el) => ({ text: el.textContent.trim().slice(0, 40), box: el.getBoundingClientRect() }))
      .filter(({ box }) => box.height < 44 || box.width < 44)
      .map(({ text, box }) => `${text} (${Math.round(box.width)}x${Math.round(box.height)})`)
  })
  expect(small).toEqual([])
})

test('the security policy is enforced: an injected inline script does not run', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const ran = await page.evaluate(() => {
    const script = document.createElement('script')
    script.textContent = 'window.__injected = true'
    document.head.append(script)
    return (window as unknown as { __injected?: boolean }).__injected === true
  })
  expect(ran).toBe(false)
  await expect.poll(() => problems.some((p) => p.includes('Content Security Policy'))).toBe(true)
  // Expected here; every other test requires none.
  problems.length = 0
})
