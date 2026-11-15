import { type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from 'react'
import type { StoryCard } from './cards'
import './story.css'

interface Props {
  cards: StoryCard[]
  onClose: () => void
  /** Leave the story for the card's subject: the item in the brief, or the company's research page. */
  onDigIn: (card: StoryCard) => void
}

/**
 * Today's brief as a story: one card at a time, a big figure and one line each, the way a phone is
 * read on the move. Tap the right of a card (or swipe left, or press →) for the next, the left for
 * the previous; Escape closes; "Dig in" leaves for the detail. Nothing here fetches anything.
 */
export function Story({ cards, onClose, onDigIn }: Props) {
  const [index, setIndex] = useState(0)
  const dialog = useRef<HTMLDivElement>(null)
  const start = useRef<{ x: number; y: number } | null>(null)
  const card = cards[index]

  useEffect(() => {
    dialog.current?.focus()
    document.body.classList.add('story-open')
    return () => document.body.classList.remove('story-open')
  }, [])

  if (!card) return null
  const last = index === cards.length - 1
  const next = () => (last ? onClose() : setIndex((i) => i + 1))
  const previous = () => setIndex((i) => Math.max(0, i - 1))

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    } else if (event.key === 'ArrowRight' || event.key === 'PageDown') {
      event.preventDefault()
      next()
    } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
      event.preventDefault()
      previous()
    } else if (event.key === 'Tab') {
      // Keep focus inside the story while it is open.
      const focusable = dialog.current?.querySelectorAll<HTMLElement>('button')
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const lastButton = focusable[focusable.length - 1]
      if (!first || !lastButton) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        lastButton.focus()
      } else if (!event.shiftKey && document.activeElement === lastButton) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    start.current = { x: event.clientX, y: event.clientY }
  }
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const from = start.current
    start.current = null
    if (!from || (event.target as HTMLElement).closest('button')) return
    const dx = event.clientX - from.x
    const dy = event.clientY - from.y
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
      if (dx < 0) next()
      else previous()
      return
    }
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      const box = event.currentTarget.getBoundingClientRect()
      if (event.clientX - box.left < box.width / 3) previous()
      else next()
    }
  }

  return (
    <div className="story" role="dialog" aria-modal="true" aria-label="Today’s brief, card by card" tabIndex={-1} ref={dialog} onKeyDown={onKey}>
      <div className="story__progress" aria-hidden="true">
        {cards.map((c, i) => (
          <span key={c.key} className={i < index ? 'story__seg story__seg--done' : i === index ? 'story__seg story__seg--now' : 'story__seg'} />
        ))}
      </div>
      <div className="story__bar">
        <p className="story__count" aria-live="polite">
          {index + 1} of {cards.length}
          <span className="visually-hidden">
            : {card.company}, {card.kind}
          </span>
        </p>
        <button type="button" className="story__close" onClick={onClose} aria-label="Close the story">
          Close
        </button>
      </div>
      <div className="story__stage" onPointerDown={onPointerDown} onPointerUp={onPointerUp}>
        <article className={`story__card story__card--${card.tone}`} key={card.key} aria-roledescription="card">
          <p className="story__kind">{card.kind}</p>
          <h2 className="story__company">
            {card.company} <span className="story__symbol">{card.symbol}</span>
          </h2>
          <p className="story__figure">{card.figure}</p>
          {card.figureNote && <p className="story__note">{card.figureNote}</p>}
          <p className="story__line">{card.line}</p>
        </article>
      </div>
      <div className="story__controls">
        <button type="button" className="story__nav" onClick={previous} disabled={index === 0}>
          Previous
        </button>
        <button type="button" className="story__dig" onClick={() => onDigIn(card)}>
          {card.target.kind === 'item' ? 'Dig in' : `Research ${card.company}`}
        </button>
        <button type="button" className="story__nav" onClick={next}>
          {last ? 'Done' : 'Next'}
        </button>
      </div>
    </div>
  )
}
