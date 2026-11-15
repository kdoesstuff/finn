// Draws FINN's icon and writes every size the app needs into public/. Run: npm run icons
//
// The mark: an ink "F" over the bookkeeper's double rule (the line drawn under a total to say it
// is final), on ledger paper. Plain rectangles, no text, so it renders the same everywhere.
// Colours are the light theme's tokens (src/styles/tokens.css).

import { writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { chromium } from '@playwright/test'

const PAPER = '#ECEFE8'
const INK = '#18202E'
const ACCENT = '#26388A'

/** The mark on a 512 grid, scaled by `scale` about the centre (for maskable safe zones). */
function mark(scale) {
  const shapes = [
    // F: stem, top arm, middle arm
    [158, 96, 56, 262, INK],
    [158, 96, 206, 52, INK],
    [158, 206, 156, 46, INK],
    // double rule
    [158, 390, 206, 18, ACCENT],
    [158, 426, 206, 18, ACCENT],
  ]
  const offset = 256 * (1 - scale)
  return shapes
    .map(([x, y, w, h, fill]) => {
      const sx = (offset + x * scale).toFixed(1)
      const sy = (offset + y * scale).toFixed(1)
      return `<rect x="${sx}" y="${sy}" width="${(w * scale).toFixed(1)}" height="${(h * scale).toFixed(1)}" fill="${fill}"/>`
    })
    .join('')
}

function svg({ rounded, scale }) {
  const background = rounded
    ? `<rect width="512" height="512" rx="104" fill="${PAPER}"/>`
    : `<rect width="512" height="512" fill="${PAPER}"/>`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${background}${mark(scale)}</svg>\n`
}

const outputs = [
  { file: 'icon-192.png', size: 192, rounded: true, scale: 0.86 },
  { file: 'icon-512.png', size: 512, rounded: true, scale: 0.86 },
  // Maskable: full bleed, the mark inside the central 80% safe zone.
  { file: 'icon-maskable-512.png', size: 512, rounded: false, scale: 0.62 },
  // iOS rounds the corners itself.
  { file: 'apple-touch-icon.png', size: 180, rounded: false, scale: 0.78 },
]

const publicDir = new URL('../public/', import.meta.url)
await writeFile(new URL('favicon.svg', publicDir), svg({ rounded: true, scale: 0.86 }))

// Playwright's own Chromium when installed; otherwise a local Chrome.
const bundled = chromium.executablePath()
const browser = await chromium.launch(existsSync(bundled) ? {} : { channel: 'chrome' })
const page = await browser.newPage()
for (const { file, size, rounded, scale } of outputs) {
  await page.setViewportSize({ width: size, height: size })
  const image = svg({ rounded, scale }).replace('<svg ', `<svg width="${size}" height="${size}" `)
  await page.setContent(`<html><body style="margin:0;background:transparent">${image}</body></html>`)
  await writeFile(new URL(file, publicDir), await page.screenshot({ omitBackground: true }))
  console.log(`public/${file} (${size} px)`)
}
await browser.close()
