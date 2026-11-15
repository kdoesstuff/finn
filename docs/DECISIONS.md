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

Live check, smoke-sources run 43058120274 (11 Nov 2026, 21:55 IST): 17 of 17 fetchers OK in 51 s,
38 requests. Results XBRL to headline matched the verified figures: TCS Sep 2026 consolidated
revenue ₹73,188 cr (YoY +11.2%), Asian Paints ₹9,977 cr (+16.9%), HDFC Bank net interest income
₹44,464 cr (+10.5%). Bhavcopy present for Sun 8 Nov (Muhurat session) and absent for Tue 10 Nov
(holiday) and Sat 7 Nov, confirming the calendar comes from the files, not weekdays. 814
announcements market-wide over two days; 1,558 pledge rows; 1,464 board meetings in the next 14 days.

## B2 Database (15 Nov 2026)

Schema in `db/migrations/0001_foundation.sql`, applied by `finn/db.py` (`scripts/migrate.py`, or the
manual `migrate` workflow). Considered and rejected: Supabase CLI migrations (one more tool and a
login step for a single SQL file); tables in `public` behind RLS only (the REST API would then be one
policy mistake away from the data).

**Access model, three layers.**

| Layer | What it does | Evidence |
| --- | --- | --- |
| Schema not exposed | Tables live in schema `finn`, which Supabase's Data API does not serve, and Supabase's API roles (`anon`, `authenticated`, `service_role`) are granted nothing in it, so neither the publishable nor the secret key can read FINN data over REST | Tests set each API role and read every table: refused. `migrate.py verify` calls the live REST API with both real keys |
| Least-privilege roles | Pipeline and API connect with the database URL and switch at once to `finn_ingest` (writes public market data; cannot see investor tables) or `finn_api` (reads market data; writes documents, chunks and the model cache; reads and writes investor rows) | Tests: ingest refused on investor tables; API refused when changing market data or creating investors |
| Row-level security | On every table. Investor rows are visible only to a transaction scoped to that investor (`finn.investor_id`); unscoped, nothing is visible | Tests: investor A sees only A's holdings and notes, cannot insert, update or delete B's rows; a test fails if any table ever lacks RLS. A mutation check (opening the holdings policy) made three tests fail |

Honest limit: the roles are reached with `SET ROLE` from the admin connection, so code that is fully
compromised could switch back. They limit mistakes, not an attacker who already runs code on the
server; the database URL stays server-side only for that reason.

**Found while testing.** Two things that would have been production bugs:

1. On Postgres 16+, an admin that creates a role cannot switch into it until it grants the role to
   itself (`grant ... to current_user`). Verified by logging in as a non-superuser admin; testing as
   superuser hid it, because a superuser may switch into any role. Tests therefore log in as a
   non-superuser admin, as Supabase's `postgres` does.
2. Role and investor scope leaked. `as_role` sets them with `set local`, which lasts until the end
   of the *transaction*. On a connection that already had a transaction open, the block was only a
   savepoint, so `finn_api` and investor A's scope stayed in force after it. Fixed by running
   connections in autocommit (each `as_role` is a real transaction) and refusing `as_role` inside an
   open transaction. Both have tests.

**Other decisions.** Constraints refuse bad data at the door: symbol pattern, https-only document
links, positive prices, percentages in 0-100, and the year-to-date guard on results (a quarter is
80-95 days). Embeddings are `vector(768)` with an HNSW cosine index; changing the size is a new
migration, not a setting. NSE's pledge feed names companies but carries no symbol, so pledges are
keyed by company name and disclosure time, with the symbol resolved at ingest. Prefs defaults match
`Thresholds` and `Prefs` in code, with a test. Migrations run in name order, one transaction each,
under an advisory lock, recorded with a checksum: an edited migration, or a database ahead of the
code, is refused.

Deferred to the task that first needs them, as their own migrations: promise ledger (E5), insider
trades (D3), network people and edges (G2).

CI now runs the database tests on a real Postgres 16 with pgvector (Ubuntu 24.04 packages, the
pipeline job pinned to that runner); they fail rather than skip in CI.

Live on Supabase (15 Nov 2026): `check_setup.py` 10 of 10, Postgres 17.11 with pgvector 0.8.2;
CI run 43698214984 green including the database job; `migrate` run 43698551282 applied
`0001_foundation.sql` and every check passed. The admin was allowed to grant use of `extensions`,
so both FINN roles use pgvector; the REST API refused all probed FINN tables with both real keys
(`PGRST106`, schema not exposed). CI tests on Postgres 16 with pgvector 0.6 (Ubuntu 24.04
packages) while Supabase runs 17.11 with 0.8.2: the migration is proven on both; the gap is noted
in case a later migration uses something only 17 has.

## B3 Scheduled ingest (15 Nov 2026)

`finn/ingest.py`, run by `scripts/ingest.py` and the `ingest` workflow, every job as `finn_ingest`.

| Job | Schedule (IST) | What it does |
| --- | --- | --- |
| filings | every 30 min, 07:37 to 00:07 | Last two days of announcements, market-wide, upserted by NSE's id and classified; then results for covered companies that filed results in the window; then filings classified by older rules (a hash of the rule files) are reclassified, 5,000 per run |
| eod | 19:22 and 21:22 | Bhavcopy for every recent day not yet recorded; a day without one is recorded as not a session (non-sessions older than 3 days are final; today is re-checked until the file appears) |
| daily | 06:52 | Equity master list, board meetings (a week back, a month ahead), pledges, corporate actions and a results sweep for covered companies |
| backfill | by hand | Daily jobs, then filings day by day, then prices from an earlier start |

Minutes are off the hour on purpose: GitHub delays scheduled runs at busy times, and a late run
loses nothing because every job re-reads an overlapping window and writes idempotently.

**Coverage** (`0002_coverage.sql`). Ingest may not read investor tables, so it cannot learn from
holdings which companies need results and history. `finn.coverage` is the public half of that fact,
a symbol and a reason, with no link to any investor; the API adds to it. The demo investor's 18
holdings and 3 research names are seeded through the API role (`ingest.py seed`). The same
migration adds `finn.lockdown()`, called last by every migration, which strips any privilege
Supabase's API roles might gain on new objects; `migrate.py verify` now also checks on the live
database that those roles hold no privilege on any FINN table.

**Found in the data while building it.**

1. ISINs disagree between sources: Asian Paints' November filings carry `INE021A01018`, the same
   week's bhavcopy `INE021A01026`. Writing both would flip the record on every run; ISINs now come
   only from the bhavcopy and the equity master, names and industries from filings.
2. NSE's pledge feed has company names and no symbol. Names are matched exactly after normalising
   case, punctuation and "Limited/Ltd", never fuzzily: Kalyani Forge must not become Kalyan
   Jewellers. Names come from NSE's equity master list (a new fetcher; its live format is checked by
   the smoke test, since only a constructed sample exists in the fixtures), filings and board
   meetings.
3. A results file NSE lists but does not serve is asked for again on the next run, not marked
   missing for good; a stored file is never downloaded again (tests count the downloads).

**Tested** with a stand-in for NSE that answers from the recorded responses, filtering by date as
NSE does: 4,795 filings stored once and unchanged on a second run; timestamps stored as Indian
time; the July revision of Asian Paints' March results stored, not May's original; TCS Sep 2026
revenue ₹73,188 cr from the stored facts; HDFC Bank on the bank template; 6 Nov a session, 7 and
10 Nov not; Kalyan's pledge (24.85% of promoter stake) matched to KALYANKJIL; a failed job logged
with its error and raised; the seed idempotent. 157 tests in all.

Moved to D6: the daily JSON snapshot. It is the app's fallback for what the app shows, which is
the digest, and the digest does not exist until D6; exporting raw tables now would be thrown away.

Live (15 Nov 2026): migration 0002 applied (run 43699745898), every check passed including the new
one that Supabase's API roles hold no privilege on any FINN table; demo investor seeded (18
holdings, 3 research names, 21 covered); smoke run 43699859792: 18 of 18 fetchers OK, the equity
master list has 2,635 companies with names and ISINs (TCS = Tata Consultancy Services Limited,
INE467B01029), confirming the constructed sample's layout.

## B4 Backfill (15 Nov 2026)

**Pledge feed went empty.** The same smoke run returned 0 pledge rows (1,558 on 11 Nov). The smoke
test had counted that as a pass. Now: an empty pledge feed is an error in the daily job (the run
goes red, stored pledge history is kept, the other parts still run), and the smoke test fails on
it and reports what NSE returns for other ways of asking (a 90-day date range, a period, the SME
index, no parameters), so the fix comes from evidence.

Evidence (smoke run 43706393122, Sun 15 Nov): the default query, a 90-day date range and a 1-year
period all returned no rows (the 90-day answer still had both of its keys, `comNameList` and
`data`); the report of the remaining variants was cut off at 200 characters, which is why the probe
now prints in full. The recorded response of 9-11 Nov shows what the feed holds: 1,558 companies,
all published by NSE within two minutes of each other (9 Nov 2026, 16:30:17 to 16:31:58; corrected
from "one time" after the Push stream checked), nearly all for the quarter to
30 Sep 2026 (1,454 rows). So it looks like a snapshot NSE regenerates, and the current one is empty.

So, three changes:
1. **The 9 Nov snapshot is loaded** (`ingest.py import-pledges`, the JSON exactly as NSE served it).
   It is NSE's own published data, and each row keeps NSE's publication time, so the app can say
   "as published by NSE on 9 Nov". Pledges change when companies file their quarterly
   shareholding, so for the September quarter it is current.
2. **An empty feed is a warning while the stored copy is under 14 days old**, and a failure after
   that. The daily run stays green and says so (a warning annotation on the run) for a known,
   dated gap, and goes red once the copy is stale enough to matter. Never "no pledges anywhere":
   stored history is never touched.
3. **The probe prints the full shape of every answer** (each list's length, the company list
   included) for eight ways of asking, including by symbol and by company name.

Probe result (smoke run 43719842012, 15 Nov 19:07 IST): all eight ways of asking (default, 7-day
and 90-day ranges, 1-year period, by symbol, by company name, the SME index, no parameters) answered
with both lists empty: `comNameList: 0 items, data: 0 items`. NSE's pledge dataset itself is empty,
not our query: there is nothing to fix in the fetcher. The stored 9 Nov copy carries the pledge
cards; the daily run warns until 23 Nov and fails after, which is when to look again.

**Verified live** (`verify --live`, run 43706396788): all 21 covered companies have the Sep 2026
quarter and its year-ago quarter, and 98 sessions of prices; TCS, Asian Paints and HDFC Bank match
the figures checked by hand. "No failures."

**Verification report** (`ingest.py verify --live`, also a workflow job): for every covered
company, the quarters stored, whether the target quarter and the year-ago quarter (for YoY) are
there, sessions of price history, filings since a date, and whether pledges are matched. A
missing target quarter gets a reason from NSE itself: "not listed yet" is a reason; "listed but
not stored" is a failure. TCS, Asian Paints and HDFC Bank's stored figures are compared with the
values verified by hand. Cards are rebuilt from stored results by the same parser code that reads
NSE's files (`finn/stored.py`), so the database can never disagree with the parser.

**Live backfill** (run 43700944742, 23 min 26 s, `--from 2026-10-01 --to 2026-11-15 --prices-from
2026-06-25`). Everything loaded; the run went red only because the pledge feed was still empty.

| Part | Result |
| --- | --- |
| Filings, 1 Oct to 15 Nov, market-wide | 24,766 new over 46 days (1,530 on 5 Nov, the peak of results season; 21 on Sun 11 Oct) |
| Prices, 25 Jun to 15 Nov | 98 sessions, 276,847 rows; 46 days without a bhavcopy, recorded as not sessions (weekends, 14 Sep, 2 Oct, 20 Oct, 10 Nov); Sun 8 Nov recorded as a session (Muhurat trading), as the plan predicted |
| Results, 21 covered companies, 9 quarters, both bases | 16 companies with all 18; NMDC 17, LT 16 plus 2 that NSE lists but did not serve (asked again next run), ABB 14, Page Industries 9 (standalone only); none rejected |
| Equity master, board meetings, corporate actions | 2,635 companies; 1,573 meetings; 384 actions |
| Pledges | Feed empty again: the only error |

**Two weaknesses the run exposed, fixed before the next one.** (1) The run's errors were printed at
the end of a summary cut at 6,000 characters, where a long run could lose them: errors now come
first (up to 40, all of them in `ingest_runs`), then the counts. (2) One day of filings or prices
that NSE refused would have stopped the whole backfill with nothing after it: a failed day is now
recorded and skipped (it is asked for again next run, since nothing is recorded for it), and after
5 failed days in a row the job stops asking, because NSE is then down or refusing us. A damaged
bhavcopy zip is a source error like any other. Tests for each, with a mutation check.

## B5 API (15 Nov 2026)

Built by one agent on a branch, reviewed and merged by the lead; details, measurements and
sources in `docs/notes/B5-B7.md`, the contract in `docs/API.md`.

- **One FastAPI service** on Render's free tier in Singapore, the only reader of the database for
  the web apps. Each request runs as `finn_api` with the investor's id set for row-level security,
  inside one transaction; the digest is two SQL statements, because the API (Singapore) and the
  database are in different regions and every round trip costs.
- **Sessions** are signed tokens (HMAC-SHA256, version, investor, read-only flag, deployment,
  issued and expiry times), not database rows; no sign-up (decision 2). The deployment (`core` or
  `full`) comes from the request's `Origin`, checked against two allow-lists, so `finn-core` can
  never be served the Network layer.
- **Limits**: 60 requests a minute on `/v1`, 10 a minute for sessions, keyed by Render's
  `True-Client-IP` (a client can forge `X-Forwarded-For`, not that); 16 KB bodies; 5 s statement
  timeout. Errors have one shape and never carry a stack trace. Sentry receives no request bodies,
  headers or IP addresses.
- **Deploys** only after CI passes (`autoDeployTrigger: checksPass`), and only when `api/` or the
  pipeline code it imports changes.
- Tested: 121 API tests (CORS, refusals, limits, token tampering and expiry, the digest's shape
  against the contract, the pool recovering from a lost database); pip-audit and gitleaks clean.

## B6 Web (15 Nov 2026)

Built by a second agent, reviewed and merged; details in `docs/notes/B6.md`.

- **The morning brief**, phone first: one sentence on what changed, then "Needs your attention",
  "Worth knowing" and the routine filings folded away, each item with why it was chosen and a link
  to the filing. Windows of 24 hours, 3 days and 7 days.
- **Never a blank screen**: a "waking up" state while Render starts, then the bundled snapshot with
  its "data as of" time if the API does not answer.
- **Security**: a strict Content Security Policy in `web/vercel.json` (`connect-src` names only the
  API and Sentry); the build refuses an API address the policy does not allow, so the two can
  never drift apart; no `innerHTML`; self-hosted fonts.
- **Look**: paper and ink, Castoro and Mukta (both drawn for Indian scripts as well as Latin),
  tokens in one file, so Karthik's references change tokens, not components (decision 5).
- Tested: 79 unit tests; Playwright in Chromium with axe accessibility checks (27 pass; 3 skipped
  by design because they need the deployed site).

## B7 Keep-warm (15 Nov 2026)

Render's free tier sleeps after 15 idle minutes, and a reviewer must never meet a 50-second cold
start. Primary: an external monitor (UptimeRobot, free) calls `/health` every 5 minutes. Backup: the
`keep-warm` workflow every 10 minutes, at minutes off the hour, because GitHub delays and drops
scheduled runs under load. Kept warm all month, the service uses about 720 of Render's 750 free
instance-hours.

## Integrated end to end, before deploying (15 Nov 2026)

The real API (uvicorn, the Render start command) over a Postgres migrated by our migrations, seeded
with the demo investor and loaded with the recorded week of filings and a session of prices; the
real production web build, pointed at it, served as static files; driven by Chrome at 360 px. The
demo session, CORS preflight with the `Authorization` header, and the digest for 24 hours and 7
days all answered 200, with no console errors and no failed requests; the brief rendered Larsen &
Toubro's 9 Nov order announcement with its link and reason.

Found and fixed: the summary read "1 routine filings set aside" (`rank.py` now says "filing" for
one); the contract's example routine counts did not add up to its own total.

## Deploying B5 and B6 (15 Nov 2026)

- **A test that passed everywhere but CI.** The lint-rule test hands ESLint a forbidden line of
  code as text. With `CI=true`, which GitHub's runners set, typescript-eslint assumes a one-off run
  and type-checks the file on disk instead of the text, so it linted the real, clean `Summary.tsx`
  and found nothing. Reproduced on a clean clone of the pushed commit with `CI=true`; the test now
  turns that inference off for itself; a mutation (the rule removed) still fails it under `CI=true`.
  Lesson kept: run every suite with `CI=true` before pushing.
- **The API's address is `https://finn-api-53vw.onrender.com`**: Render added a suffix because
  `finn-api` was taken. The app's CSP, its build check and its tests name it; the build refuses the
  old address. `/health` answered `{"ok":true,"db":true,...}` from the deployed commit.
- **Dependency alerts**: GitHub reported three advisories in the web app's build and lint tools,
  none in what the browser downloads. `glob` and `minimatch` (moderate) are forced to patched
  versions with `overrides` scoped to the one tool that pulls each (the tools' own latest releases
  still ask for the old ones; each call site was read to confirm the API it uses is unchanged).
  `deepmerge` (low) has no patched release at all; it only merges a plugin's constant defaults at
  build time and is absent from `dist`, so the alert is to be dismissed on GitHub as "risk is
  tolerable", with that reason. After: `npm audit` 0 moderate, 0 high; the full web suite passes
  under `CI=true`; the service worker precaches the same 13 files. Details:
  `docs/notes/dependency-advisories.md`.
- **No scheduled ingest run yet.** By 11:30 UTC, about two hours after the schedule was pushed,
  GitHub had started no scheduled run of `ingest.yml` (four filings slots had passed); the API's
  `data_as_of` was still the backfill's last filings run (15:35 IST). GitHub warns that scheduled
  runs can be delayed or dropped under load. B3 is not done until three scheduled runs succeed in a
  row; if none has fired by the time of the next check, the schedule is re-registered (disable and
  enable the workflow) and filings are run by hand meanwhile. If GitHub's scheduler stays
  unreliable, the fix is an external trigger calling `workflow_dispatch` (the same pattern as the
  keep-warm monitor), decided then.

## Gate G1 security review (15 Nov 2026)

Reviewed at lead commit `aa33523` (GitHub `main` at `dd42347` plus the pledge change awaiting push;
neither touches the security surface). What is deployed: the API on Render (`finn-api-53vw`,
Singapore, free), the web app on Vercel (`finn-lac.vercel.app` full edition; `finn-core` pending),
the database on Supabase (Mumbai), ingest in GitHub Actions. Every test named below was run for
this review on a local Postgres 16 with pgvector, logged in as a non-superuser admin as on Supabase:
pipeline 175 passed (`tests/test_db.py` 30 of them), API 121 passed, web unit 79 passed under
`CI=true`, and the browser tests named below passed in Chrome against the production build.

**Database**

| Check | Result | Evidence |
| --- | --- | --- |
| Row-level security on every table | Yes, all 18 FINN tables | `test_every_table_has_row_level_security` (`db.tables_without_rls` is empty); `migrate.py verify` checks the live database (run 43699745898) |
| Supabase's API roles locked out | `anon`, `authenticated`, `service_role` hold no privilege on any FINN table and cannot read one; the schema is not served over REST | `test_supabase_api_roles_reach_nothing`, `test_supabase_api_roles_hold_no_privilege_on_any_table`, `test_a_stray_grant_is_reported`; `finn.lockdown()` (`0002_coverage.sql:26`) runs last in every migration; live REST probe with both real keys answered `PGRST106` (B2) |
| Ingest role | Writes market data, cannot see investor tables | `test_ingest_writes_market_data_and_never_sees_investors` |
| API role | Reads market data, cannot change it or create investors | `test_api_reads_market_data_but_cannot_change_it` |
| Investor scope (`finn.investor_id`) | A transaction sees only its investor's rows; unscoped, none; another investor's rows cannot be written | `test_an_investor_sees_only_their_own_rows`, `test_without_a_scope_no_investor_rows_are_visible`, `test_an_investor_cannot_write_or_change_another_investors_rows`; through the API: `test_one_investor_never_sees_another_investors_holdings`, `test_a_token_for_an_unknown_investor_sees_an_empty_portfolio` |
| Role and scope never outlive a request | Each `as_role` is its own transaction on an autocommit connection; refused inside an open one | `test_role_and_scope_end_with_the_transaction`, `test_switching_role_inside_an_open_transaction_is_refused`, `test_api_connections_are_autocommit_scoped_and_time_limited` (the next request starts as the admin, unscoped) |
| Every API query runs as `finn_api` | Yes: the session route (`api/app.py:189`), the digest and the health query (`pipeline/finn/digest.py:107, 181`) | Code read; no other SQL in `api/` |

**API** (`api/`, deployed with `render.yaml`)

| Check | Result | Evidence |
| --- | --- | --- |
| Session tokens | HMAC-SHA256 over the claims with a context prefix; one algorithm, no header to downgrade; signature checked in constant time before parsing; exact claim set `v sub ro dep iat exp`, types checked, canonical base64url only, at most 1,024 characters; 12-hour life; refused if issued in the future (60 s skew) or longer-lived than allowed | `api/sessions.py:87-115`; `test_altered_or_foreign_tokens_are_refused`, `test_malformed_authorization_is_refused`, `test_a_session_expires_after_12_hours`, `test_tokens_from_the_future_or_too_long_lived_are_refused`, `test_verify_checks_claims_strictly`, `test_a_token_survives_a_restart_but_not_a_new_secret` |
| Secret | `SESSION_SECRET` generated by Render (`generateValue`), at least 32 bytes or the service refuses to start, never printed | `test_a_missing_or_short_session_secret_stops_start_up`, `test_the_service_refuses_to_start_on_a_weak_secret_without_printing_secrets`, `test_secrets_never_appear_in_the_settings_repr` |
| Origin allow-list | Two exact lists (`ALLOWED_ORIGINS_CORE`, `_FULL`): https only (http on localhost), no wildcards, no origin on both | `api/settings.py:31`; `test_origins_must_be_exact_https_origins`, `test_an_origin_cannot_belong_to_both_deployments` |
| Deployment from the origin | Sessions start only from an allow-listed site; the token records which (`dep`); a token is refused on the other site, so `finn-core` cannot be served Network | `api/app.py:170-171, 185`; `test_sessions_start_only_from_an_allow_listed_site`, `test_core_site_gets_a_read_only_demo_session`, `test_full_site_gets_network_when_the_investor_has_it_on`, `test_a_session_works_only_on_the_site_that_started_it` |
| CORS | Preflight from an allowed site, for GET/POST/OPTIONS with only `Authorization`/`Content-Type`: 204 with the exact origin echoed, max-age 600. Anything else: 403, no grant. A non-preflight `/v1` request carrying any other Origin is refused (403), which also stops a cross-site "simple" POST | `api/middleware.py:61-123`; `test_preflight_from_an_allowed_site_is_granted_exactly`, `test_preflight_is_refused_for_anything_else`, `test_allowed_sites_can_read_responses_including_refusals`, `test_other_sites_get_no_grant_and_v1_refuses_them`; checked end to end in Chrome with the real build (`DECISIONS.md`, "Integrated end to end") |
| Rate limits | 60 a minute per client on `/v1`, 10 for sessions, sliding window; preflights not counted. The client is Cloudflare's `True-Client-IP` on Render, never `X-Forwarded-For` (Render's proxy appends to whatever the client sent); a missing or doubled header falls back to the connection; IPv6 counted per /64 | `api/ratelimit.py:27-56`; `test_sessions_are_limited_to_10_a_minute_per_client`, `test_v1_is_limited_to_60_a_minute_per_client_counting_sessions`, `test_on_render_the_client_is_the_true_client_ip_not_x_forwarded_for`, `test_a_missing_or_doubled_client_header_falls_back_to_the_connection`, `test_without_a_trusted_header_forwarding_headers_are_ignored` |
| Proxy headers | uvicorn runs `--no-proxy-headers --no-server-header`; the start command is tested as written in the Blueprint | `render.yaml:26`; `test_the_blueprint_is_what_this_test_runs`, `test_the_service_answers_over_real_http` |
| Body limit | 16 KB, by Content-Length or while reading a chunked body; a non-numeric length is refused | `test_bodies_over_16_kb_are_refused`, `test_chunked_bodies_over_16_kb_are_refused_while_reading`, `test_a_non_numeric_content_length_is_refused` |
| Statement timeout | 5 s on every pooled connection; a slow statement is cancelled and answered 503 | `test_api_connections_are_autocommit_scoped_and_time_limited`, `test_a_slow_statement_is_cancelled_and_reported_unavailable` |
| Errors | One shape, `{"error":{"code","message"}}`, from routes and middlewares alike; no stack trace or exception text reaches a client; database errors carry only their class name | `api/errors.py`, `api/database.py:66-68`; `test_an_unexpected_error_is_a_500_in_the_contract_shape`, `test_unknown_routes_are_404_in_the_contract_shape`, `test_wrong_methods_are_405_in_the_contract_shape`, `test_errors_have_the_contract_shape` |
| Surface | Three routes; no docs pages; the schema only behind `API_DOCS=1` | `test_the_schema_only_behind_the_flag_and_never_a_docs_page` |
| Security headers | On every response, refusals included: HSTS 2 years, `nosniff`, `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Cache-Control: no-store` | `api/middleware.py:28`; `test_security_headers_on_every_kind_of_response` |
| Sentry and logs | `data_collection` off for user, cookies, bodies, frame variables; Authorization, cookie and client-address headers dropped; bearer tokens, FINN tokens and database URLs redacted from events, breadcrumbs and log lines, tracebacks included | `api/observability.py`; `test_sentry_options_collect_nothing_personal`, `test_scrub_removes_credentials_wherever_they_appear`, `test_a_real_error_report_carries_no_token_cookie_ip_or_database_url`, `test_log_lines_are_redacted_tracebacks_included` |
| Dependencies | Exact pins in `api/requirements.txt`; `pip-audit`: no known vulnerabilities (API and pipeline, 15 Nov) | Command output; CI runs it on every push |

**Web** (`web/`, served by Vercel)

| Check | Result | Evidence |
| --- | --- | --- |
| Content-Security-Policy | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://finn-api-53vw.onrender.com https://*.ingest.de.sentry.io; manifest-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests`. No inline script or style anywhere | `web/vercel.json:15`; `sends a strict Content-Security-Policy on every path`, `index.html has no inline script or style`; `the security policy is enforced: an injected inline script does not run` (passed in Chrome against the production build) |
| Other headers | HSTS 2 years, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, a `Permissions-Policy` denying camera, microphone, location, payment and the rest | `web/vercel.json:17-25`; `sends the other security headers on every path` |
| API address and policy cannot drift | The build refuses a `VITE_API_URL` that `connect-src` does not list, plain http, a path, or a Sentry DSN on a host the policy does not allow; the API origin appears exactly once | `web/build/deploy-config.ts:78-137`; `refuses an API the security policy would block, plain http, or a path`, `accepts a Sentry DSN only on a host the policy allows`, `names the API origin exactly once` |
| No HTML injection | ESLint fails the build on `dangerouslySetInnerHTML`, `innerHTML`/`outerHTML` assignment, `insertAdjacentHTML`, `document.write`, `DOMParser`, `createContextualFragment`, inline styles, `eval`/`new Function` | `web/eslint.config.js`; `refuses HTML injection and inline styles` (now also under `CI=true`; see "Deploying B5 and B6") |
| Token in memory only | Never in localStorage, sessionStorage or a cookie; storage APIs are lint errors | `web/src/api/client.ts:109`; `keeps the token in memory only`; `web/eslint.config.js:63-68` |
| Service worker | Precaches the app shell; one runtime route, `/snapshot.json`; never the API (no API host or `/v1/` in `sw.js`) | `web/vite.config.ts:69-92`; `the service worker caches the app shell and the saved copy, never the API` |
| Error reporting | Loaded only when a DSN is set; collects no user details, cookies, headers, bodies or query strings; no trace headers on API calls | `web/src/sentry.ts` |
| Dependencies | `npm audit --omit=dev`: 0 vulnerabilities in what ships. `npm audit --audit-level=high` (CI's gate) passes. Of the three advisories in build and lint tooling, `glob` and `minimatch` are fixed by scoped overrides; `deepmerge` has no patched release and is accepted (see "Deploying B5 and B6") | Command output; `docs/notes/dependency-advisories.md` |

**Secrets**

| Where | What | Evidence |
| --- | --- | --- |
| GitHub Actions secrets | The settings from `.env` (`gh secret set -f .env`). Only `ingest` (`SUPABASE_DB_URL`) and `migrate` (database URL and Supabase keys) read any; both run only on schedule or by hand, never on `pull_request`, so a fork's pull request cannot reach them | `.github/workflows/ingest.yml:51`, `migrate.yml:42-45`; triggers read from every workflow |
| Render | `SUPABASE_DB_URL` and `SENTRY_DSN_API` entered by hand (`sync: false`), `SESSION_SECRET` generated; origins are public | `render.yaml` |
| Vercel | Public build values only (`VITE_API_URL`, `VITE_NETWORK_ENABLED`, optional `VITE_SENTRY_DSN`, which is public by design). Nothing secret reaches the browser | `web/.env.example` |
| Repository | `.env` and `.env.*` ignored at every level (`.env.example` kept); only the two examples are tracked | `.gitignore:17-20`; `git check-ignore` on `.env`, `pipeline/.env`, `web/.env.local`; `git ls-files` |
| Secret scan | gitleaks 8.30.0: lead clone history (35 commits) and working tree (28.7 MB), no leaks. GitHub's own history is scanned by CI on every push (last confirmed green: run 43706005413, `1ee59da`) | Command output |

**CI and supply chain**

| Check | Result |
| --- | --- |
| Token scope | Every workflow `permissions: contents: read` |
| Script injection | Every workflow input reaches the shell through an environment variable, never `${{ }}` inside `run:`; the ingest script validates each argument (`set -f`, argparse) |
| Pinning | Actions pinned to major tags (`actions/*@v7`), gitleaks by image tag `v8.30.0`; Python tools pinned exactly in `requirements-dev.txt`; npm lockfile with exact versions |
| Gates | `pip-audit`, `npm audit --audit-level=high`, gitleaks over full history, lint, types and tests on every push; Render deploys a commit only after every check on it passes (`autoDeployTrigger: checksPass`) and only when API or pipeline code changed (`buildFilter`) |

**Residual risks, accepted for now**

1. **The database login is the admin.** The API and ingest connect with Supabase's `postgres` login
   and narrow to `finn_api`/`finn_ingest` per transaction (B2's honest limit). Least privilege holds
   along every code path above, by test, but not against code that is already compromised. Before
   phase G stores network data: create login roles for `finn_api` and `finn_ingest` with their own
   passwords, and give Render and Actions those instead.
2. **The demo session is public by design.** `Origin` is a browser rule, not a secret: any client
   that sends `Origin: https://finn-lac.vercel.app` gets a read-only demo token. What it reads is
   what the site shows anyone (public filings, fictional holdings), bounded by the rate limits. Real
   investors would need real authentication.
3. **Rate limits are in memory.** One instance, one worker: exact while that holds; they reset when
   the free service sleeps or restarts.
4. **Availability.** Render's free service sleeps after 15 idle minutes and takes about a minute to
   wake. Mitigated by an external monitor (UptimeRobot, every 5 minutes, which also emails if
   `/health` stops reporting the database), the keep-warm workflow as a backup, and the saved copy
   (`web/public/snapshot.json`), which the app shows with its date if the API does not answer.
5. **Actions pinned by tag, not commit SHA.** All are GitHub's own actions running with a read-only
   token; pinning by SHA is the next hardening step.
6. **`connect-src https://*.ingest.de.sentry.io`** allows any Sentry EU ingest host. It matters only
   if script injection succeeded, which `script-src 'self'` and the lint rules prevent.
7. **No HSTS preload.** `onrender.com` and `vercel.app` are not FINN's domains to list.

**Verified live** (15 Nov 2026, 19:21 IST, from Karthik's laptop, after Render's origins were set
and the saved copy was deployed; the commands are below, to repeat after any change to headers,
origins or sessions):

| Check | Expected | Live result |
| --- | --- | --- |
| Web headers, `finn-lac` (full) and `finn-hkmn` (core) | All seven, CSP exactly as in `web/vercel.json` | Both sites: CSP identical to the file (`connect-src` names only the API and Sentry EU), COOP `same-origin`, Permissions-Policy, `Referrer-Policy: no-referrer`, HSTS 2 years, `nosniff`, `X-Frame-Options: DENY` |
| API `/health` headers | 200 and the six security headers | 200; `default-src 'none'; frame-ancestors 'none'`, HSTS, `nosniff`, `no-referrer`, `DENY`, `Cache-Control: no-store`; no uvicorn `Server` header (the one shown is Cloudflare's, in front of Render) |
| Preflight from each site | 204, that exact origin, `GET, POST, OPTIONS`, `Authorization, Content-Type`, max-age 600 | Both 204 with their own origin echoed and exactly those values |
| Preflight from `https://example.com` | 403, no grant | 403, no `access-control-allow-origin`, `This website may not use FINN's API.` |
| Session from each site, and from none | full: `network: true`; core: `network: false`; none: 403 | Exactly that; tokens carry `dep: full` / `dep: core`, `ro: true`, 12-hour expiry |
| A token on the other site; no token | 401, 401 | 401, 401; the same token on its own site returned the 7-day summary |
| Saved copy | 200 | 200 |

Both sites, opened on a phone, start a session and show the brief. Still to see once: a deliberate
test error reaching each Sentry project with nothing personal in it. Rate limits are not tested
live (61 requests lock the address out of `/v1` for a minute); the tests cover them.

```powershell
$api  = "https://finn-api-53vw.onrender.com"
$full = "https://finn-lac.vercel.app"
$core = "https://finn-hkmn.vercel.app"
curl.exe -sI "$full/" | Select-String "content-security-policy|strict-transport-security|x-frame-options|x-content-type-options|referrer-policy|cross-origin-opener-policy|permissions-policy"
curl.exe -sI "$core/" | Select-String "content-security-policy|strict-transport-security|x-frame-options|x-content-type-options|referrer-policy|cross-origin-opener-policy|permissions-policy"
curl.exe -sI --max-time 120 "$api/health"
curl.exe -si -X OPTIONS "$api/v1/digest" -H "Origin: $full" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
curl.exe -si -X OPTIONS "$api/v1/digest" -H "Origin: $core" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
curl.exe -si -X OPTIONS "$api/v1/digest" -H "Origin: https://example.com" -H "Access-Control-Request-Method: GET"
curl.exe -s -X POST "$api/v1/session/demo" -H "Origin: $full"
curl.exe -s -X POST "$api/v1/session/demo" -H "Origin: $core"
curl.exe -s -X POST "$api/v1/session/demo"
$t = (curl.exe -s -X POST "$api/v1/session/demo" -H "Origin: $full" | ConvertFrom-Json).token
(curl.exe -s "$api/v1/digest?hours=168" -H "Origin: $full" -H "Authorization: Bearer $t" | ConvertFrom-Json).summary
curl.exe -s -o NUL -w '%{http_code}\n' "$api/v1/digest" -H "Origin: $core" -H "Authorization: Bearer $t"
curl.exe -s -o NUL -w '%{http_code}\n' "$api/v1/digest" -H "Origin: $full"
curl.exe -s -o NUL -w '%{http_code}\n' "$full/snapshot.json"
```

**Deployed** (15 Nov 2026): API `https://finn-api-53vw.onrender.com`; full edition
`https://finn-lac.vercel.app` (Vercel project `finn`); core edition `https://finn-hkmn.vercel.app`
(Vercel project `finn-hkmn`, named so by Vercel; the address is what reviewers get). Keep-warm
installed (variable `API_URL`), UptimeRobot keyword monitor on `/health` every 5 minutes, saved
copy committed (`94b2e67`: 11 needing attention, 13 worth knowing, 34 routine, data as of 19:04).
Gate G1 waits only on its own definition: a filing brought in by a *scheduled* run, seen as a card
on a phone. GitHub had not started any scheduled run by 19:13 (see "Deploying B5 and B6"); the
workflow was disabled and re-enabled at about 19:00 to re-register the schedule.

## The final sprint: phases C, D, E and G in one evening (15 Nov 2026)

The deadline turned out to be tonight, not open-ended. Decision: build all four remaining layers at
once, as four agents in separate copies of the repository with fixed ownership and interfaces
(`docs/notes/sprint-15nov.md`), merged and checked by the lead, shipped in waves so that what is
live is always coherent. Each stream's notes say what it built and what it did not:
`docs/notes/llm.md`, `push.md`, `pull.md`, `network.md`.

**What shipped.**
- **C, models** (`finn/llm.py`, `finn/guard.py`): roles, not models, with fallback chains across
  four free providers; documents screened for prompt injection (Llama Prompt Guard 2), fenced
  between random markers, never given tools; answers schema-checked with one repair; cached and
  logged. Verified live (`llm-check`): every role answered; the guard flagged an obvious injection
  (score 1.00) and passed an ordinary sentence.
- **D, Push**: results items carry the quarter's numbers from the company's own XBRL (revenue,
  EBITDA, PBT, PAT, QoQ and YoY); price and volume moves tied to the filing that may explain them,
  or listed as moves without a filing; promoter pledges dated as NSE published them.
- **E, Pull**: a research page for any NSE company (price, filings, and for covered companies nine
  quarters of results); for covered companies, the promise ledger, business snapshot and bull and
  bear case, read from the last four earnings calls and the annual report. A claim survives only if
  its quote is found in the cited document, and a "delivered" number only if it is one FINN read
  from XBRL. First live company (TCS): 11 promises; kept 1 of 2 measurable, 1 missed, 5 too early,
  4 not measurable; 3 snapshot points, 5 bull and 3 bear, every one quote-checked.
- **G, Network** (full edition only): 150 fictional people overlapping the covered companies, owned
  by the investor under RLS, questions answered in code (no model ever sees network data), "who to
  call" on brief items and from the research page; a core session gets 404 for every network route
  and the core build contains no network code.

**What went wrong live, and the fixes.**
1. **The API stopped deploying after Wave 1.** The digest began importing the pipeline's XBRL
   parser, which needs `defusedxml`; it was not in `api/requirements.txt`, so the service crashed
   at start on Render and Render kept serving the old version. CI installs every tool at once and
   could not see it. Fixed, and CI now starts the API from `api/requirements.txt` alone.
2. **The new app refused old-format briefs** (the old API, and the saved copy made before results
   were added). The app now reads fields added after the first deploy as absent when missing, and
   still refuses anything present in the wrong form, so the order in which Vercel and Render deploy
   cannot break it.
3. **The injection screen was rate-limited.** The first live analysis asked Groq up to 48 times per
   document at once and was refused on every document; the screen failed closed as designed, so
   nothing was read. Now at most 8 windows per document, calls paced under the per-minute limit, a
   refused window retried, and parallel batches given their share of the minute.
4. **NSE serves attachments from a second host** (`nsearchives.nseindia.in`, 5% of a recorded week's
   links); links there were shown as text. Both hosts are now allowed; nothing else is.
5. **Manappuram's results read as a bank's** came out as "PAT ₹0 cr". A lender's card is now shown
   only when the bank template finds interest expended and a profit line; otherwise the company's
   own words stay and no number is shown. A lender template for NBFCs is the fix (not built).
6. **GitHub's scheduler never started a scheduled run** for this repository, even after the
   workflow was disabled and re-enabled. Data is refreshed by hand (`gh workflow run ingest.yml -f
   job=filings`) until an outside trigger calls `workflow_dispatch` on a schedule; that needs a
   token stored with a free cron service, Karthik's decision, not taken tonight. Gate G1's
   "scheduled filing on a phone" is therefore not met as worded.

**Not built tonight** (each said in the app where it matters): an NBFC results template; alert
settings, feedback and decision notes in the app; document search and the ask box (embeddings);
deep analysis on demand for a company outside coverage; five-year annual figures, balance sheet and
cash quality; narrative versus numbers as its own section; model evaluation (C4); importing a real
Connections.csv; matching people named in filings to the network (G3); failure drills.

