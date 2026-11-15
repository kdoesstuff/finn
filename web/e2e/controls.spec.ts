// --- Controls --- since a date, the investor's alert settings, new since the last visit.
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { digestFor } from '../src/test/fixtures/contract'
import { NOW, mockApi, startClock, watchConsole } from './api'

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([])
}

const digestParams = (api: Awaited<ReturnType<typeof mockApi>>) =>
  api.requests
    .filter((r) => r.method() === 'GET' && new URL(r.url()).pathname === '/v1/digest')
    .map((r) => Object.fromEntries(new URL(r.url()).searchParams))

test.beforeEach(async ({ page }) => {
  await startClock(page)
})

test('a since date sets the window to that day’s midnight in India, up to now', async ({ page }) => {
  const problems = watchConsole(page)
  const api = await mockApi(page, { digest: (hours) => ({ body: digestFor(hours) }) })
  await page.goto('/brief')
  await expect(page.getByText(/the 24 hours to/)).toBeVisible()

  await page.getByRole('radio', { name: 'Since…' }).click()
  await expect(page).toHaveURL(/\?since=2026-11-01$/)
  await expect(page.getByText('Filings since 1 Nov')).toBeVisible()
  await page.getByLabel('Since the start of').fill('2026-11-10')
  await expect(page).toHaveURL(/\?since=2026-11-10$/)
  await expect(page.getByText('Filings since 10 Nov')).toBeVisible()
  await expect.poll(() => api.digestHours()).toEqual([24, 352, 136])
  await expectAccessible(page)
  expect(problems).toEqual([])
})

test('alert settings: change a threshold, and the brief is asked again with it', async ({ page }) => {
  const problems = watchConsole(page)
  const api = await mockApi(page)
  await page.goto('/brief')
  await expect(page.getByRole('button', { name: 'Your alerts' })).toBeVisible()
  await expect.poll(() => digestParams(api)).toEqual([{ hours: '24' }])

  await page.getByRole('button', { name: 'Your alerts' }).click()
  const dialog = page.getByRole('dialog', { name: 'Your alerts' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Your alerts' })).toBeFocused()
  await expectAccessible(page)

  const slider = dialog.getByRole('slider', { name: /Volume above/ })
  await slider.focus()
  for (let i = 0; i < 10; i += 1) await page.keyboard.press('ArrowRight')
  await expect(dialog.getByText('3×')).toBeVisible()
  await dialog.getByRole('checkbox', { name: /Credit ratings/ }).check()
  await dialog.getByRole('button', { name: 'Save and refresh the brief' }).click()

  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: 'Your alerts (custom)' })).toBeFocused()
  await expect.poll(() => digestParams(api).length).toBe(2)
  expect(digestParams(api)[1]).toEqual({
    hours: '24',
    alerts: 'results,M&A,management_change,litigation,pledging,credit_rating',
    move_pct: '5',
    volume_multiple: '3',
    move_rule: 'either',
  })

  // Kept on the device: a reload asks with the same settings.
  await page.reload()
  await expect(page.getByRole('button', { name: 'Your alerts (custom)' })).toBeVisible()
  await expect.poll(() => digestParams(api).length).toBe(3)
  expect(digestParams(api)[2]).toMatchObject({ volume_multiple: '3' })
  expect(problems).toEqual([])
})

test('items published since the last visit are marked new', async ({ page }) => {
  await page.addInitScript((seen) => {
    if (!window.sessionStorage.getItem('seeded')) {
      window.localStorage.setItem('finn.lastSeen.v1', String(seen))
      window.sessionStorage.setItem('seeded', '1')
    }
  }, NOW - 5 * 3_600_000)
  await mockApi(page)
  await page.goto('/brief')
  const link = page.getByRole('link', { name: '1 new since you last looked' })
  await expect(link).toBeVisible()
  await expect(page.locator('.seen-mark:has(#item-test-elgi-1) .badge--new')).toHaveText('New')
  await expect(page).toHaveTitle('(1) Your brief, FINN')
  await link.click()
  await expect(page).toHaveURL(/#item-test-elgi-1$/)

  // This visit is now the last one: nothing is new on the next.
  await page.reload()
  await expect(page.getByRole('button', { name: 'Your alerts' })).toBeVisible()
  await expect(page.getByText(/new since you last looked/)).toHaveCount(0)
})
