// A scripted stand-in for FINN's API and the static host, for tests. Each route answers from a
// list of handlers in turn (the last one repeats), and every request is recorded.

import { createApi, type Timing } from '../api/client'

export interface Recorded {
  method: string
  url: URL
  headers: Headers
}

type Handler = (request: Recorded, signal: AbortSignal | undefined) => Response | Promise<Response>

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

export function html(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/html' } })
}

/** A network failure, as fetch reports it (CORS refusals look the same). */
export const networkError: Handler = () => Promise.reject(new TypeError('Failed to fetch'))

/** A request that never answers until it is aborted. */
export const hang: Handler = (_request, signal) =>
  new Promise((_, reject) => {
    signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  })

/** Answers after `ms`. */
export function after(ms: number, respond: () => Response): Handler {
  return (_request, signal) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(respond()), ms)
      signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timer)
          reject(new DOMException('Aborted', 'AbortError'))
        },
        { once: true },
      )
    })
}

export type Routes = Record<string, Handler | Response | (Handler | Response)[]>

export function fakeServer(routes: Routes) {
  const calls: Recorded[] = []
  const served = new Map<string, number>()

  const fetchImpl = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'https://app.finn.test')
    const method = (init?.method ?? 'GET').toUpperCase()
    const request: Recorded = { method, url, headers: new Headers(init?.headers) }
    calls.push(request)
    const signal = init?.signal ?? undefined
    if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
    const key = `${method} ${url.pathname}`
    const route = routes[key]
    if (route === undefined) return Promise.resolve(json({ error: { code: 'not_found', message: `No route ${key}` } }, 404))
    const list = Array.isArray(route) ? route : [route]
    const index = served.get(key) ?? 0
    served.set(key, index + 1)
    const handler = list[Math.min(index, list.length - 1)]!
    if (handler instanceof Response) return Promise.resolve(handler.clone())
    return Promise.resolve().then(() => handler(request, signal))
  }

  return {
    fetch: fetchImpl,
    calls,
    /** Calls to one route, e.g. "GET /v1/digest". */
    callsTo(key: string): Recorded[] {
      return calls.filter((c) => `${c.method} ${c.url.pathname}` === key)
    },
  }
}

/** Short waits, so the waking and fallback paths run in milliseconds. */
export const FAST: Partial<Timing> = {
  slowAfterMs: 40,
  wakeBudgetMs: 600,
  backoffMs: [10, 20, 40],
  snapshotTimeoutMs: 500,
}

export function fakeApi(routes: Routes, options: { timing?: Partial<Timing>; online?: () => boolean; now?: () => number } = {}) {
  const server = fakeServer(routes)
  const api = createApi({
    baseUrl: 'https://api.finn.test',
    fetch: server.fetch,
    timing: { ...FAST, ...options.timing },
    ...(options.online ? { online: options.online } : {}),
    ...(options.now ? { now: options.now } : {}),
  })
  return { api, server }
}
