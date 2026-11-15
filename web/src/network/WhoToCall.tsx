import { useId, useState } from 'react'
import type { WhoToCall as Person } from '../api/types'

/** Full edition: the people in the investor's network best placed to explain a brief item. */
export function WhoToCall({ people, company }: { people: Person[]; company: string }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  if (people.length === 0) return null
  return (
    <div className="who">
      <button
        type="button"
        className="action toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        Who in your network can explain this ({people.length})
      </button>
      <div className="panel" id={panelId} hidden={!open}>
        <ul className="related">
          {people.map((p) => (
            <li key={p.person_id} className="related__item">
              <p className="related__headline">
                {p.name}
                <span className="related__label">
                  {p.degree === 1 ? 'Your contact' : p.via ? `Through ${p.via}` : 'Second degree'}
                </span>
              </p>
              <p className="related__meta">{p.why}</p>
              {p.caution && <p className="note">{p.caution}</p>}
            </li>
          ))}
        </ul>
        <p className="panel__source">
          From your network (synthetic for this demo).{' '}
          <a href={`/network?q=${encodeURIComponent(`Who can explain ${company}?`)}`}>Ask your network</a>
        </p>
      </div>
    </div>
  )
}
