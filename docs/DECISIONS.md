# Decisions

Each entry: the decision, what else was considered, and the evidence. Measurements are added as the
build produces them.

## Settled with Karthik, 11 Nov 2026

| # | Decision | Alternatives considered | Why |
| --- | --- | --- | --- |
| 1 | Supabase is the store; the API is the only reader and writer; a daily JSON snapshot is bundled into the frontend | Frontend reading Supabase directly; no snapshot | The demo must render while the free backend wakes, or if Supabase or NSE fail |
| 2 | Reviewers use a one-tap, read-only demo investor. No sign-up | Magic-link sign-up | Not needed at this stage; the schema and row-level security are still per investor |
| 3 | Zero spend, without exception | $10 OpenRouter credit | The brief says free tiers are enough and rewards efficiency; precomputing and caching keep review-time load small |
| 4 | Interaction: a morning brief you can interrogate. Ranked cards (what changed, why it matters to the thesis, evidence, who to call); company page with the promise ledger first; ask box scoped to that company's documents; decision notes kept | Chat-first; dashboard; audio brief | Chat invites ungrounded answers; a dashboard reads as a trading app; the brief asks for a point of view |
| 5 | Visual direction: Karthik supplies references later; until then paper-and-ink typography, one accent, light and dark, all through design tokens | Waiting for references before building screens | A restyle is a token change, so nothing waits |
| 6 | Network: fictional people only, generated from a seed, in LinkedIn's Connections.csv format, labelled synthetic. Real names appear only where a filing itself names someone | Real profiles; a public dataset | Privacy; the brief allows realistic synthetic profiles if stated |
| 7 | Portfolio of 18: Kalyan Jewellers, MRF, Tata Power, Triveni Turbine, Manappuram Finance, Page Industries, NMDC, ABB India, Eicher Motors, Natco Pharma, TCS, HDFC Bank, Asian Paints, Elgi Equipments, Asahi India Glass, Persistent Systems, Navin Fluorine, Larsen & Toubro. Research names: Polycab India, Bajaj Finance, Dixon Technologies | HAL, ITC, IGL Spirits, EIH, IRCTC, Avanti Feeds (all excluded by ENAM's values) | Sector and size mix; ten report during the build; a bank and two lenders exercise all three results templates; two real pledge stories |
| 8 | Two submissions from one codebase: `finn-core` (Push, Pull) and `finn` (with Network); two emails | One email | Both applications are allowed; each brief has its own subject line |

## Found by verification, 11 Nov 2026 (repaired in task A3)

Each repair has a regression test built on the real filing that exposed it
(`pipeline/tests/test_repairs.py`, filings named by NSE `seq_id`).

| Finding | Evidence |
| --- | --- |
| De-duplication dropped distinct filings | 264 of 4,795 filings with different PDFs were merged; 54 would have ranked as attention items |
| One event appeared as several cards | Asian Paints: two filings for one appointment; Sadbhav: three for one auditor exit |
| Roles misread | "Chairman and Non-Executive Director" read as MD; roles inferred from NSE's label alone |
| Auditor red flag overstated | Of 14 items scored 100, 5 were cost, internal or secretarial auditors and 1 a subsidiary's auditor |
| Litigation flat | 56 items ranked as attention, routine GST notices among them |
| Pledge fields mislabelled | 16.68% (Kalyan) and 6.25% (Asian Paints) are all demat pledges by any holder; promoter pledge is 15.62% and 5.46% of all shares |
| Trading calendar | 10 Nov 2026 was a market holiday; Sun 8 Nov had a Muhurat session; weekday logic is wrong for both |

### How each was repaired

| Defect | Repair | Evidence it holds |
| --- | --- | --- |
| Dropped filings | Identity is NSE's `seq_id`. Only exact re-uploads (same company, label, summary, file name and size, within 60 minutes) count once; everything else is kept and grouped into events | 4,765 of 4,795 listed; the 30 not listed are each an exact copy of a listed filing. Same-PDF-different-announcement (Motherson) and same-subject-different-document (Alembic) cases stay separate |
| One event, several cards | Filings by one company in one category within 6 hours form one event card listing every filing. The card is scored from the filings in the company's own words; a summary that only restates NSE's label is evidence of nothing more | 3,903 events, 666 with more than one filing. Asian Paints is one card led by the Leo Puri filing (55); Sadbhav's three auditor filings one card (100) |
| Roles | Roles and actions read only from the company's own words (`text.own_words`). "Non-executive" folded before matching; "MD" case-sensitive; new rungs: executive director (exit 80, appointment 70) and senior management (CTO, unit or subsidiary heads: 60-70); reappointments are continuity (45 at the top, routine for directors) | Sundaram, IVP, Tata Steel read as chair; Wipro's unit CEO and Arvind's subsidiary CFO as senior; Manappuram's CTO exit 70 |
| Auditor kind | Statutory auditor of the company 100; subsidiary's auditor 70; cost, internal or secretarial 40 | Of the week's red flags, only Varvee Global and Sadbhav name the company's own statutory auditor. Popular Vehicles and Enviro Infra were subsidiaries' auditors; the handoff's note that R.G.N. Price was Popular Vehicles' own auditor was a misreading |
| Litigation | Kinds: insolvency and default 100, regulator acting 90, licence 75, tax 55, other legal 70. Tax and legal orders rise only when the amount is material against net worth (>=5%: 85; >=1%: 70; else 45); without an amount or net worth they stay below attention and say so | Attention-level litigation 56 -> 16. Citing "SEBI (LODR) Regulations" no longer counts as a regulator acting (Kansai Nerolac, Tenneco); Dabur's SEBI warning letter does |
| Pledges | `finn/pledges.py` names each NSE field for what it measures; checked against the feed's own share counts | Kalyan: 24.85% of promoter stake, 15.62% of the company, 16.68% all pledges of demat shares. Asian Paints: 10.35%, 5.46%, 6.25% |
| Alerts | A move reports which rule fired (pct, sigma or both) and that rule's threshold. Which moves a filing explains is decided on exchange sessions: the next two sessions after it, plus that day's session for a filing published after 15:30 ("moved before the filing") | Test with the real November 2026 calendar: a filing after the close on 9 Nov explains moves on 11 and 12 Nov, across the 10 Nov holiday |

### Classifier measurement after the repairs (4,795 filings, 4-9 Nov 2026)

`python pipeline/scripts/measure_classifier.py`

| Layer | Filings | Share |
| --- | --- | --- |
| Text rule on the company's own words | 2,123 | 44.3% |
| Exact NSE label | 1,147 | 23.9% |
| Fuzzy label match | 549 | 11.4% |
| Text rule on a summary that only restates the label | 519 | 10.8% |
| Needs a model | 457 | 9.5% |

The handoff's "text rule 55.1%" counted the fourth row as text rules; it is a label match in effect.
A quarter of summaries (1,201, 25.0%) say nothing beyond NSE's label. Events: 838 attention,
567 worth knowing, 2,498 routine (a results-season week across the whole market). For the 18-stock
portfolio: one item for attention (Elgi's results, with its investor presentation on the same card),
eight worth knowing, 18 routine.

Still left for a model: General Updates 214, Updates 131, Outcome of Board Meeting 107 (task C3).

## Phase A security review (11 Nov 2026)

| Check | Result |
| --- | --- |
| Secrets in git history | gitleaks v8.30.0 over all 16 commits (26 MB): no leaks. Today's changed files scanned: clean |
| Secrets in code | None. Settings are read from `.env` or platform variables only; `config.require()` raises a named error instead of returning nothing; the setup checker redacts keys from any error text |
| Untrusted XML | Results XBRL comes from the internet. Parsed with `defusedxml` with DTDs forbidden: entity expansion and external entities are refused, with tests. Python 3.13's expat already stopped entity expansion, but that depends on the expat version |
| Dependencies | `pip-audit` on `requirements.txt`: no known vulnerabilities |
| Production asserts | Removed from product code (they disappear under `python -O`); ruff's security rules (bandit) now run on every push |
| New network surface | None in phase A |
| CI | `workflows-to-install/ci.yml`: ruff, mypy, pytest, pip-audit, gitleaks over full history; read-only token; tool versions pinned in `requirements-dev.txt`, actions pinned to verified tags (checkout v7, setup-python v7, gitleaks v8.30.0) |

Tooling note: mypy's cache database fails inside a OneDrive-synced folder ("disk I/O error"); run
it with `--cache-dir` outside the folder there, or move the clone to `C:\dev\finn` as the handoff
recommends. CI is unaffected.

## Facts checked for later tasks

- Gemini embeddings (Google's embeddings docs, read 11 Nov 2026): `gemini-embedding-2` takes no
  `task_type`; the task is written into the text (`task: search result | query: ...`). Output
  dimensions 128-3072, 768 recommended; truncated vectors are normalised by the model; 8,192 input
  tokens; batch endpoint `batchEmbedContents`. Affects task E3.
- Exchange calendar, November 2026: Sun 8 Nov Muhurat session; Tue 10 Nov holiday (Diwali
  Balipratipada); Tue 24 Nov holiday. Affects task B3.

## Gate G0 passed (11 Nov 2026, 21:45 IST)

- CI run 43055989175 on `main`: lint, type check, 93 tests, dependency audit and the gitleaks
  history scan all green (pipeline job 44 s, secrets job 20 s).
- `check_setup.py` on Karthik's laptop: 9 of 9, including a real `embedContent` call that returned a
  768-dimension vector of length 1.000 (the model normalises truncated vectors, as documented).
- All 22 settings copied to GitHub Actions secrets.

## B1 Fetchers (11 Nov 2026)

`pipeline/finn/sources/`: one `NSEClient` (session warm-up and re-warm on 401/403, 0.7 s pacing,
exponential backoff with jitter on timeouts, 429 and 5xx, 404 returned as "does not exist", a named
`SourceError` when retries run out) and typed parsers for announcements, results indexes (legacy
and Integrated Filing), bhavcopy, pledges, board meetings, annual reports, insider trades and
corporate actions. Client behaviour is tested against a scripted session; every parser against the
recorded NSE responses. Live check: `smoke-sources` workflow (manual).

Found while testing: on Integrated Filing revision rows NSE leaves `broadcast_Date` empty and stamps
`creation_Date`. A parser keyed on `broadcast_Date` skips every revision and serves the original
numbers; Asian Paints' Mar 2026 results (revised 29 May and 15 Jul) would have been stale. The
parser now orders by the first of broadcast, creation and revision time, with a test.

A missing bhavcopy is returned as None, not an error: it is how a non-session day (a holiday such
as 10 Nov 2026) shows up, and B3 builds the trading calendar from it.

yfinance (secondary price source) is left to B4, where history is backfilled; the bhavcopy covers
daily ingest.
