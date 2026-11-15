import { useId } from 'react'
import { WINDOWS, type WindowHours } from '../api/types'

interface Props {
  hours: WindowHours
  onChange: (hours: WindowHours) => void
  disabled?: boolean
  note?: string | null
}

/** The brief's window: native radio buttons, so arrow keys and screen readers work as expected. */
export function WindowSelector({ hours, onChange, disabled = false, note = null }: Props) {
  const name = useId()
  const legendId = useId()
  const noteId = useId()
  return (
    <fieldset className="window" disabled={disabled} aria-describedby={note ? noteId : undefined}>
      <legend className="window__legend" id={legendId}>
        Filings from the last
      </legend>
      <div className="window__options">
        {WINDOWS.map((option) => (
          <label key={option.hours} className="window__option">
            <input
              type="radio"
              name={name}
              value={option.hours}
              checked={hours === option.hours}
              onChange={() => onChange(option.hours)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
      {note && (
        <p className="window__note" id={noteId}>
          {note}
        </p>
      )}
    </fieldset>
  )
}
