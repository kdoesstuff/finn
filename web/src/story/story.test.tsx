import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QuarterBars, StackBar } from '../charts/Charts'
import { liveDigest, quietDigest } from '../test/fixtures/contract'
import { storyCards } from './cards'
import { Story } from './Story'

describe('storyCards', () => {
  it('makes one card per attention item, then one per unexplained move', () => {
    const cards = storyCards(liveDigest)
    expect(cards.map((c) => c.symbol)).toEqual(['ELGIEQUIP', 'ABB'])
    expect(cards[0]?.target).toEqual({ kind: 'item', id: 'test-elgi-1' })
    expect(cards[1]?.target).toEqual({ kind: 'research', symbol: 'ABB' })
    expect(cards[1]?.kind).toBe('Move without a filing')
  })

  it('makes no cards on a quiet day', () => {
    expect(storyCards(quietDigest)).toEqual([])
  })
})

describe('Story', () => {
  const cards = storyCards(liveDigest)

  it('opens on the first card with focus inside, and advances with the button and arrow keys', async () => {
    const user = userEvent.setup()
    render(<Story cards={cards} onClose={() => undefined} onDigIn={() => undefined} />)
    const dialog = screen.getByRole('dialog', { name: 'Today’s brief, card by card' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveFocus()
    expect(screen.getByText(/^1 of 2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText(/^2 of 2/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('ABB')
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument()

    fireEvent.keyDown(dialog, { key: 'ArrowLeft' })
    expect(screen.getByText(/^1 of 2/)).toBeInTheDocument()
    fireEvent.keyDown(dialog, { key: 'ArrowRight' })
    expect(screen.getByText(/^2 of 2/)).toBeInTheDocument()
  })

  it('closes on Escape, on Close, and on Done at the last card', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const { unmount } = render(<Story cards={cards} onClose={onClose} onDigIn={() => undefined} />)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Close the story' }))
    expect(onClose).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledTimes(3)
    unmount()
    expect(document.body).not.toHaveClass('story-open')
  })

  it('digs into the brief item, or into research for a move', async () => {
    const user = userEvent.setup()
    const onDigIn = vi.fn()
    render(<Story cards={cards} onClose={() => undefined} onDigIn={onDigIn} />)
    await user.click(screen.getByRole('button', { name: 'Dig in' }))
    expect(onDigIn).toHaveBeenLastCalledWith(cards[0])
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: /^Research / }))
    expect(onDigIn).toHaveBeenLastCalledWith(cards[1])
  })
})

describe('charts', () => {
  it('draws the latest quarter in the accent and PAT inside each bar', () => {
    const { container } = render(
      <QuarterBars points={[{ label: 'a', value: 10, inner: 2 }, { label: 'b', value: 20, inner: 4 }]} />,
    )
    expect(container.querySelectorAll('rect.chart__bar')).toHaveLength(2)
    expect(container.querySelectorAll('rect.chart__bar--latest')).toHaveLength(1)
    expect(container.querySelectorAll('rect.chart__inner')).toHaveLength(2)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('stacks counts end to end and skips an empty set', () => {
    const { container, rerender } = render(
      <StackBar parts={[{ key: 'a', count: 1, className: 'x' }, { key: 'b', count: 3, className: 'y' }]} />,
    )
    const rects = container.querySelectorAll('rect')
    expect(rects).toHaveLength(2)
    expect(rects[1]).toHaveAttribute('x', '60')
    rerender(<StackBar parts={[{ key: 'a', count: 0, className: 'x' }]} />)
    expect(container.querySelector('svg')).toBeNull()
  })
})
