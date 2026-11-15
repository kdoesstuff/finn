import { describe, expect, it, vi } from 'vitest'
import { after, fakeApi, hang, html, json, networkError } from '../test/fakeServer'
import { digestFor, errorBody, health, liveDigest, session, snapshot } from '../test/fixtures/contract'
import { ApiError, parseRetryAfter, UnreachableError } from './client'
import { ContractError } from './validate'

const SESSION = 'POST /v1/session/demo'
const DIGEST = 'GET /v1/digest'
const HEALTH = 'GET /health'
const SNAPSHOT = 'GET /snapshot.json'

describe('session', () => {
  it('starts a demo session, then sends its token as a bearer header', async () => {
    const { api, server } = fakeApi({ [SESSION]: json(session), [DIGEST]: json(liveDigest) })
    const digest = await api.digest(24)
    expect(digest.summary).toBe(liveDigest.summary)
    const [start] = server.callsTo(SESSION)
    expect(start!.url.href).toBe('https://api.finn.test/v1/session/demo')
    const [read] = server.callsTo(DIGEST)
    expect(read!.headers.get('authorization')).toBe('Bearer test-token-1')
    expect(read!.url.searchParams.get('hours')).toBe('24')
    expect(api.investor()).toEqual(session.investor)
  })

  it('keeps the token in memory only', async () => {
    const { api } = fakeApi({ [SESSION]: json(session), [DIGEST]: json(liveDigest) })
    await api.digest(24)
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
    expect(document.cookie).toBe('')
  })

  it('reuses a valid session', async () => {
    const { api, server } = fakeApi({ [SESSION]: json(session), [DIGEST]: json(liveDigest) })
    await api.digest(24)
    await api.digest(72)
    expect(server.callsTo(SESSION)).toHaveLength(1)
    expect(server.callsTo(DIGEST).map((c) => c.url.searchParams.get('hours'))).toEqual(['24', '72'])
  })

  it('asks for a new session when the old one has expired', async () => {
    let clock = Date.parse('2026-11-15T15:00:00+05:30')
    const { api, server } = fakeApi(
      { [SESSION]: [json(session), json({ ...session, token: 'test-token-2' })], [DIGEST]: json(liveDigest) },
      { now: () => clock },
    )
    await api.digest(24)
    clock = Date.parse(session.expires_at) + 1_000
    await api.digest(24)
    expect(server.callsTo(SESSION)).toHaveLength(2)
    expect(server.callsTo(DIGEST)[1]!.headers.get('authorization')).toBe('Bearer test-token-2')
  })

  it('on 401 starts one new session and tries once more', async () => {
    const { api, server } = fakeApi({
      [SESSION]: [json(session), json({ ...session, token: 'test-token-2' })],
      [DIGEST]: [json(errorBody('unauthorised', 'Sign in again: your session has expired.'), 401), json(liveDigest)],
    })
    await expect(api.digest(24)).resolves.toEqual(liveDigest)
    expect(server.callsTo(SESSION)).toHaveLength(2)
    expect(server.callsTo(DIGEST).map((c) => c.headers.get('authorization'))).toEqual([
      'Bearer test-token-1',
      'Bearer test-token-2',
    ])
  })

  it('gives up after a second 401', async () => {
    const { api, server } = fakeApi({
      [SESSION]: json(session),
      [DIGEST]: json(errorBody('unauthorised', 'Sign in again: your session has expired.'), 401),
    })
    await expect(api.digest(24)).rejects.toMatchObject({ status: 401, code: 'unauthorised' })
    expect(server.callsTo(DIGEST)).toHaveLength(2)
  })

  it('shares one session request between callers', async () => {
    const { api, server } = fakeApi({ [SESSION]: after(20, () => json(session)), [DIGEST]: json(liveDigest) })
    await Promise.all([api.digest(24), api.digest(72)])
    expect(server.callsTo(SESSION)).toHaveLength(1)
  })
})

describe('errors', () => {
  it('reports 429 with the Retry-After seconds', async () => {
    const { api } = fakeApi({
      [SESSION]: json(session),
      [DIGEST]: json(errorBody('rate_limited', 'Too many requests.'), 429, { 'Retry-After': '42' }),
    })
    const error = await api.digest(24).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 429, code: 'rate_limited', retryAfterS: 42 })
  })

  it('does not wait out a 503 from the API itself: the database is down, not the server', async () => {
    const { api, server } = fakeApi({
      [SESSION]: json(session),
      [DIGEST]: json(errorBody('unavailable', 'The database is unreachable.'), 503),
    })
    await expect(api.digest(24)).rejects.toMatchObject({ status: 503, code: 'unavailable' })
    expect(server.callsTo(DIGEST)).toHaveLength(1)
    expect(server.callsTo(HEALTH)).toHaveLength(0)
  })

  it('passes on the API message for a refused request', async () => {
    const { api } = fakeApi({
      [SESSION]: json(session),
      [DIGEST]: json(errorBody('bad_request', 'hours must be between 1 and 744'), 422),
    })
    await expect(api.digest(24)).rejects.toMatchObject({ status: 422, message: 'hours must be between 1 and 744' })
  })

  it('refuses a digest that does not match the contract', async () => {
    const { api } = fakeApi({ [SESSION]: json(session), [DIGEST]: json({ ...liveDigest, attention: 'none' }) })
    const error = await api.digest(24).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ContractError)
    expect((error as ContractError).path).toBe('digest.attention')
  })

  it('stops at once when the caller aborts', async () => {
    const { api } = fakeApi({ [SESSION]: json(session), [DIGEST]: hang })
    const controller = new AbortController()
    const pending = api.digest(24, { signal: controller.signal })
    setTimeout(() => controller.abort(), 10)
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('waking a sleeping server', () => {
  it('says the server is waking when the first call is slow, then answers', async () => {
    const onProgress = vi.fn()
    const { api } = fakeApi({ [SESSION]: after(80, () => json(session)), [DIGEST]: json(liveDigest) })
    await expect(api.digest(24, { onProgress })).resolves.toEqual(liveDigest)
    expect(onProgress).toHaveBeenCalledWith('waking')
  })

  it('polls /health after network failures and retries once the server is up', async () => {
    const onProgress = vi.fn()
    const { api, server } = fakeApi({
      [SESSION]: [networkError, json(session)],
      [HEALTH]: [networkError, json(health)],
      [DIGEST]: json(liveDigest),
    })
    await expect(api.digest(24, { onProgress })).resolves.toEqual(liveDigest)
    expect(onProgress).toHaveBeenCalledWith('waking')
    expect(server.callsTo(HEALTH)).toHaveLength(2)
    expect(server.callsTo(SESSION)).toHaveLength(2)
  })

  it("treats a host's own page (a 502, or a 200 that is not JSON) as still waking", async () => {
    const { api, server } = fakeApi({
      [SESSION]: [html('<p>Bad gateway</p>', 502), html('<p>Service waking up</p>', 200), json(session)],
      [HEALTH]: json(health),
      [DIGEST]: json(liveDigest),
    })
    await expect(api.digest(24)).resolves.toEqual(liveDigest)
    expect(server.callsTo(SESSION)).toHaveLength(3)
  })

  it('gives up when the waking budget runs out', async () => {
    const { api } = fakeApi({ [SESSION]: networkError, [HEALTH]: networkError }, { timing: { wakeBudgetMs: 120 } })
    const error = await api.digest(24).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(UnreachableError)
    expect((error as UnreachableError).reason).toBe('timeout')
  })

  it('gives up when a call hangs past the budget', async () => {
    const { api } = fakeApi({ [SESSION]: hang, [HEALTH]: hang }, { timing: { wakeBudgetMs: 150 } })
    await expect(api.digest(24)).rejects.toBeInstanceOf(UnreachableError)
  })

  it('falls back at once when /health says the database is unreachable', async () => {
    const { api } = fakeApi({ [SESSION]: networkError, [HEALTH]: json({ ...health, db: false }) })
    await expect(api.digest(24)).rejects.toMatchObject({ status: 503, code: 'unavailable' })
  })

  it('does not wait when the device is offline', async () => {
    const { api, server } = fakeApi({ [SESSION]: json(session) }, { online: () => false })
    const error = await api.digest(24).catch((e: unknown) => e)
    expect((error as UnreachableError).reason).toBe('offline')
    expect(server.calls).toHaveLength(0)
  })

  it('calls a slow answer "slow", not "waking", when the server was just heard from', async () => {
    const onProgress = vi.fn()
    const { api } = fakeApi({ [SESSION]: json(session), [DIGEST]: [json(liveDigest), after(80, () => json(digestFor(72)))] })
    await api.digest(24)
    await api.digest(72, { onProgress })
    expect(onProgress).toHaveBeenCalledWith('slow')
    expect(onProgress).not.toHaveBeenCalledWith('waking')
  })

  it('knocks on /health to start the server waking', async () => {
    const { api, server } = fakeApi({ [HEALTH]: json(health) })
    api.prewarm()
    await vi.waitFor(() => expect(server.callsTo(HEALTH)).toHaveLength(1))
  })
})

describe('saved copy', () => {
  it('reads a valid snapshot', async () => {
    const { api, server } = fakeApi({ [SNAPSHOT]: json(snapshot) })
    await expect(api.snapshot()).resolves.toEqual(snapshot)
    expect(server.callsTo(SNAPSHOT)[0]!.url.origin).toBe('https://app.finn.test')
  })

  it('returns null when there is none yet (404)', async () => {
    const { api } = fakeApi({ [SNAPSHOT]: new Response('Not found', { status: 404 }) })
    await expect(api.snapshot()).resolves.toBeNull()
  })

  it("returns null for a page that is not JSON (a host's fallback HTML)", async () => {
    const { api } = fakeApi({ [SNAPSHOT]: html('<!doctype html><title>FINN</title>') })
    await expect(api.snapshot()).resolves.toBeNull()
  })

  it('ignores a snapshot that does not match the contract', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const { api } = fakeApi({ [SNAPSHOT]: json({ ...snapshot, snapshot: false }) })
    await expect(api.snapshot()).resolves.toBeNull()
    expect(warn).toHaveBeenCalled()
  })

  it('returns null when the network fails', async () => {
    const { api } = fakeApi({ [SNAPSHOT]: networkError })
    await expect(api.snapshot()).resolves.toBeNull()
  })
})

describe('parseRetryAfter', () => {
  it('reads seconds and HTTP dates', () => {
    const now = Date.parse('2026-11-15T10:00:00Z')
    expect(parseRetryAfter('30', now)).toBe(30)
    expect(parseRetryAfter('Sun, 15 Nov 2026 10:00:45 GMT', now)).toBe(45)
    expect(parseRetryAfter(null, now)).toBeNull()
    expect(parseRetryAfter('soon', now)).toBeNull()
  })
})
