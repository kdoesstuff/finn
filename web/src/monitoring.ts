// Error reporting, off unless VITE_SENTRY_DSN is set. Sentry is then loaded as its own chunk; the
// service worker does not precache it, so builds without a DSN never download it.
//
// Privacy: no session replay (it would record the investor's screen, and later their network), no
// user details, cookies, headers, bodies or query strings, and no trace headers (see sentry.ts).

type Capture = (error: unknown) => void

let capture: Capture | null = null

export function reportError(error: unknown): void {
  capture?.(error)
}

export async function initMonitoring(dsn: string | null, release: string): Promise<void> {
  if (!dsn) return
  const { startSentry } = await import('./sentry')
  capture = startSentry(dsn, release, import.meta.env.MODE)
}
