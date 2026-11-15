/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import { checkDeployConfig, type VercelConfig } from './build/deploy-config.ts'
import { paper } from './build/theme.ts'

const root = fileURLToPath(new URL('.', import.meta.url))
const vercel = JSON.parse(readFileSync(new URL('./vercel.json', import.meta.url), 'utf8')) as VercelConfig

// `vite preview` serves the production build with the same headers Vercel will send, so the
// end-to-end tests run under the real Content-Security-Policy. Vercel's sources here are plain
// regular expressions, so they can be matched directly.
function productionHeaders(): Plugin {
  return {
    name: 'finn-production-headers',
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? '/').split('?')[0] ?? '/'
        for (const entry of vercel.headers ?? []) {
          if (new RegExp(`^${entry.source}$`).test(path)) {
            for (const header of entry.headers) res.setHeader(header.key, header.value)
          }
        }
        next()
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  if (mode !== 'test') {
    const env = loadEnv(mode, root, 'VITE_')
    // loadEnv reads web/.env* files and VITE_* variables from the environment (Vercel's settings).
    const checked = checkDeployConfig(env, vercel)
    for (const warning of checked.warnings) console.warn(`[finn] ${warning}`)
  }

  return {
    plugins: [
      react(),
      productionHeaders(),
      VitePWA({
        registerType: 'autoUpdate',
        // Registered from the app bundle (src/main.tsx): no inline script for the CSP to refuse,
        // and no extra script blocking the first paint.
        injectRegister: false,
        // public/ files (icons, favicon) are precached by the glob below; listing them again duplicates them.
        includeManifestIcons: false,
        manifest: {
          id: '/',
          name: 'FINN',
          short_name: 'FINN',
          description: 'What changed across your portfolio, and why it matters.',
          lang: 'en-IN',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          background_color: paper.light,
          theme_color: paper.light,
          icons: [
            { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
            { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
        },
        workbox: {
          // The app shell only. API responses are never cached: they are cross-origin, carry the
          // investor's token, and no route below matches them.
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          // Error reporting loads only when a DSN is set; no device should download it otherwise.
          globIgnores: ['**/sentry-*.js'],
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/\.[^/]+$/],
          cleanupOutdatedCaches: true,
          clientsClaim: true,
          skipWaiting: true,
          runtimeCaching: [
            {
              // The saved copy: fresh from the network when there is one, the last good copy offline.
              urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname === '/snapshot.json',
              handler: 'NetworkFirst',
              options: {
                cacheName: 'finn-snapshot',
                networkTimeoutSeconds: 4,
                expiration: { maxEntries: 1 },
                cacheableResponse: { statuses: [200] },
              },
            },
          ],
        },
      }),
    ],
    define: {
      __FINN_RELEASE__: JSON.stringify(process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? 'local'),
    },
    build: {
      // Fonts and images are always files: the CSP allows fonts from 'self' only, not data: URLs.
      assetsInlineLimit: 0,
      sourcemap: false,
      target: 'es2022',
    },
    preview: { port: 4173, strictPort: true },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}', 'build/**/*.test.ts'],
      restoreMocks: true,
      // A device clock far from India proves every time is shown in Indian time.
      env: { TZ: 'America/New_York', VITE_API_URL: 'https://api.finn.test', VITE_NETWORK_ENABLED: 'false' },
    },
  }
})
