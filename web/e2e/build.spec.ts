// Checks on the production build itself: what the service worker may cache, and that the HTML
// carries nothing the Content-Security-Policy would block.
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { API } from './api'

const dist = (file: string) => readFileSync(new URL(`../dist/${file}`, import.meta.url), 'utf8')

test.describe('production build', () => {
  test.skip(({ isMobile }) => isMobile, 'Build checks run once, not per device.')

  test('the service worker caches the app shell and the saved copy, never the API', () => {
    const sw = dist('sw.js')
    const precached = [...sw.matchAll(/url:"([^"]+)"/g)].map((m) => m[1]!)
    expect(precached).toContain('index.html')
    expect(precached.some((url) => /^assets\/index-.*\.js$/.test(url))).toBe(true)
    expect(precached.some((url) => /sentry/.test(url))).toBe(false)
    expect(new Set(precached).size).toBe(precached.length)
    expect(sw).not.toContain(new URL(API).hostname)
    expect(sw).not.toMatch(/\/v1\//)
    // The only runtime route: /snapshot.json, network first.
    expect([...sw.matchAll(/registerRoute\(/g)]).toHaveLength(2)
    expect(sw).toContain('"/snapshot.json"===')
    expect(sw).toContain('NetworkFirst')
  })

  test('index.html has no inline script or style', () => {
    const html = dist('index.html')
    for (const tag of html.match(/<script\b[^>]*>/g) ?? []) expect(tag).toMatch(/\bsrc="/)
    expect(html).not.toMatch(/<style\b/)
    expect(html).not.toMatch(/\sstyle="/)
  })

  test('the manifest names the app and its icons', () => {
    const manifest = JSON.parse(dist('manifest.webmanifest')) as { name: string; icons: { purpose?: string }[] }
    expect(manifest.name).toBe('FINN')
    expect(manifest.icons.some((icon) => icon.purpose === 'maskable')).toBe(true)
  })
})
