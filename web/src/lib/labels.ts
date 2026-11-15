// Plain words for the classifier's internal names (pipeline/finn/taxonomy.py and classify.py).
// The investor reads "Earnings call notices", never "earnings_call".

const CATEGORY: Record<string, string> = {
  management_change: 'Management change',
  governance: 'Governance',
  litigation: 'Litigation',
  pledging: 'Promoter pledge',
  insider_trading: 'Insider trading',
  results: 'Results',
  'M&A': 'Merger or acquisition',
  fund_raise: 'Fund raising',
  credit_rating: 'Credit rating',
  capex: 'Capital expenditure',
  dividend: 'Dividend',
  bonus_split: 'Bonus or split',
  press_release: 'Company announcement',
  earnings_call: 'Earnings call',
  investor_meetings: 'Investor meeting',
  postal_ballot: 'Postal ballot',
  agm_egm: 'Shareholder meeting',
  unclassified: 'Filing',
}

/** "management_change" -> "Management change"; unknown names are made readable, not hidden. */
export function categoryLabel(category: string): string {
  return CATEGORY[category] ?? humanise(category)
}

// Routine counts are keyed by subtype when there is one, otherwise by category
// (pipeline/finn/rank.py). Each kind has a singular and a plural phrase.
const KIND: Record<string, [string, string]> = {
  earnings_call: ['earnings call notice', 'earnings call notices'],
  investor_meetings: ['investor meeting notice', 'investor meeting notices'],
  newspaper: ['newspaper notice', 'newspaper notices'],
  results_ad: ['results advertisement', 'results advertisements'],
  unclassified: ['other filing', 'other filings'],
  trading_window: ['trading window closure', 'trading window closures'],
  share_certificates: ['share certificate notice', 'share certificate notices'],
  compliance: ['compliance certificate', 'compliance certificates'],
  record_date: ['record date notice', 'record date notices'],
  board_meeting_notice: ['board meeting notice', 'board meeting notices'],
  esg: ['sustainability report', 'sustainability reports'],
  esop: ['employee stock option allotment', 'employee stock option allotments'],
  debt: ['debt security filing', 'debt security filings'],
  convertible: ['convertible security filing', 'convertible security filings'],
  deck: ['investor presentation', 'investor presentations'],
  filing: ['results document', 'results documents'],
  routine_notice: ['routine notice', 'routine notices'],
  postal_ballot: ['postal ballot notice', 'postal ballot notices'],
  agm_egm: ['shareholder meeting notice', 'shareholder meeting notices'],
  auditor_appointment: ['auditor appointment', 'auditor appointments'],
  auditor_change: ['auditor change', 'auditor changes'],
  auditor_exit_other: ['cost, internal or secretarial auditor change', 'cost, internal or secretarial auditor changes'],
  secretarial: ['company secretary change', 'company secretary changes'],
  inter_se: ['transfer between promoters', 'transfers between promoters'],
  dividend: ['dividend notice', 'dividend notices'],
  bonus_split: ['bonus or split notice', 'bonus or split notices'],
  press_release: ['company announcement', 'company announcements'],
  business_update: ['business update', 'business updates'],
  credit_rating: ['credit rating', 'credit ratings'],
  insider_trading: ['insider trading disclosure', 'insider trading disclosures'],
  management_change: ['management change', 'management changes'],
  results: ['results filing', 'results filings'],
}

/** "8 earnings call notices", "1 newspaper notice" */
export function kindPhrase(kind: string, count: number): string {
  const known = KIND[kind]
  const phrase = known ? known[count === 1 ? 0 : 1] : `${humanise(kind).toLowerCase()} ${count === 1 ? 'filing' : 'filings'}`
  return phrase
}

/** Routine counts, largest first, then alphabetically by phrase. */
export function routineKinds(byKind: Record<string, number>): { kind: string; count: number; phrase: string }[] {
  return Object.entries(byKind)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => ({ kind, count, phrase: kindPhrase(kind, count) }))
    .sort((a, b) => b.count - a.count || a.phrase.localeCompare(b.phrase))
}

/**
 * Said when the exchange's summary only restates its label (detail_in_document): the event is
 * real, the detail is in the PDF, and FINN does not guess it.
 */
export function detailInDocumentNote(category: string): string {
  if (category === 'management_change') return 'The filing does not say who; the document does.'
  if (category === 'results') return 'The filing does not give the numbers; the document does.'
  return 'The filing does not say what happened; the document does.'
}

/** "Asian Paints Limited" -> "Asian Paints" */
export function shortCompany(name: string): string {
  return name.replace(/\s+(limited|ltd\.?)$/i, '').trim() || name
}

function humanise(name: string): string {
  const words = name.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}
