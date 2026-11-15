// --- Reader stream --- The filing reader's note: the contract parser and what the brief shows.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Item, Note } from '../api/types'
import { ContractError, parseDigest } from '../api/validate'
import { NOW, liveDigest, manappuram } from '../test/fixtures/contract'
import { AttentionCard, WorthLine } from './ItemEntry'

const resigned: Note = {
  summary: 'Manappuram’s Group CTO, Arjun Rao, resigns to pursue opportunities outside the group.',
  quote: 'has tendered his resignation as Group Chief Technology Officer',
  page: 1,
  person: {
    name: 'Mr. Arjun Rao',
    role: 'Group Chief Technology Officer',
    action: 'resigned',
    effective_date: 'November 30, 2026',
    background: [
      {
        text: 'He has led the group’s technology since 2021.',
        quote: 'heading technology for the group since 2021',
        page: 2,
      },
    ],
    previous_roles: [{ org: 'Konark Engineering Limited', title: 'Head of IT' }],
  },
}
const read: Item = { ...manappuram, note: resigned }

const failsAt = (fn: () => unknown) => {
  try {
    fn()
  } catch (error) {
    if (error instanceof ContractError) return error.path
    throw error
  }
  return null
}

describe('the note in the contract', () => {
  it('reads a note, and an item from before notes existed as having none', () => {
    const digest = { ...liveDigest, worth: [read] }
    expect(parseDigest(digest).worth[0]?.note).toEqual(resigned)
    const older = Object.fromEntries(Object.entries(manappuram).filter(([key]) => key !== 'note'))
    expect(parseDigest({ ...liveDigest, worth: [older] }).worth[0]?.note).toBeNull()
  })

  it('names the part of a note that is wrong', () => {
    const bad = (note: unknown) => failsAt(() => parseDigest({ ...liveDigest, worth: [{ ...manappuram, note }] }))
    expect(bad({ ...resigned, page: -1 })).toBe('digest.worth[0].note.page')
    expect(bad({ ...resigned, person: { ...resigned.person, background: [{ text: 'x', quote: 'y', page: 0 }] } })).toBe(
      'digest.worth[0].note.person.background[0].page',
    )
    expect(bad({ ...resigned, person: { ...resigned.person, previous_roles: 'CTO' } })).toBe(
      'digest.worth[0].note.person.previous_roles',
    )
  })
})

describe('the note in the brief', () => {
  it('shows the line under the headline, with the filing’s words on tap', async () => {
    render(<WorthLine item={read} now={NOW} />)
    expect(screen.getByText(/resigns to pursue opportunities/)).toBeVisible()
    const quote = screen.getByText(/has tendered his resignation/)
    expect(quote).not.toBeVisible()
    const toggle = screen.getByRole('button', { name: 'The filing’s words, p. 1' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(quote).toBeVisible()
    expect(screen.getByText('Page 1 of the filing')).toBeVisible()
  })

  it('shows who a management change is about, each background line checkable', async () => {
    render(<AttentionCard item={read} now={NOW} />)
    const bio = screen.getByRole('region', { name: 'Mr. Arjun Rao' })
    expect(within(bio).getByText('Resigned: Group Chief Technology Officer, effective November 30, 2026')).toBeVisible()
    expect(within(bio).getByRole('list', { name: 'Earlier roles the filing names' })).toHaveTextContent(
      'Head of IT, Konark Engineering Limited',
    )
    const words = within(bio).getByRole('button', { name: 'The filing’s words, p. 2' })
    expect(within(bio).getByText(/heading technology for the group/)).not.toBeVisible()
    await userEvent.click(words)
    expect(within(bio).getByText(/heading technology for the group/)).toBeVisible()
  })

  it('shows only what was checked: a bio with no line, a line with no bio, or nothing', () => {
    const personOnly: Item = { ...manappuram, note: { ...resigned, summary: '', quote: '', page: 0 } }
    const { container, unmount } = render(<WorthLine item={personOnly} now={NOW} />)
    expect(container.querySelector('.reader__summary')).toBeNull()
    expect(screen.getByRole('region', { name: 'Mr. Arjun Rao' })).toBeVisible()
    unmount()

    const lineOnly: Item = {
      ...manappuram,
      note: { ...resigned, person: { ...resigned.person!, role: '', effective_date: '', background: [], previous_roles: [] } },
    }
    const second = render(<WorthLine item={lineOnly} now={NOW} />)
    expect(screen.getByText('Resigned')).toBeVisible()
    expect(screen.queryByRole('list', { name: 'Earlier roles the filing names' })).toBeNull()
    second.unmount()

    const unread = render(<WorthLine item={manappuram} now={NOW} />)
    expect(unread.container.querySelector('.reader')).toBeNull()
    expect(screen.queryByRole('region')).toBeNull()
  })
})
