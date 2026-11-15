// Stands in for FINN's API (and the saved copy) in the browser tests. Every request leaving the app
// is answered here or refused: nothing reaches the network.

import type { Page, Request } from '@playwright/test'
import { errorBody, health, liveDigest, NOW, session, snapshot } from '../src/test/fixtures/contract'

export const API = 'https://finn-api.onrender.com'
export const APP = 'http://localhost:4173'
export { NOW }

export interface Reply {
  status?: number
  body?: unknown
  headers?: Record<string, string>
  /** Answer after this many milliseconds. */
  delayMs?: number
}

export interface MockOptions {
  session?: Reply | Reply[]
  digest?: (hours: number, call: number) => Reply
  health?: Reply
  /** The saved copy at /snapshot.json: a body, or 'none' for a 404 (there is none yet). */
  snapshot?: unknown
}

export interface Mock {
  requests: Request[]
  digestHours(): number[]
  sessions(): number
}

const json = (reply: Reply) => ({
  status: reply.status ?? 200,
  contentType: 'application/json',
  headers: { 'access-control-allow-origin': APP, ...reply.headers },
  body: JSON.stringify(reply.body),
})

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function mockApi(page: Page, options: MockOptions = {}): Promise<Mock> {
  const requests: Request[] = []
  let sessionCalls = 0
  let digestCalls = 0

  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.origin === APP) {
      if (url.pathname === '/snapshot.json') {
        const saved = options.snapshot ?? 'none'
        if (saved === 'none') return route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not found' })
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(saved) })
      }
      return route.fallback()
    }
    if (url.origin !== API) return route.abort('blockedbyclient')

    requests.push(request)
    if (request.method() === 'OPTIONS') {
      // The CORS preflight for a request carrying Authorization.
      return route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': APP,
          'access-control-allow-methods': 'GET, POST',
          'access-control-allow-headers': 'authorization, accept',
          'access-control-max-age': '600',
        },
      })
    }

    let reply: Reply
    if (url.pathname === '/health') {
      reply = options.health ?? { body: health }
    } else if (url.pathname === '/v1/session/demo' && request.method() === 'POST') {
      const list = options.session ?? { body: session }
      reply = Array.isArray(list) ? list[Math.min(sessionCalls, list.length - 1)]! : list
      sessionCalls += 1
    } else if (url.pathname === '/v1/digest') {
      const hours = Number(url.searchParams.get('hours'))
      reply = options.digest ? options.digest(hours, digestCalls) : { body: liveDigest }
      digestCalls += 1
    } else {
      reply = { status: 404, body: errorBody('not_found', 'Unknown route') }
    }
    if (reply.delayMs) await pause(reply.delayMs)
    return route.fulfill(json(reply))
  })

  return {
    requests,
    digestHours: () =>
      requests
        .filter((r) => r.method() === 'GET' && new URL(r.url()).pathname === '/v1/digest')
        .map((r) => Number(new URL(r.url()).searchParams.get('hours'))),
    sessions: () => sessionCalls,
  }
}

/** Fixes the page's clock at the tests' "now", then lets it run. */
export async function startClock(page: Page): Promise<void> {
  await page.clock.install({ time: NOW })
  await page.clock.resume()
}

/**
 * Collects console errors, CSP violations among them; the tests expect none. Chrome's own line for
 * an HTTP error status the test asked for (a 404 saved copy, a 503) is not a problem.
 */
export function watchConsole(page: Page): string[] {
  const problems: string[] = []
  page.on('console', (message) => {
    const text = message.text()
    if (message.type() !== 'error') return
    if (/^Failed to load resource: the server responded with a status of (401|404|429|503)/.test(text)) return
    problems.push(text)
  })
  page.on('pageerror', (error) => problems.push(error.message))
  return problems
}

export { snapshot }
