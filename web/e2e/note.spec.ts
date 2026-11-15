// --- Reader stream --- The filing reader's note in the real build, under the real security policy.
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Digest, Item } from '../src/api/types'
import { liveDigest, manappuram } from '../src/test/fixtures/contract'
import { mockApi, startClock, watchConsole } from './api'

const read: Item = {
  ...manappuram,
  note: {
    summary: 'Manappuram’s Group CTO, Arjun Rao, resigns to pursue opportunities outside the group.',
    quote: 'has tendered his resignation as Group Chief Technology Officer',
    page: 1,
    person: {
      name: 'Mr. Arjun Rao',
      role: 'Group Chief Technology Officer',
      action: 'resigned',
      effective_date: 'November 30, 2026',
      background: [{ text: 'He has led the group’s technology since 2021.', quote: 'heading technology for the group since 2021', page: 2 }],
      previous_roles: [{ org: 'Konark Engineering Limited', title: 'Head of IT' }],
    },
  },
}
const digest: Digest = { ...liveDigest, worth: liveDigest.worth.map((i) => (i.id === manappuram.id ? read : i)) }

test('a read filing shows its checked line and bio, accessibly and within the security policy', async ({ page }) => {
  const problems = watchConsole(page)
  await startClock(page)
  await mockApi(page, { digest: () => ({ body: digest }) })
  await page.goto('/brief')
  await expect(page.getByText(/resigns to pursue opportunities/)).toBeVisible()
  const bio = page.getByRole('region', { name: 'Mr. Arjun Rao' })
  await expect(bio.getByText('Resigned: Group Chief Technology Officer, effective November 30, 2026')).toBeVisible()

  const toggle = page.getByRole('button', { name: 'The filing’s words, p. 1' })
  await expect(page.getByText(/has tendered his resignation/)).toBeHidden()
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByText(/has tendered his resignation/)).toBeVisible()

  for (const name of ['The filing’s words, p. 1', 'The filing’s words, p. 2']) {
    const box = await page.getByRole('button', { name }).boundingBox()
    expect(box && box.height >= 44 && box.width >= 44, name).toBe(true)
  }
  const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(sideways).toBeLessThanOrEqual(0)
  const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  expect(axe.violations.map((v) => v.id)).toEqual([])
  expect(problems, 'console errors or CSP violations').toEqual([])
})
