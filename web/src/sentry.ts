// Loaded only when VITE_SENTRY_DSN is set (see monitoring.ts). Named imports, so the bundler keeps
// only what is used: no session replay, no feedback widget.
import { browserTracingIntegration, captureException, init } from '@sentry/react'

export function startSentry(dsn: string, release: string, environment: string): (error: unknown) => void {
  init({
    dsn,
    release,
    environment,
    // Sentry 11 removed `sendDefaultPii`; `dataCollection` replaces it, and its defaults collect
    // user details, cookies, headers, bodies and query strings. Every category is switched off.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
    },
    integrations: [browserTracingIntegration()],
    tracesSampleRate: 0.2,
    // No trace headers on any request: the API's CORS allow-list does not accept them.
    tracePropagationTargets: [],
    beforeBreadcrumb(breadcrumb) {
      // Console output can quote API messages; it is not needed to debug a crash.
      return breadcrumb.category === 'console' ? null : breadcrumb
    },
  })
  return (error) => {
    captureException(error)
  }
}
