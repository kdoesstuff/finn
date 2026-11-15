import { useCallback, useEffect, useState } from 'react'
import { ApiError, isAbort, UnreachableError, type Api, type Progress } from '../api/client'
import type { Digest, Snapshot } from '../api/types'
import { ContractError } from '../api/validate'
import { reportError } from '../monitoring'

/** Why the live brief could not be shown. */
export type FailureReason =
  | { kind: 'offline' }
  | { kind: 'unreachable' }
  | { kind: 'unavailable' }
  | { kind: 'server_error'; status: number }
  | { kind: 'contract' }
  | { kind: 'refused'; message: string }

export type Outcome =
  | { kind: 'live'; digest: Digest }
  | { kind: 'snapshot'; snapshot: Snapshot; reason: FailureReason }
  | { kind: 'rate_limited'; retryAt: number }
  | { kind: 'unavailable'; reason: FailureReason }

export interface BriefView {
  /** The latest outcome; while `pending`, it belongs to the previous window or attempt. */
  outcome: Outcome | null
  pending: boolean
  progress: Progress | null
  /** When the request now in progress started (for the waking timer); 0 when there is none. */
  startedAt: number
  retry: () => void
}

export function failureReason(error: unknown): FailureReason {
  if (error instanceof UnreachableError) return { kind: error.reason === 'offline' ? 'offline' : 'unreachable' }
  if (error instanceof ContractError) return { kind: 'contract' }
  if (error instanceof ApiError) {
    if (error.status === 503 && error.code === 'unavailable') return { kind: 'unavailable' }
    if (error.status >= 500) return { kind: 'server_error', status: error.status }
    return { kind: 'refused', message: error.message }
  }
  return { kind: 'unreachable' }
}

const DEFAULT_RETRY_AFTER_S = 30

export function useBrief(api: Api, hours: number): BriefView {
  const [attempt, setAttempt] = useState(0)
  const key = `${hours}#${attempt}`
  const [result, setResult] = useState<{ key: string; outcome: Outcome } | null>(null)
  const [progress, setProgress] = useState<{ key: string; value: Progress; startedAt: number } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const started = Date.now()
    const settle = (outcome: Outcome) => {
      if (!signal.aborted) setResult({ key, outcome })
    }

    api
      .digest(hours, {
        signal,
        onProgress: (value) => {
          if (!signal.aborted) setProgress({ key, value, startedAt: started })
        },
      })
      .then(
        (digest) => settle({ kind: 'live', digest }),
        async (error: unknown) => {
          if (signal.aborted || isAbort(error)) return
          if (error instanceof ApiError && error.status === 429) {
            settle({ kind: 'rate_limited', retryAt: Date.now() + (error.retryAfterS ?? DEFAULT_RETRY_AFTER_S) * 1000 })
            return
          }
          const expected = error instanceof ApiError || error instanceof UnreachableError
          if (!expected) reportError(error)
          const reason = failureReason(error)
          const snapshot = await api.snapshot(signal).catch(() => null)
          settle(snapshot ? { kind: 'snapshot', snapshot, reason } : { kind: 'unavailable', reason })
        },
      )
    return () => controller.abort()
  }, [api, hours, key])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  const current = progress?.key === key ? progress : null
  return {
    outcome: result?.outcome ?? null,
    pending: result?.key !== key,
    progress: current?.value ?? null,
    startedAt: current?.startedAt ?? 0,
    retry,
  }
}
