import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  CATEGORIES,
  DEFAULT_SETTINGS,
  MOVE_PCT,
  MOVE_RULES,
  VOLUME_MULTIPLE,
  parseSettings,
  type AlertSettings,
} from './alerts'
import './settings.css'

interface Props {
  current: AlertSettings | null
  onSave: (next: AlertSettings) => void
  onReset: () => void
  onClose: () => void
  /** Whether the device can keep settings between visits. */
  persistent: boolean
}

/**
 * The investor decides what is worth an alert: which announcement types, and what an unusual day's
 * price move or volume is. A modal sheet: focus moves in on open, Escape and the close button leave,
 * and focus returns to the button that opened it.
 */
export function AlertSettingsSheet({ current, onSave, onReset, onClose, persistent }: Props) {
  const [draft, setDraft] = useState<AlertSettings>(() => current ?? DEFAULT_SETTINGS)
  const titleId = useId()
  const pctId = useId()
  const volId = useId()
  const sheet = useRef<HTMLDivElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  // The parent may pass a new onClose on every render; the focus handling below must run once.
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  }, [onClose])

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    heading.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current()
      if (event.key === 'Tab' && sheet.current) {
        const focusable = sheet.current.querySelectorAll<HTMLElement>('button, input, [tabindex="-1"]')
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      opener?.focus()
    }
  }, [])

  const toggle = (id: string) =>
    setDraft((d) => ({ ...d, alerts: d.alerts.includes(id) ? d.alerts.filter((a) => a !== id) : [...d.alerts, id] }))

  // On document.body, above every card: the masthead it is opened from makes its own stacking context.
  return createPortal(
    <div className="sheet-scrim" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={sheet}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="sheet__title" id={titleId} tabIndex={-1} ref={heading}>
          Your alerts
        </h2>
        <p className="sheet__lead">
          You decide what is worth an alert. Items that match are marked “On your alert list”; moves beyond your
          thresholds are flagged and tied to the filing that explains them.
        </p>

        <fieldset className="sheet__group">
          <legend className="sheet__legend">Announcements that are alerts</legend>
          <ul className="sheet__toggles">
            {CATEGORIES.map((c) => (
              <li key={c.id}>
                <label className="sheet__toggle">
                  <input type="checkbox" checked={draft.alerts.includes(c.id)} onChange={() => toggle(c.id)} />
                  <span className="sheet__toggle-label">{c.label}</span>
                  <span className="sheet__hint">{c.hint}</span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>

        <fieldset className="sheet__group">
          <legend className="sheet__legend">An unusual day</legend>
          <label className="sheet__field" htmlFor={pctId}>
            <span>
              Price moves more than <strong>±{draft.movePct}%</strong> in a day
            </span>
            <input
              id={pctId}
              type="range"
              min={MOVE_PCT.min}
              max={MOVE_PCT.max}
              step={MOVE_PCT.step}
              value={draft.movePct}
              onChange={(e) => setDraft((d) => parseSettings({ ...d, movePct: Number(e.target.value) }))}
            />
          </label>
          <label className="sheet__field" htmlFor={volId}>
            <span>
              Volume above <strong>{draft.volumeMultiple}×</strong> its 20-day average
            </span>
            <input
              id={volId}
              type="range"
              min={VOLUME_MULTIPLE.min}
              max={VOLUME_MULTIPLE.max}
              step={VOLUME_MULTIPLE.step}
              value={draft.volumeMultiple}
              onChange={(e) => setDraft((d) => parseSettings({ ...d, volumeMultiple: Number(e.target.value) }))}
            />
          </label>
          <div className="sheet__rules" role="radiogroup" aria-label="Which price moves count">
            {MOVE_RULES.map((r) => (
              <label key={r.id} className="sheet__toggle">
                <input
                  type="radio"
                  name="move-rule"
                  checked={draft.moveRule === r.id}
                  onChange={() => setDraft((d) => ({ ...d, moveRule: r.id }))}
                />
                <span className="sheet__toggle-label">{r.label}</span>
                <span className="sheet__hint">{r.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {!persistent && (
          <p className="note">This device will not keep these settings after you close the page.</p>
        )}
        <div className="sheet__actions">
          <button className="button button--primary" type="button" onClick={() => onSave(parseSettings(draft))}>
            Save and refresh the brief
          </button>
          <button
            className="action"
            type="button"
            onClick={() => {
              setDraft(DEFAULT_SETTINGS)
              onReset()
            }}
          >
            Use FINN’s defaults
          </button>
          <button className="action" type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
