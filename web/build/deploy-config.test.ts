// @vitest-environment node
import { readFileSync } from 'node:fs'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'
import { checkDeployConfig, ConfigError, contentSecurityPolicy, directive, globalHeaders, type VercelConfig } from './deploy-config.ts'
import { paper } from './theme.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const vercel = JSON.parse(read('../vercel.json')) as VercelConfig & {
  rewrites: { source: string; destination: string }[]
}
const API = 'https://finn-api-53vw.onrender.com'

function fails(env: Parameters<typeof checkDeployConfig>[0]): string {
  try {
    checkDeployConfig(env, vercel)
  } catch (error) {
    if (error instanceof ConfigError) return error.message
    throw error
  }
  return ''
}

describe('build settings', () => {
  it('stops the build without VITE_API_URL, saying what to set', () => {
    expect(fails({})).toMatch(/^VITE_API_URL is not set\. Set it to the API origin/)
    expect(fails({ VITE_API_URL: '  ' })).toMatch(/VITE_API_URL is not set/)
  })

  it('accepts the production API, with or without a trailing slash', () => {
    expect(checkDeployConfig({ VITE_API_URL: API }, vercel)).toEqual({
      apiUrl: API,
      networkEnabled: false,
      sentryDsn: null,
      warnings: [],
    })
    expect(checkDeployConfig({ VITE_API_URL: `${API}/`, VITE_NETWORK_ENABLED: 'true' }, vercel).networkEnabled).toBe(true)
  })

  it('refuses an API the security policy would block, plain http, or a path', () => {
    expect(fails({ VITE_API_URL: 'https://other-api.onrender.com' })).toMatch(/does not list it/)
    expect(fails({ VITE_API_URL: 'http://finn-api-53vw.onrender.com' })).toMatch(/must use https/)
    expect(fails({ VITE_API_URL: `${API}/v1` })).toMatch(/origin only/)
    expect(fails({ VITE_API_URL: 'not a url' })).toMatch(/not a valid URL/)
  })

  it('allows localhost for local work, with a warning', () => {
    const checked = checkDeployConfig({ VITE_API_URL: 'http://localhost:8000' }, vercel)
    expect(checked.warnings[0]).toMatch(/would be blocked by the security policy if deployed/)
  })

  it('accepts only "true", "false" or nothing for the Network switch', () => {
    expect(fails({ VITE_API_URL: API, VITE_NETWORK_ENABLED: 'yes' })).toMatch(/must be "true", "false" or unset/)
    expect(fails({ VITE_API_URL: API, VITE_NETWORK_ENABLED: 'True' })).toMatch(/must be "true", "false" or unset/)
  })

  it('accepts a Sentry DSN only on a host the policy allows', () => {
    const dsn = 'https://abc123@o4510000000000000.ingest.de.sentry.io/4510000000000001'
    expect(checkDeployConfig({ VITE_API_URL: API, VITE_SENTRY_DSN: dsn }, vercel).sentryDsn).toBe(dsn)
    expect(fails({ VITE_API_URL: API, VITE_SENTRY_DSN: 'https://abc@o1.ingest.us.sentry.io/2' })).toMatch(
      /connect-src does not allow/,
    )
  })
})

describe('vercel.json', () => {
  const csp = contentSecurityPolicy(vercel)

  it('sends a strict Content-Security-Policy on every path', () => {
    expect(directive(csp, 'default-src')).toEqual(["'self'"])
    expect(directive(csp, 'script-src')).toEqual(["'self'"])
    expect(directive(csp, 'style-src')).toEqual(["'self'"])
    expect(directive(csp, 'img-src')).toEqual(["'self'", 'data:'])
    expect(directive(csp, 'font-src')).toEqual(["'self'"])
    expect(directive(csp, 'connect-src')).toEqual(["'self'", API, 'https://*.ingest.de.sentry.io'])
    expect(directive(csp, 'frame-ancestors')).toEqual(["'none'"])
    expect(directive(csp, 'base-uri')).toEqual(["'self'"])
    expect(directive(csp, 'form-action')).toEqual(["'self'"])
    expect(directive(csp, 'object-src')).toEqual(["'none'"])
    expect(csp).not.toMatch(/unsafe-inline|unsafe-eval|\*;|https:;/)
  })

  it('names the API origin exactly once', () => {
    expect(read('../vercel.json').split(API)).toHaveLength(2)
  })

  it('sends the other security headers on every path', () => {
    const headers = Object.fromEntries(globalHeaders(vercel).map((h) => [h.key, h.value]))
    expect(headers['Strict-Transport-Security']).toMatch(/^max-age=\d{8,}; includeSubDomains$/)
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(headers['Referrer-Policy']).toBe('no-referrer')
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['Permissions-Policy']).toMatch(/camera=\(\)/)
    expect(headers['Permissions-Policy']).toMatch(/geolocation=\(\)/)
  })

  it('rewrites client routes to the app, but never a file (a missing snapshot.json stays a 404)', () => {
    const [rewrite] = vercel.rewrites
    expect(rewrite!.destination).toBe('/index.html')
    const pattern = new RegExp(`^${rewrite!.source}$`)
    expect(pattern.test('/brief')).toBe(true)
    expect(pattern.test('/')).toBe(true)
    expect(pattern.test('/snapshot.json')).toBe(false)
    expect(pattern.test('/assets/index-abc.js')).toBe(false)
  })
})

describe('design tokens', () => {
  it('keeps the manifest and theme-color in step with --paper', () => {
    const tokens = read('../src/styles/tokens.css')
    const [light, dark] = [...tokens.matchAll(/--paper:\s*(#[0-9A-Fa-f]{6})/g)].map((m) => m[1])
    expect([light, dark]).toEqual([paper.light, paper.dark])
    const html = read('../index.html')
    expect(html).toContain(`content="${paper.light}" media="(prefers-color-scheme: light)"`)
    expect(html).toContain(`content="${paper.dark}" media="(prefers-color-scheme: dark)"`)
  })

  it('uses colours only from tokens.css', () => {
    for (const file of ['../src/styles/base.css', '../src/styles/brief.css']) {
      expect(read(file), file).not.toMatch(/#[0-9A-Fa-f]{3,8}\b|rgba?\(|hsla?\(/)
    }
  })
})

describe('lint rules', () => {
  // With CI=true (as on GitHub's runners) typescript-eslint assumes a one-off run and lints the files
  // as they are on disk, ignoring the text given here; the test would then lint the real, clean
  // Summary.tsx and see nothing. Turning that inference off makes it lint this text, everywhere.
  const eslint = new ESLint({
    cwd: new URL('..', import.meta.url).pathname,
    overrideConfig: { languageOptions: { parserOptions: { disallowAutomaticSingleRunInference: true } } },
  })
  // Linted as if it were a file of the app (the text replaces the file's contents; nothing is written).
  const lint = async (code: string) => {
    const [result] = await eslint.lintText(code, { filePath: 'src/brief/Summary.tsx' })
    return result!.messages.map((m) => m.message)
  }

  it('refuses HTML injection and inline styles', async () => {
    expect(await lint('export const A = () => <div dangerouslySetInnerHTML={{ __html: "x" }} />\n')).toContain(
      'No dangerouslySetInnerHTML: render text as text.',
    )
    expect(await lint('export function f(el: HTMLElement) {\n  el.innerHTML = "x"\n}\n')).toContain(
      'No innerHTML or outerHTML: build elements, or render text as text.',
    )
    expect(await lint("export function f(el: HTMLElement) {\n  el.insertAdjacentHTML('beforeend', 'x')\n}\n")).toContain(
      'No insertAdjacentHTML.',
    )
    expect(await lint('export const A = () => <div style={{ color: "red" }} />\n')).toContain(
      'No inline styles: use a class and tokens.css (the CSP allows stylesheets from the app only).',
    )
    expect((await lint('export const t = localStorage.getItem("token")\n')).join(' ')).toMatch(/stays in memory/)
  })
})
