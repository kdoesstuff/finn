/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_NETWORK_ENABLED?: string
  readonly VITE_SENTRY_DSN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** The deployed commit (Vercel's VERCEL_GIT_COMMIT_SHA, shortened), or "local". */
declare const __FINN_RELEASE__: string
