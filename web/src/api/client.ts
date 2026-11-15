// The only code that talks to FINN's API. It keeps the demo session's token in memory (never in
// storage), renews it when it expires or the API answers 401, and rides out the free host's cold
// start: a call that is slow or fails at the network level is retried, with backoff, for up to
// about 90 seconds while the caller is told the server is waking.

import type { DemoSession, Digest, Investor, Snapshot } from './types'
import { type Companies, type Company, parseCompanies, parseCompany } from './pull'
import { ContractError, parseDigest, parseErrorBody, parseHealth, parseSession, parseSnapshot } from './validate'

export interface Timing {
  /** After this long without an answer, the caller is told the call is slow or waking. */
  slowAfterMs: number
  /** How long to keep trying a sleeping server before giving up. */
  wakeBudgetMs: number
  /** Waits between attempts while the server wakes; the last value repeats. */
  backoffMs: readonly number[]
  /** A server heard from within this long is assumed awake (the free host sleeps after 15 idle minutes). */
  awakeForMs: number
  /** Renew the session this long before it expires. */
  renewBeforeMs: number
  /** Time allowed for the saved copy to load. */
  snapshotTimeoutMs: number
}

export const DEFAULT_TIMING: Timing = {
  slowAfterMs: 3_000,
  wakeBudgetMs: 90_000,
  backoffMs: [1_000, 2_000, 4_000, 8_000, 10_000],
  awakeForMs: 14 * 60_000,
  renewBeforeMs: 60_000,
  snapshotTimeoutMs: 8_000,
}

/** 'waking': the server is probably asleep and starting. 'slow': it was awake, but is taking a while. */
export type Progress = 'waking' | 'slow'

export interface CallOptions {
  signal?: AbortSignal | undefined
  onProgress?: ((progress: Progress) => void) | undefined
}

/** --- Controls --- The digest's optional alert settings (docs/API.md), sent as query parameters. */
export interface DigestOptions extends CallOptions {
  params?: Readonly<Record<string, string>> | undefined
}

/** The API answered with an error (the contract's shape, or a bare status). */
export class ApiError extends Error {
  override name = 'ApiError'
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS: number | null = null,
  ) {
    super(message)
  }
}

/** No answer from the API within the waking budget, or the device is offline. */
export class UnreachableError extends Error {
  override name = 'UnreachableError'
  constructor(readonly reason: 'offline' | 'timeout') {
    super(reason === 'offline' ? 'This device is offline.' : "FINN’s server did not answer in time.")
  }
}

/** A gateway or proxy answered for the API (for example while the free host wakes): try again. */
class TransientError extends Error {
  override name = 'TransientError'
}

export interface ApiDeps {
  baseUrl: string
  fetch?: typeof fetch
  timing?: Partial<Timing>
  now?: () => number
  online?: () => boolean
}

export interface Api {
  /** Starts the server waking (a GET /health nobody waits for). */
  prewarm(): void
  digest(hours: number, options?: DigestOptions): Promise<Digest>
  /** The saved copy at /snapshot.json, or null when there is none (or it cannot be read). */
  snapshot(signal?: AbortSignal): Promise<Snapshot | null>
  investor(): Investor | null
  /** --- Network stream --- An authenticated GET of any /v1 path, checked by `parse`; one new
   *  session and one more try if the token is refused. */
  get<T>(path: string, parse: (json: unknown) => T, options?: CallOptions): Promise<T>
  /** Pull: companies matching a symbol or name. */
  companies(query: string, options?: CallOptions): Promise<Companies>
  /** Pull: one company's research page. */
  company(symbol: string, options?: CallOptions): Promise<Company>
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError')
}

/** Seconds from a Retry-After header: a number of seconds or an HTTP date. */
export function parseRetryAfter(header: string | null, nowMs: number): number | null {
  if (header === null || header.trim() === '') return null
  const trimmed = header.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const at = Date.parse(trimmed)
  if (Number.isNaN(at)) return null
  return Math.max(0, Math.ceil((at - nowMs) / 1000))
}

export function createApi(deps: ApiDeps): Api {
  const base = new URL(deps.baseUrl).origin
  const doFetch = deps.fetch ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init))
  const timing: Timing = { ...DEFAULT_TIMING, ...deps.timing }
  const now = deps.now ?? (() => Date.now())
  const online = deps.online ?? (() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  let session: { token: string; expiresAt: number; investor: Investor } | null = null
  let pendingSession: Promise<DemoSession> | null = null
  let lastHeard = Number.NEGATIVE_INFINITY

  function sleep(ms: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError())
        return
      }
      const timer = setTimeout(() => {
        signal?.removeEventListener('abort', onAbort)
        resolve()
      }, ms)
      function onAbort() {
        clearTimeout(timer)
        reject(abortError())
      }
      signal?.addEventListener('abort', onAbort, { once: true })
    })
  }

  /** One HTTP attempt with a time limit, following the caller's abort signal. */
  async function attempt(url: string, init: RequestInit, timeoutMs: number, signal?: AbortSignal): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), Math.max(1, timeoutMs))
    const onAbort = () => controller.abort()
    signal?.addEventListener('abort', onAbort, { once: true })
    try {
      return await doFetch(url, { ...init, signal: controller.signal })
    } catch (error) {
      if (signal?.aborted) throw abortError()
      // Our own time limit, or a network failure (fetch rejects with TypeError, CORS included).
      if (controller.signal.aborted || error instanceof TypeError) throw new TransientError(String(error))
      throw error
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
    }
  }

  /** Reads a response: the parsed body, or the error it stands for. */
  async function read<T>(response: Response, parse: (json: unknown) => T): Promise<T> {
    let body: unknown = undefined
    const type = response.headers.get('content-type') ?? ''
    if (type.includes('json')) {
      try {
        body = await response.json()
      } catch {
        body = undefined
      }
    }
    if (response.ok) {
      // A 2xx that is not JSON did not come from the API (a host's loading page, say).
      if (body === undefined) throw new TransientError(`Non-JSON ${response.status} response`)
      return parse(body)
    }
    const error = parseErrorBody(body)
    if (!error && [502, 503, 504].includes(response.status)) {
      throw new TransientError(`Gateway answered ${response.status}`)
    }
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `FINN’s server answered with HTTP ${response.status}.`,
      parseRetryAfter(response.headers.get('retry-after'), now()),
    )
  }

  /** Polls /health until the server answers, or the deadline passes. */
  async function waitUntilAwake(deadline: number, step: number, signal?: AbortSignal): Promise<number> {
    let index = step
    for (;;) {
      if (!online()) throw new UnreachableError('offline')
      const wait = timing.backoffMs[Math.min(index, timing.backoffMs.length - 1)] ?? 1_000
      index += 1
      if (now() + wait >= deadline) throw new UnreachableError('timeout')
      await sleep(wait, signal)
      try {
        const response = await attempt(`${base}/health`, request('GET'), deadline - now(), signal)
        const health = await read(response, parseHealth).catch((error: unknown) => {
          // The server answered; a health body this app cannot read does not keep it asleep.
          if (error instanceof ContractError) return null
          throw error
        })
        lastHeard = now()
        if (health && !health.db) {
          throw new ApiError(503, 'unavailable', "FINN’s server cannot reach its database right now.")
        }
        return index
      } catch (error) {
        if (!(error instanceof TransientError)) throw error
      }
    }
  }

  /** A call to the API that waits out a cold start. */
  async function call<T>(path: string, init: RequestInit, parse: (json: unknown) => T, options: CallOptions): Promise<T> {
    const { signal, onProgress } = options
    const started = now()
    const deadline = started + timing.wakeBudgetMs
    const awake = started - lastHeard < timing.awakeForMs
    let told = false
    const tell = (progress: Progress) => {
      if (!told) onProgress?.(progress)
      told = told || progress === 'waking'
    }
    const slowTimer = setTimeout(() => tell(awake ? 'slow' : 'waking'), timing.slowAfterMs)
    let step = 0
    try {
      for (;;) {
        if (!online()) throw new UnreachableError('offline')
        try {
          const response = await attempt(`${base}${path}`, init, deadline - now(), signal)
          lastHeard = now()
          return await read(response, parse)
        } catch (error) {
          if (!(error instanceof TransientError)) throw error
          tell('waking')
          step = await waitUntilAwake(deadline, step, signal)
        }
      }
    } finally {
      clearTimeout(slowTimer)
    }
  }

  function request(method: 'GET' | 'POST', token?: string): RequestInit {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    // No cookies, no HTTP cache (responses carry the investor's data), no referrer.
    return { method, headers, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', mode: 'cors' }
  }

  async function ensureSession(options: CallOptions): Promise<string> {
    if (session && session.expiresAt - timing.renewBeforeMs > now()) return session.token
    session = null
    // One request for a new session, however many callers wait for it. It is not cancelled when
    // the caller that started it gives up (a window change, say): the next caller needs it too.
    pendingSession ??= call('/v1/session/demo', request('POST'), parseSession, { onProgress: options.onProgress })
      .then((fresh) => {
        session = { token: fresh.token, expiresAt: Date.parse(fresh.expires_at), investor: fresh.investor }
        return fresh
      })
      .finally(() => {
        pendingSession = null
      })
    const fresh = await untilAborted(pendingSession, options.signal)
    return fresh.token
  }

  function untilAborted<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
    if (!signal) return promise
    if (signal.aborted) return Promise.reject(abortError())
    return new Promise<T>((resolve, reject) => {
      const onAbort = () => reject(abortError())
      signal.addEventListener('abort', onAbort, { once: true })
      promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', onAbort))
    })
  }

  /** An authenticated GET: one new session and one more try if the token has expired. */
  async function authedGet<T>(path: string, parse: (json: unknown) => T, options: CallOptions): Promise<T> {
    const token = await ensureSession(options)
    try {
      return await call(path, request('GET', token), parse, options)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      session = null
      const renewed = await ensureSession(options)
      return await call(path, request('GET', renewed), parse, options)
    }
  }

  return {
    prewarm() {
      void attempt(`${base}/health`, request('GET'), timing.wakeBudgetMs)
        .then((response) => {
          if (response.ok) lastHeard = now()
        })
        .catch(() => undefined)
    },

    async digest(hours, options = {}) {
      const query = new URLSearchParams({ hours: String(hours), ...(options.params ?? {}) })
      const path = `/v1/digest?${query.toString()}`
      const token = await ensureSession(options)
      try {
        return await call(path, request('GET', token), parseDigest, options)
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error
        // Expired or revoked: one new session, one more try.
        session = null
        const renewed = await ensureSession(options)
        return await call(path, request('GET', renewed), parseDigest, options)
      }
    },

    async snapshot(signal) {
      let response: Response
      try {
        response = await attempt('/snapshot.json', { method: 'GET', cache: 'no-cache', credentials: 'same-origin' }, timing.snapshotTimeoutMs, signal)
      } catch (error) {
        if (isAbort(error)) throw error
        return null
      }
      if (!response.ok || !(response.headers.get('content-type') ?? '').includes('json')) return null
      try {
        return parseSnapshot(await response.json())
      } catch (error) {
        if (error instanceof ContractError) console.warn(`[finn] Saved copy ignored: ${error.message}`)
        return null
      }
    },

    investor() {
      return session?.investor ?? null
    },

    companies(query, options = {}) {
      return authedGet(`/v1/companies?q=${encodeURIComponent(query)}`, parseCompanies, options)
    },

    company(symbol, options = {}) {
      return authedGet(`/v1/company/${encodeURIComponent(symbol)}`, parseCompany, options)
    },

    // --- Network stream ---
    get(path, parse, options = {}) {
      return authedGet(path, parse, options)
    },
  }
}
