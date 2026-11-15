import { useId, useState } from 'react'
import type { Digest } from '../api/types'
import { routineKinds } from '../lib/labels'

/** Paperwork, counted rather than listed: one line that opens to counts by kind. */
export function Routine({ routine }: { routine: Digest['routine'] }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const headingId = useId()
  if (routine.count === 0) return null
  const kinds = routineKinds(routine.by_kind)
  const itemised = kinds.reduce((sum, kind) => sum + kind.count, 0)
  const remainder = routine.count - itemised

  return (
    <section className="routine" aria-labelledby={headingId}>
      <h2 className="visually-hidden" id={headingId}>
        Routine filings
      </h2>
      <button
        type="button"
        className="routine__toggle toggle"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
      >
        {routine.count} routine {routine.count === 1 ? 'filing' : 'filings'} set aside
      </button>
      <div id={listId} hidden={!open}>
        {kinds.length > 0 ? (
          <ul className="routine__list">
            {kinds.map(({ kind, count, phrase }) => (
              <li key={kind}>
                <span className="routine__count">{count}</span> {phrase}
              </li>
            ))}
            {remainder > 0 && (
              <li>
                <span className="routine__count">{remainder}</span> not broken down by kind
              </li>
            )}
          </ul>
        ) : (
          <p className="routine__none">FINN did not record what kinds they were.</p>
        )}
        <p className="routine__why">
          FINN ranks these as paperwork: meeting schedules, notices, certificates and newspaper copies.
        </p>
      </div>
    </section>
  )
}
