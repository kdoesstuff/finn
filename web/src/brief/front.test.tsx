import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { parseDigest } from '../api/validate'
import { liveDigest, quietDigest } from '../test/fixtures/contract'
import { forCompany, holdings, Holdings } from './Holdings'
import { filterCounts, Summary } from './Summary'

describe('the filter, made visible', () => {
  it('counts what FINN read and where it went, related filings included', () => {
    expect(filterCounts(liveDigest)).toEqual({ read: 24, need: 1, worth: 3, aside: 18, grouped: 2 })
  })

  it('falls back to the three piles when the API does not send filings_read', () => {
    const older = { ...liveDigest, filings_read: undefined }
    expect(filterCounts(older)).toEqual({ read: 22, need: 1, worth: 3, aside: 18, grouped: 0 })
  })

  it('shows the count as a heading and each pile as a link to its section, plus the 30-second read', async () => {
    const user = userEvent.setup()
    const onPlay = vi.fn()
    render(<Summary digest={liveDigest} onPlay={onPlay} />)
    expect(screen.getByRole('heading', { level: 2, name: 'FINN read 24 filings for you' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /1 needs you/ })).toHaveAttribute('href', '#attention-heading')
    expect(screen.getByRole('link', { name: /18 set aside/ })).toHaveAttribute('href', '#routine-heading')
    expect(screen.getByText('filed alongside those')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Read in 30 seconds/ }))
    expect(onPlay).toHaveBeenCalledTimes(1)
  })

  it('is just the lede on a quiet day', () => {
    render(<Summary digest={quietDigest} onPlay={() => undefined} />)
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Read in 30 seconds/ })).not.toBeInTheDocument()
  })
})

describe('the portfolio at a glance', () => {
  it('shows every holding when the digest lists them, loud ones marked', () => {
    const { tiles, quietRest } = holdings(liveDigest)
    expect(tiles).toHaveLength(18)
    expect(quietRest).toBe(0)
    expect(tiles.find((t) => t.symbol === 'ELGIEQUIP')).toMatchObject({ standing: 'need' })
    expect(tiles.find((t) => t.symbol === 'HDFCBANK')).toMatchObject({ standing: 'worth' })
    expect(tiles.find((t) => t.symbol === 'ABB')).toMatchObject({ standing: 'quiet', move: true })
    expect(tiles.find((t) => t.symbol === 'KALYANKJIL')).toMatchObject({ standing: 'quiet', pledge: true })
    expect(tiles.find((t) => t.symbol === 'TCS')).toMatchObject({ standing: 'quiet', move: false, pledge: false })
  })

  it('without the list, shows the companies the digest names and counts the quiet rest', () => {
    const older = { ...liveDigest, portfolio: { holdings: 18, pledges: liveDigest.portfolio.pledges } }
    const { tiles, quietRest } = holdings(older)
    expect(tiles.map((t) => t.symbol)).toEqual(['ELGIEQUIP', 'ASIANPAINT', 'HDFCBANK', 'MANAPPURAM', 'ABB', 'KALYANKJIL'])
    expect(quietRest).toBe(12)
  })

  it('narrows the page to one company and back', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const { rerender } = render(<Holdings digest={liveDigest} selected={null} onSelect={onSelect} />)
    const grid = screen.getByRole('region', { name: 'Your portfolio today' })
    await user.click(within(grid).getByRole('button', { name: 'ELGIEQUIP: needs you' }))
    expect(onSelect).toHaveBeenLastCalledWith('ELGIEQUIP')
    rerender(<Holdings digest={liveDigest} selected="ELGIEQUIP" onSelect={onSelect} />)
    expect(within(grid).getByRole('button', { name: 'ELGIEQUIP: needs you' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(within(grid).getByRole('button', { name: 'ELGIEQUIP: needs you' }))
    expect(onSelect).toHaveBeenLastCalledWith(null)
    await user.click(screen.getByRole('button', { name: 'Show all' }))
    expect(onSelect).toHaveBeenLastCalledWith(null)
    expect(within(grid).getByRole('button', { name: 'ABB: quiet, a move without a filing' })).toBeInTheDocument()
  })

  it('filters every list to the chosen company', () => {
    const elgi = forCompany(liveDigest, 'ELGIEQUIP')
    expect(elgi.attention).toHaveLength(1)
    expect(elgi.worth).toHaveLength(0)
    expect(elgi.unexplained_moves).toHaveLength(0)
    expect(forCompany(liveDigest, 'ABB').unexplained_moves).toHaveLength(1)
    expect(forCompany(liveDigest, null)).toBe(liveDigest)
  })
})

describe('fields added after v1', () => {
  it('reads portfolio.companies and filings_read when present, and does without them', () => {
    const full = parseDigest(JSON.parse(JSON.stringify(liveDigest)))
    expect(full.portfolio.companies).toHaveLength(18)
    expect(full.filings_read).toBe(24)
    const older = parseDigest(JSON.parse(JSON.stringify({ ...liveDigest, filings_read: undefined, portfolio: { holdings: 18, pledges: [] } })))
    expect(older.portfolio.companies).toBeUndefined()
    expect(older.filings_read).toBeUndefined()
  })
})
