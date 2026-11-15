// --- Reader stream ---
// What a filing's attachment says, under the headline: one line, and for a management change the
// person it is about. Every sentence here was found in the filing's own text by the pipeline
// (finn.reader); its exact words and page are one tap away, so the reader can check it.

import { useId, useState } from 'react'
import type { Item, NotePerson, QuotedLine } from '../api/types'
import './note.css'

export function Note({ item }: { item: Item }) {
  const note = item.note
  if (!note) return null
  return (
    <div className="reader">
      {note.summary && (
        <Quoted line={{ text: note.summary, quote: note.quote, page: note.page }} className="reader__summary" />
      )}
      {note.person && <PersonCard person={note.person} />}
    </div>
  )
}

/** A sentence with the filing's own words behind a toggle. */
function Quoted({ line, className }: { line: QuotedLine; className: string }) {
  const [open, setOpen] = useState(false)
  const quoteId = useId()
  return (
    <>
      <p className={className}>
        {line.text}{' '}
        <button
          type="button"
          className="action toggle reader__toggle"
          aria-expanded={open}
          aria-controls={quoteId}
          onClick={() => setOpen((was) => !was)}
        >
          The filing’s words, p. {line.page}
        </button>
      </p>
      <blockquote className="reader__quote" id={quoteId} hidden={!open}>
        <p>“{line.quote}”</p>
        <footer className="reader__page">Page {line.page} of the filing</footer>
      </blockquote>
    </>
  )
}

function sentenceCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Who a management change is about: only what the filing states, each line checkable. */
function PersonCard({ person }: { person: NotePerson }) {
  const headingId = useId()
  const what = [sentenceCase(person.action), person.role].filter(Boolean).join(': ')
  return (
    <section className="bio" aria-labelledby={headingId}>
      <h4 className="bio__name" id={headingId}>
        {person.name}
      </h4>
      {(what || person.effective_date) && (
        <p className="bio__meta">
          {[what, person.effective_date && `effective ${person.effective_date}`].filter(Boolean).join(', ')}
        </p>
      )}
      {person.previous_roles.length > 0 && (
        <ul className="bio__roles" aria-label="Earlier roles the filing names">
          {person.previous_roles.map((r, i) => (
            <li key={i}>{r.title ? `${r.title}, ${r.org}` : r.org}</li>
          ))}
        </ul>
      )}
      {person.background.length > 0 && (
        <ul className="bio__background">
          {person.background.map((b, i) => (
            <li key={i}>
              <Quoted line={b} className="bio__line" />
            </li>
          ))}
        </ul>
      )}
      <p className="bio__source">From the filing only: nothing here comes from anywhere else.</p>
    </section>
  )
}
