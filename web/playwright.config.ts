import { existsSync } from 'node:fs'
import { chromium, defineConfig, devices } from '@playwright/test'

// End-to-end tests run against the production build (`vite preview`), served with the same
// headers as vercel.json, so they run under the real Content-Security-Policy. The API is never
// called: every request to it is answered by the tests (e2e/api.ts).
//
// Browser: in CI, Playwright's own Chromium (`npx playwright install --with-deps chromium`).
// Where that download is not possible but Google Chrome is installed, the local Chrome is used.
const CI = Boolean(process.env.CI)
const useLocalChrome = !CI && !existsSync(chromium.executablePath()) && existsSync('/opt/google/chrome/chrome')
const browser = useLocalChrome ? { channel: 'chrome' as const } : {}

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:4173',
    // A page controlled by a service worker hides its requests from route interception.
    serviceWorkers: 'block',
    locale: 'en-IN',
    // A device clock outside India: every time on screen must still be Indian time.
    timezoneId: 'Europe/London',
    trace: 'retain-on-failure',
    ...browser,
  },
  projects: [
    {
      name: 'phone-360',
      use: {
        ...devices['Pixel 7'],
        ...browser,
        viewport: { width: 360, height: 800 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'desktop-1280',
      use: { ...devices['Desktop Chrome'], ...browser, viewport: { width: 1280, height: 900 } },
    },
  ],
  webServer: {
    // The build must already exist (CI builds it in its own step; locally: npm run build).
    command: 'npm run preview',
    url: 'http://localhost:4173',
    reuseExistingServer: !CI,
    timeout: 60_000,
    env: { VITE_API_URL: 'https://finn-api-53vw.onrender.com' },
  },
})
