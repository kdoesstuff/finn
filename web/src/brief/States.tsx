import { useEffect, useRef } from 'react'
import type { Progress } from '../api/client'
import type { Snapshot } from '../api/types'
import { formatStamp } from '../lib/time'
import { useNow } from '../lib/useNow'
import { windowPhrase } from './Summary'
import type { FailureReason } from './useBrief'

const WAKE_BUDGET_S = 90
const WAKE_EXPECTED_S = 60

export function waitingMessage(progress: Progress | null, elapsedS: number): string {
  if (progress === 'waking') {
    if (elapsedS >= WAKE_EXPECTED_S) {
      return `Still waking. If the server has not answered by ${WAKE_BUDGET_S} seconds, FINN will show its saved copy.`
    }
    return "Waking FINN’s server. Free hosting sleeps when idle; this takes up to a minute."
  }
  if (progress === 'slow') return 'Still fetching your brief.'
  return 'Fetching your brief.'
}

/** The message and, while the server wakes, how long it has been. */
export function Waiting({ progress, startedAt }: { progress: Progress | null; startedAt: number }) {
  const now = useNow(1_000)
  const elapsedS = progress === 'waking' ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0
  return (
    <div className="waiting">
      <p className="waiting__message" role="status" aria-live="polite">
        {waitingMessage(progress, elapsedS)}
      </p>
      {progress === 'waking' && (
        <div className="waiting__progress">
          <progress max={WAKE_BUDGET_S} value={Math.min(elapsedS, WAKE_BUDGET_S)} aria-label="Time spent waking the server" />
          <span className="waiting__elapsed" aria-hidden="true">
            {elapsedS} s
          </span>
        </div>
      )}
    </div>
  )
}

/** First load: the message over a blank ledger page. */
export function Loading({ progress, startedAt }: { progress: Progress | null; startedAt: number }) {
  return (
    <div className="loading">
      <Waiting progress={progress} startedAt={startedAt} />
      <div className="blank-ledger" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}

export function reasonText(reason: FailureReason): string {
  switch (reason.kind) {
    case 'offline':
      return 'This device is offline.'
    case 'unreachable':
      return `FINN’s server did not answer within ${WAKE_BUDGET_S} seconds.`
    case 'unavailable':
      return "FINN’s server is running but cannot reach its database."
    case 'server_error':
      return `FINN’s server answered with an error (HTTP ${reason.status}).`
    case 'contract':
      return "FINN’s server sent a brief this version of the app cannot read."
    case 'refused':
      return `FINN’s server refused the request: ${reason.message}`
  }
}

/** Moves focus to a state's heading when it replaces the content, so screen readers hear it. */
function useFocusOnShow<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return ref
}

export function Unavailable({ reason, onRetry }: { reason: FailureReason; onRetry: () => void }) {
  const heading = useFocusOnShow<HTMLHeadingElement>()
  return (
    <section className="problem" aria-labelledby="problem-heading">
      <h2 className="problem__title" id="problem-heading" tabIndex={-1} ref={heading}>
        The brief could not be loaded
      </h2>
      <p>{reasonText(reason)}</p>
      <p>The app has no saved copy of the brief yet, so there is nothing to show instead.</p>
      <button type="button" className="button" onClick={onRetry}>
        Try again
      </button>
    </section>
  )
}

export function RateLimited({ retryAt, onRetry }: { retryAt: number; onRetry: () => void }) {
  const heading = useFocusOnShow<HTMLHeadingElement>()
  const now = useNow(1_000)
  const seconds = Math.max(0, Math.ceil((retryAt - now) / 1000))
  const retried = useRef(false)
  useEffect(() => {
    // One automatic try when the wait is over; the button stays for anyone who wants it sooner.
    if (seconds === 0 && !retried.current) {
      retried.current = true
      onRetry()
    }
  }, [seconds, onRetry])
  return (
    <section className="problem" aria-labelledby="problem-heading">
      <h2 className="problem__title" id="problem-heading" tabIndex={-1} ref={heading}>
        Too many requests
      </h2>
      <p>FINN’s server limits how often one device can ask in a minute.</p>
      <p>
        {seconds > 0
          ? `FINN will ask again in ${seconds} ${seconds === 1 ? 'second' : 'seconds'}.`
          : 'Asking again now.'}
      </p>
      <button type="button" className="button" onClick={onRetry}>
        Try again now
      </button>
    </section>
  )
}

/** The saved copy's label: when it was made, why it is showing, and the way back to live. */
export function SavedCopyBanner({ snapshot, reason, onRetry }: { snapshot: Snapshot; reason: FailureReason; onRetry: () => void }) {
  return (
    <aside className="saved" aria-labelledby="saved-heading">
      <h2 className="saved__title" id="saved-heading">
        Saved copy from {formatStamp(snapshot.generated_at)} IST
      </h2>
      <p className="saved__text">
        {reasonText(reason)} This is the last brief saved with the app, covering the{' '}
        {windowPhrase(snapshot.window.hours)} to {formatStamp(snapshot.window.to)}.
      </p>
      <button type="button" className="button button--quiet" onClick={onRetry}>
        Try the live brief
      </button>
    </aside>
  )
}
