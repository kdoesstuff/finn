import { useId, useState } from 'react'
import { WINDOWS } from '../api/types'
import { earliestDate, istDate, sinceLabel, validSince, type BriefWindow } from '../settings/window'
import '../settings/settings.css'

interface Props {
  value: BriefWindow
  onChange: (next: BriefWindow) => void
  nowMs: number
  disabled?: boolean
  note?: string | null
}

/** A sensible first "since" date: the start of this month, or 7 days back early in a month. */
function firstSince(nowMs: number): string {
  const today = istDate(nowMs)
  const monthStart = `${today.slice(0, 8)}01`
  const weekBack = istDate(nowMs - 7 * 86_400_000)
  return monthStart < weekBack ? monthStart : weekBack
}

/**
 * The brief's window: native radio buttons (arrow keys and screen readers work as expected) for the
 * quick choices, and "Since…" with a native date picker, from 31 days back (the API's limit) to today.
 */
export function WindowSelector({ value, onChange, nowMs, disabled = false, note = null }: Props) {
  const name = useId()
  const legendId = useId()
  const noteId = useId()
  const dateId = useId()
  const [draft, setDraft] = useState(() => (value.kind === 'since' ? value.date : firstSince(nowMs)))
  const min = earliestDate(nowMs)
  const max = istDate(nowMs)
  const sinceOn = value.kind === 'since'
  const draftOk = validSince(draft, nowMs)
  return (
    <fieldset className="window" disabled={disabled} aria-describedby={note ? noteId : undefined}>
      <legend className="window__legend" id={legendId}>
        Filings from
      </legend>
      <div className="window__options">
        {WINDOWS.map((option) => (
          <label key={option.hours} className="window__option">
            <input
              type="radio"
              name={name}
              value={option.param}
              checked={value.kind === 'preset' && value.hours === option.hours}
              onChange={() => onChange({ kind: 'preset', hours: option.hours })}
            />
            <span>{option.label}</span>
          </label>
        ))}
        <label className="window__option">
          <input
            type="radio"
            name={name}
            value="since"
            checked={sinceOn}
            onChange={() => {
              const date = draftOk ? draft : firstSince(nowMs)
              setDraft(date)
              onChange({ kind: 'since', date })
            }}
          />
          <span>Since…</span>
        </label>
      </div>
      {sinceOn && (
        <div className="window__since">
          <label htmlFor={dateId} className="window__since-label">
            Since the start of
          </label>
          <input
            id={dateId}
            className="window__date"
            type="date"
            min={min}
            max={max}
            value={draft}
            aria-invalid={!draftOk}
            onChange={(event) => {
              const date = event.target.value
              setDraft(date)
              if (validSince(date, nowMs)) onChange({ kind: 'since', date })
            }}
          />
          <p className="window__note" role="status">
            {draftOk
              ? `Every filing since ${sinceLabel(draft)}, 00:00 IST, up to now.`
              : `Pick a day from ${sinceLabel(min)} to today: FINN reads back 31 days at most.`}
          </p>
        </div>
      )}
      {note && (
        <p className="window__note" id={noteId}>
          {note}
        </p>
      )}
    </fieldset>
  )
}
