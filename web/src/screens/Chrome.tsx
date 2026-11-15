import type { MouseEvent } from 'react'

/** A same-app link: an ordinary <a> (so it opens in a new tab when asked) that navigates in place. */
function inPlace(event: MouseEvent<HTMLAnchorElement>, go: () => void) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return
  }
  event.preventDefault()
  go()
}

export function Wordmark({ onHome }: { onHome: () => void }) {
  return (
    <a className="wordmark" href="/" onClick={(event) => inPlace(event, onHome)}>
      FINN<span className="visually-hidden">, about this demo</span>
    </a>
  )
}

/** The page's foot. `onHome` (the brief) adds the demo note, which the introduction already makes. */
export function Colophon({ networkEnabled, onHome }: { networkEnabled: boolean; onHome?: () => void }) {
  return (
    <footer className="colophon">
      {onHome && (
        <p>
          A demo. The companies and their filings are real, read from NSE, and every item links to its filing. The
          holdings are fictional.
        </p>
      )}
      <p>
        {networkEnabled ? 'Full edition, with Network.' : 'Core edition.'}
        {onHome && (
          <>
            {' '}
            <a className="colophon__link" href="/" onClick={(event) => inPlace(event, onHome)}>
              About FINN
            </a>
          </>
        )}
      </p>
    </footer>
  )
}

/** The two sections of the app: the brief (Push) and research (Pull). */
export function SectionNav({ current, navigate }: { current: 'brief' | 'research'; navigate: (to: string) => void }) {
  const links = [
    { key: 'brief', to: '/brief', label: 'Brief' },
    { key: 'research', to: '/research', label: 'Research' },
  ] as const
  return (
    <nav className="sections" aria-label="Sections">
      <ul className="sections__list">
        {links.map((l) => (
          <li key={l.key}>
            <a
              className="sections__link"
              href={l.to}
              aria-current={current === l.key ? 'page' : undefined}
              onClick={(event) => inPlace(event, () => navigate(l.to))}
            >
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
