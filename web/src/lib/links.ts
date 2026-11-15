// Source documents are links only when they are what the contract promises: an https document on
// NSE's archive. Anything else is shown as text, never as something a tap could open.

const NSE_ARCHIVE_HOSTS = new Set(['nsearchives.nseindia.com', 'archives.nseindia.com'])

export function nseDocumentUrl(raw: string): string | null {
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return null
  }
  if (url.protocol !== 'https:') return null
  if (!NSE_ARCHIVE_HOSTS.has(url.hostname)) return null
  if (url.port !== '' || url.username !== '' || url.password !== '') return null
  return url.href
}

/** "PDF" for a .pdf link, otherwise null: said once, so a tap is never a surprise download. */
export function documentKind(href: string): string | null {
  return /\.pdf$/i.test(new URL(href).pathname) ? 'PDF' : null
}
