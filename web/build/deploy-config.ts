// Build-time checks on the deployment settings. The build stops with a plain message instead of
// shipping an app that cannot reach its API, or one whose security policy would block it.
//
// The API origin is written in exactly one place for the browser: the connect-src of the
// Content-Security-Policy in web/vercel.json. VITE_API_URL must name an origin listed there.

export interface BuildEnv {
  VITE_API_URL?: string | undefined
  VITE_NETWORK_ENABLED?: string | undefined
  VITE_SENTRY_DSN?: string | undefined
}

export interface VercelHeader {
  key: string
  value: string
}

export interface VercelConfig {
  headers?: { source: string; headers: VercelHeader[] }[]
}

export class ConfigError extends Error {
  override name = 'ConfigError'
}

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

/** The policy every path is served with (the entry whose source is "/(.*)"). */
export function globalHeaders(config: VercelConfig): VercelHeader[] {
  const entry = config.headers?.find((h) => h.source === '/(.*)')
  if (!entry) throw new ConfigError('vercel.json has no headers entry for "/(.*)".')
  return entry.headers
}

export function contentSecurityPolicy(config: VercelConfig): string {
  const csp = globalHeaders(config).find((h) => h.key.toLowerCase() === 'content-security-policy')
  if (!csp) throw new ConfigError('vercel.json sets no Content-Security-Policy for "/(.*)".')
  return csp.value
}

export function directive(csp: string, name: string): string[] {
  for (const part of csp.split(';')) {
    const tokens = part.trim().split(/\s+/)
    if (tokens[0] === name) return tokens.slice(1)
  }
  return []
}

/** Whether a CSP source expression such as https://*.ingest.de.sentry.io allows an origin. */
export function sourceAllows(source: string, origin: URL): boolean {
  const match = /^(https?):\/\/(\*\.)?([^/:]+)$/.exec(source)
  if (!match) return false
  const [, scheme, wildcard, host] = match
  if (`${scheme}:` !== origin.protocol || origin.port !== '' || host === undefined) return false
  if (wildcard) return origin.hostname.endsWith(`.${host}`)
  return origin.hostname === host
}

function parseUrl(name: string, raw: string): URL {
  try {
    return new URL(raw)
  } catch {
    throw new ConfigError(`${name} is not a valid URL: "${raw}".`)
  }
}

export interface DeployConfig {
  apiUrl: string
  networkEnabled: boolean
  sentryDsn: string | null
  warnings: string[]
}

/**
 * Validates the build's environment against vercel.json. Throws ConfigError with a message that
 * says what to change and where.
 */
export function checkDeployConfig(env: BuildEnv, vercel: VercelConfig): DeployConfig {
  const warnings: string[] = []
  const rawApi = env.VITE_API_URL?.trim()
  if (!rawApi) {
    throw new ConfigError(
      'VITE_API_URL is not set. Set it to the API origin, for example https://finn-api-53vw.onrender.com ' +
        '(on Vercel: Settings > Environment Variables; locally: web/.env.local).',
    )
  }
  const api = parseUrl('VITE_API_URL', rawApi)
  const local = LOCAL_HOSTS.has(api.hostname)
  if (api.protocol !== 'https:' && !(local && api.protocol === 'http:')) {
    throw new ConfigError(`VITE_API_URL must use https (got "${rawApi}"). Only localhost may use http.`)
  }
  if (api.pathname !== '/' || api.search || api.hash || api.username || api.password) {
    throw new ConfigError(
      `VITE_API_URL must be an origin only, with no path, query or credentials (got "${rawApi}").`,
    )
  }

  const connect = directive(contentSecurityPolicy(vercel), 'connect-src')
  if (local) {
    warnings.push(
      `VITE_API_URL is ${api.origin}, which vercel.json's connect-src does not list; fine for local ` +
        'use, but this build would be blocked by the security policy if deployed.',
    )
  } else if (!connect.some((source) => sourceAllows(source, api))) {
    throw new ConfigError(
      `VITE_API_URL is ${api.origin}, but web/vercel.json's Content-Security-Policy connect-src ` +
        `(${connect.join(' ')}) does not list it, so browsers would block every API call. ` +
        'Add the origin to connect-src in web/vercel.json, or correct VITE_API_URL.',
    )
  }

  const rawNetwork = env.VITE_NETWORK_ENABLED?.trim() ?? ''
  if (rawNetwork !== '' && rawNetwork !== 'true' && rawNetwork !== 'false') {
    throw new ConfigError(
      `VITE_NETWORK_ENABLED must be "true", "false" or unset (got "${rawNetwork}").`,
    )
  }

  const rawDsn = env.VITE_SENTRY_DSN?.trim() ?? ''
  if (rawDsn !== '') {
    const dsn = parseUrl('VITE_SENTRY_DSN', rawDsn)
    const ingest = new URL(`${dsn.protocol}//${dsn.host}`)
    if (dsn.protocol !== 'https:' || !connect.some((source) => sourceAllows(source, ingest))) {
      throw new ConfigError(
        `VITE_SENTRY_DSN points at ${ingest.origin}, which web/vercel.json's connect-src does not ` +
          'allow, so error reports would be blocked. Add that host to connect-src, or unset the DSN.',
      )
    }
  }

  return {
    apiUrl: api.origin,
    networkEnabled: rawNetwork === 'true',
    sentryDsn: rawDsn === '' ? null : rawDsn,
    warnings,
  }
}
