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
