// Settings fixed at build time (see web/.env.example). The build refuses to run without a valid
// VITE_API_URL (build/deploy-config.ts), so here it is always present.

export interface AppConfig {
  apiUrl: string
  /** True only on the full `finn` deployment. In this slice it changes one label; Network comes later. */
  networkEnabled: boolean
  sentryDsn: string | null
}

export function readConfig(env: ImportMetaEnv = import.meta.env): AppConfig {
  const apiUrl = env.VITE_API_URL
  if (typeof apiUrl !== 'string' || apiUrl === '') {
    throw new Error('VITE_API_URL is not set; the build should have stopped.')
  }
  const dsn = typeof env.VITE_SENTRY_DSN === 'string' ? env.VITE_SENTRY_DSN.trim() : ''
  return {
    apiUrl: new URL(apiUrl).origin,
    networkEnabled: env.VITE_NETWORK_ENABLED === 'true',
    sentryDsn: dsn === '' ? null : dsn,
  }
}
