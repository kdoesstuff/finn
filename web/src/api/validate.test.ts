import { describe, expect, it } from 'vitest'
import { asianPaints, health, liveDigest, quietDigest, session, snapshot } from '../test/fixtures/contract'
import { ContractError, parseDigest, parseErrorBody, parseHealth, parseSession, parseSnapshot } from './validate'

const failsAt = (fn: () => unknown) => {
  try {
    fn()
  } catch (error) {
    if (error instanceof ContractError) return error.path
    throw error
  }
  return null
}

describe('contract checks', () => {
  it("accepts the contract's own examples", () => {
    expect(parseDigest(liveDigest)).toEqual(liveDigest)
    expect(parseDigest(quietDigest)).toEqual(quietDigest)
    expect(parseSession(session)).toEqual(session)
    expect(parseHealth(health)).toEqual(health)
    expect(parseSnapshot(snapshot)).toEqual(snapshot)
  })

  it('ignores fields the contract does not name', () => {
    expect(parseDigest({ ...liveDigest, extra: 1 })).toEqual(liveDigest)
  })

  it('names the field that is wrong', () => {
    expect(failsAt(() => parseDigest({ ...liveDigest, summary: undefined }))).toBe('digest.summary')
    expect(failsAt(() => parseDigest({ ...liveDigest, worth: [{ ...asianPaints, reasons: 'x' }] }))).toBe(
      'digest.worth[0].reasons',
    )
    expect(failsAt(() => parseDigest({ ...liveDigest, worth: [{ ...asianPaints, ts: '6 Nov 2026' }] }))).toBe(
      'digest.worth[0].ts',
    )
    expect(failsAt(() => parseDigest({ ...liveDigest, window: { ...liveDigest.window, hours: 0 } }))).toBe(
      'digest.window.hours',
    )
    expect(failsAt(() => parseDigest({ ...liveDigest, routine: { count: 2, by_kind: { x: -1 } } }))).toBe(
      'digest.routine.by_kind.x',
    )
    expect(failsAt(() => parseDigest(null))).toBe('digest')
  })

  it('accepts a time only with an offset', () => {
    expect(failsAt(() => parseDigest({ ...liveDigest, data_as_of: '2026-11-15T15:07:41' }))).toBe('digest.data_as_of')
    expect(failsAt(() => parseDigest({ ...liveDigest, data_as_of: '2026-11-15T09:37:41Z' }))).toBeNull()
  })

  it('requires a saved copy to say it is one, and when it was made', () => {
    expect(failsAt(() => parseSnapshot(liveDigest))).toBe('snapshot.snapshot')
    expect(failsAt(() => parseSnapshot({ ...snapshot, generated_at: undefined }))).toBe('snapshot.generated_at')
  })

  it('refuses an empty token', () => {
    expect(failsAt(() => parseSession({ ...session, token: '' }))).toBe('session.token')
  })

  it("reads the contract's error shape and nothing else", () => {
    expect(parseErrorBody({ error: { code: 'unauthorised', message: 'Sign in again.' } })).toEqual({
      code: 'unauthorised',
      message: 'Sign in again.',
    })
    expect(parseErrorBody('<html>')).toBeNull()
    expect(parseErrorBody({ error: 'nope' })).toBeNull()
  })
})
