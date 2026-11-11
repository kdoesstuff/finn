# FINN: task pipeline to submission

Sequence only; no clock times. Decisions settled with Karthik on 11 Nov 2026 are in
`docs/DECISIONS.md`. No product code is written until Karthik approves this plan.

## Where we stand

- Foundations verified on 11 Nov (46 tests, classifier numbers, parser, portfolio facts). Six defects
  found by testing are repaired in task A3 before anything is built on them.
- Results filed before ingestion goes live are backfilled in B4; nothing is lost, because NSE serves
  400 days of filings per symbol and every results XBRL.

## Rules for every task

A task is done only when: its tests pass in CI, lint and type checks are clean, the deployed build
still works end to end, and the change is committed with a decision-stating message. A gate passes
only when the deployed build works on a phone, the whole suite is green, and the phase's security
review is written into `docs/DECISIONS.md`. Nothing starts on a red build.

**Change from the handoff skeleton:** there is no separate frontend phase. Each screen ships with its
API (B6, D7, E8, G5), so the deployed app grows by working slices instead of arriving on the last day.

**If a task proves harder than expected**, the phase does not move on with it half-working. The
task is either finished or removed whole, in this order of removal: web push notifications -> bull vs
bear and narrative vs numbers -> Network expertise map and reconnect prompts -> dark theme.
**Never removed:** evidence links, tests, security review, deployed gates, promise ledger, Network
who-to-call on Push cards (Founding requires all three layers working). Sign-up is out of scope by
decision: reviewers use a one-tap, read-only demo investor.

## Order of phases

A Repair and decide -> B Data foundation and first slice -> C Model layer -> D Push -> E Pull ->
G Network -> H Hardening -> I Submission. Each ends in a gate. After gate G4 (Push and Pull
finished) `finn-core` is submittable; Network is added on top of that working build.

---

## Phase A: repair and decide

**A1 Record decisions.** Goal: section 14 settled. In: Karthik's answers. Out: `docs/DECISIONS.md`
(decision, alternatives, evidence), this plan revised. Deps: none. Done: every open item has an owner
and an answer. Verify: Karthik confirms the file.

**A2 Requirements checklist.** Goal: plan checked against what ENAM wrote. In: both briefs, the
glossary and both job forms (read 11 Nov; the campus deck has not been supplied). Out:
`docs/REQUIREMENTS.md`, each brief line mapped to a task here. Deps: none. Done: no brief requirement
without a task. Verify: line-by-line review. Differences from the handoff already folded in below:
- Founding asks for at least one working workflow per layer, with Network woven into Push **or**
  Pull and also queryable directly. Depth is our call, which is what makes the cut order safe.
- "Tell me the moment something crosses a threshold": alerts need a delivery surface (D6).
- Trajectory is "multi-year", not eight quarters (E4).
- The bio of an incoming person may use outside sources ("e.g. from LinkedIn"); only Pull is
  restricted to primary sources (D2).
- The writeup is short and lives in the covering email for both roles (I3).

**A3 Repair the six verified defects.** Goal: nothing is built on a known fault.
In: findings of 11 Nov. Out, each with a regression test taken from the real filing that exposed it:
1. Filing identity = NSE `seq_id`. Merge only NSE/BSE copies and true resubmissions (same PDF name
   stem within minutes). Today 264 of 4,795 distinct filings are dropped, 54 of them attention-level.
2. Event grouping: several filings about one event (Asian Paints' two filings on one appointment;
   Sadbhav's three on one auditor exit) become one card listing its filings.
3. Roles from the filing's own words only, never from the NSE label; "non-executive director" is
   not MD; reappointment scored below a first appointment.
4. Auditor exit = statutory auditor of the company (100). Cost, internal and secretarial auditors and
   a subsidiary's auditor rank lower (5 of the 14 flagged items are these).
5. Litigation scored by kind and size: insolvency/default stay 100; tax and GST orders start at
   "worth knowing" and rise only when the amount is material against net worth (56 items sit at 85+
   today, GST show-cause notices among them).
6. Pledge fields named for what they are: `percPromoterShares` (of promoter holding),
   `percTotShares` (promoter pledge, of all shares), `percSharesPledged` (all demat pledges, any
   holder). Alerts: report the threshold that actually fired; use the exchange's trading dates.
Deps: none. Done: classifier measurement re-run and the new numbers recorded; handoff facts corrected.
Verify: new tests fail on the old code and pass on the new; `measure_classifier.py` output reviewed.

**A4 CI.** Goal: every push tested. Out: workflow (ruff, mypy, pytest, pip-audit, gitleaks) in
`workflows-to-install/`. Deps: none. Done: green on `main`; a deliberately failing test turns it red.
Verify: Actions run links.

**A5 Setup checker.** Goal: every setting proven. Out: `check_setup.py` makes one `embedContent`
call at `GEMINI_EMBED_DIM` and asserts the vector length; secrets re-synced (22 settings exist, the
handoff says 20 were copied). Deps: Karthik runs it (only his laptop reaches the APIs). Done: 9 of 9.
Verify: pasted output.

**Gate G0.**

## Phase B: data foundation and first slice

**B1 Fetchers package** `finn/sources/`. Goal: one tested way to reach each source in handoff
section 8. In: probe scripts. Out: NSE session (cookie warm-up, 0.7 s pacing, retry with backoff and
jitter, timeouts), typed fetchers for announcements, Integrated Filing and legacy results (latest
revision per quarter and basis), bhavcopy, pledges, board meetings, annual reports, per-symbol
insider trades, corporate actions; XML parsed with `defusedxml`. Deps: A3. Done: each fetcher has a
fixture test and a recorded-response test for 401/403/timeout. Verify: CI, plus one manual Actions
run against live NSE with row counts logged.

**B2 Database.** Goal: schema with privacy built in. Out: SQL migrations in `db/migrations/`:
market data (companies, filings, events, results_quarters, prices_eod, signals, pledges, documents,
chunks with `vector(768)`, promises, llm_calls) and investor data (profiles, portfolios, holdings,
theses, prefs, feedback); RLS enabled and deny-by-default on every table. Deps: none. Done: migrations
apply cleanly to an empty project. Verify: tests that connect with the publishable key and prove
every table refuses read and write; a schema diff check in CI.

**B3 Scheduled ingest.** Goal: data arrives without anyone at a keyboard. Out: Actions workflows:
filings every 30 min 08:00-23:30 IST at off-peak minutes; EOD at 19:30 IST driven by whether a
bhavcopy exists for the date (10 Nov was a holiday, Sun 8 Nov had a Muhurat session, so weekday logic
is wrong); pledges and board meetings daily; idempotent upserts keyed by `seq_id`; a run log row per
run; a daily JSON snapshot committed to `snapshots/`. Deps: B1, B2. Done: three consecutive scheduled
runs succeed and re-running one changes nothing. Verify: run log table; duplicate-count query is 0.

**B4 Backfill.** Goal: history for Push and Pull. Out: filings from 1 Oct for the portfolio, eight
quarters of results per name (including Mar-Sep 2025, missing from fixtures, so YoY on the current
quarter is tested), 90 sessions of prices, 10-11 Nov results. Deps: B3. Done: every portfolio name has
its Sep 2026 results or a recorded reason. Verify: TCS, HDFC Bank and Asian Paints figures match the
values already verified in the handoff; counts per name printed.

**B5 API skeleton** (FastAPI on Render, Singapore). Goal: the only door to the data. Out: `/health`,
`/v1/digest` from stored data; pydantic validation (ticker pattern, date range, sizes); CORS
allow-list of the two frontends; rate limiting; security headers; Sentry with PII scrubbing; server
holds the Supabase secret key. Deps: B2. Done: deployed, returns the stored digest. Verify: API tests
in CI; a request from a disallowed origin and a malformed ticker are refused.

**B6 Web skeleton** (Vite, React, TypeScript, PWA; Vercel `finn-core` and `finn`). Goal: the first
card on a phone. Out: design tokens (paper-and-ink default; restyled from Karthik's references when they arrive, a token change only), brief screen reading the API, "waking up" state, fallback
to the bundled snapshot with a "data as of" label, CSP, no `innerHTML`. Deps: B5. Done: both sites
live. Verify: opened on a real phone at 360 px; CSP header checked; Playwright smoke test in CI.

**B7 Keep-warm.** Goal: reviewers never meet a cold start. Out: an external 5-minute uptime monitor
on `/health` as the primary, the Actions ping as backup (scheduled Actions runs are delayed or
dropped under load, and Render sleeps after 15 idle minutes). Deps: B5. Done: 12 hours without a
gap over 10 minutes. Verify: monitor log; instance-hours projection under 750.

**Gate G1.** A filing ingested by the schedule appears as a card on a phone. Security review: RLS
tests, secret scan, headers, CORS.

## Phase C: model layer

**C1 Router.** Goal: code asks for a role, never a model. Out: roles from `config.py`; pacing to each
model's per-minute limits; fallback chain of handoff section 5; response cache keyed by hash of
(role, prompt version, inputs); every call logged to `llm_calls` (tokens, latency, cache hit,
fallback used); JSON outputs validated against a schema with one repair attempt, then the rescue
tier. Deps: B2. Done: unit tests with a fake provider cover 429, timeout, bad JSON and cache hit.
Verify: CI; one live call per role from Karthik's laptop.

**C2 Injection defence.** Goal: filing text is data. Out: guard model in front of every call that
reads filing text; delimited input; no tools on document-reading calls; outputs schema-checked. A
type-level rule that network data cannot be passed to the router at all. Deps: C1. Done: a red-team
set of filings carrying injected instructions changes no output. Verify: the red-team tests in CI.

**C3 Filing reader.** Goal: the ~10% of filings rules cannot name, for portfolio companies only.
Out: PDF text extraction locally first (model PDF reading only for scans); category, one-line "what
changed", and the quote it rests on. Deps: C1, C2. Done: the generic-label filings of the portfolio
in the fixture week are all classified. Verify: Karthik spot-checks 20 against the PDFs; quote
string-matches the source text.

**C4 Model evaluation.** Goal: routing justified by measurement. Out: the same guidance-extraction
prompt on the TCS transcript run on the reader, the rescue tier and GLM; precision and recall against
a hand-marked list, latency, tokens. Deps: C1. Done: results table in `DECISIONS.md`; routing changed
if the numbers say so. Verify: the marked list and raw outputs are committed.

**Gate G2.** Security review: injection tests, no secrets in logs, cache cannot serve one user's
data to another.

## Phase D: Push complete

**D1 Results card.** Out: general, bank and lender templates (lender: interest income, finance
costs, net interest income, impairment, PAT; confirmed against Manappuram's and Bajaj Finance's
XBRL); latest revision; audited or unaudited shown; every number linked to its XBRL; cross-check
against NSE's own `results-comparision` table. Deps: B4. Done: all 18 names render; mismatches with
NSE's table are zero or explained. Verify: fixture tests per template; the 12 Nov filings parsed live.

**D2 Management-change card.** Out: who, role, action, effective date, and a short bio of the
incoming person taken from the filing's own profile section, with the quote and page (the brief
allows outside enrichment here; anything not from the filing is labelled with its source). On `finn`
the card also says whether anyone in the network worked or studied with them, or sits one connection
away (wired in G5). Deps: C3, A3.
Done: Leo Puri (Asian Paints) and the HDFC Bank change render correctly. Verify: bio sentences
string-match the PDF; no sentence without a source.

**D3 Pledge, governance and insider cards.** Out: pledge level and change between snapshots (Kalyan
24.85% of promoter holding; Asian Paints 10.35%), related-party, insider trades per symbol. Deps: B4,
A3. Done: values equal the NSE fields. Verify: fixture tests.

**D4 Price and volume alerts.** Out: real price history; per-investor thresholds; moves attached to
the filing that explains them, otherwise "unexplained"; corporate-action days excluded using the
corporate-actions feed. Deps: B4, A3. Done: back-test over 90 sessions for the portfolio reviewed.
Verify: tests on real bars including one bonus or split date; Karthik reviews the fired list.

**D5 Thesis and values.** Out: a two-line thesis per holding (drafted, Karthik edits: he will be
asked about them); each item tagged supports / challenges / neutral with the quote behind the tag;
excluded-sector flag. Deps: C1. Done: 18 theses approved. Verify: tags reviewed for one week of items.

**D6 Digest API.** Out: window (24 h default, 3 d, 7 d, since last visit), alert categories and
thresholds per investor, ranked sections, routine counts, "why am I seeing this", feedback and
decision-note endpoints; an alerts feed of threshold crossings since the last visit, with an unread
badge (web push notification is a stretch item, cut first). Deps: D1-D5. Done: contract tests. Verify: a quiet window returns "Nothing
material across your portfolio."

**D7 Push screens**. Out: the brief, event cards, evidence drawer, settings, quiet and error
states, one-tap demo investor. Deps: D6. Done: journey test passes. Verify: Playwright at 360 px;
keyboard and screen-reader pass; real phone.

**Gate G3.** Security review: authorisation on every endpoint, rate limits, demo investor is
read-only.

## Phase E: Pull complete

**E1 Company resolution.** Out: any NSE ticker or name to a company (symbol master from bhavcopy).
Deps: B4. Done: 20 random EQ symbols resolve; junk input refused. Verify: tests.

**E2 Document acquisition.** Out: latest annual report and the last four to five concall transcripts
from NSE filings, BSE PDF links as fallback; coverage reported ("3 of 4 transcripts found").
Deps: B1. Done: portfolio and research names fetched. Verify: counts table; a name with no
transcripts gives an honest gap, not an error.

**E3 Chunks and embeddings.** Out: page-anchored chunks, 768-dim vectors in pgvector, embedded once
per document hash, within the 1,000/day quota. Deps: E2, C1. Done: retrieval returns the right page
for 10 hand-written questions. Verify: that retrieval test in CI on the TCS transcript.

**E4 Numbers.** Out: financial snapshot with key ratios; trajectory over five financial years
(annual figures from the results filings) plus the last eight quarters, all from XBRL; balance sheet and
cash quality, downside first (leverage, pledging, cash conversion, contingent liabilities, auditor
remarks, RPTs). Deps: B4. Done: figures for TCS match the filings. Verify: fixture tests.

**E5 Promise ledger** (the centrepiece). Out: each guidance statement from four quarters of
transcripts (quote, page, metric, target, horizon), matched to the delivered number from XBRL or the
later call; status kept / missed / partly / too early / not measurable; summary as plain counts
("kept 5 of 8 measurable promises"). Deps: E3, E4, C4. Done: ledgers for all 21 names; none contains
a number absent from its source. Verify: Karthik audits two ledgers line by line against the PDFs;
automatic quote and number checks in CI.

**E6 Remaining menu.** Out: business snapshot, guidance, narrative vs numbers, bull vs bear, each
sentence cited. Deps: E3. Done: renders for all names. Verify: citation coverage 100%; quote check.

**E7 Pull API.** Out: streamed progress (server-sent events), per-company cache, cold path for an
unknown ticker, tight rate limit. Deps: E1-E6. Done: cold run completes inside the measured budget.
Verify: three unseen tickers (a bank, an NBFC, a small cap with no calls) end to end.

**E8 Pull screens.** Out: company page with the ledger first, evidence drawer, ask box scoped to
this company's documents. Deps: E7. Done: journey test. Verify: Playwright; real phone.

**Gate G4.** `finn-core` is submittable from here on. Security review: the ask box cannot reach
outside the company's documents; injection red-team re-run on transcripts.

## Phase G: Network

**G1 Synthetic network**. Out: the persona; about 150 fictional people in LinkedIn's
Connections.csv format plus career histories, generated from a seed, overlapping the portfolio
(former employees, auditors, suppliers, classmates); labelled synthetic in the app. Deps: none.
Done: file imports. Verify: generator is deterministic; no real individual's name appears.

**G2 Graph and privacy.** Out: people, organisations, typed and weighted edges with dates; rows owned
by the investor under RLS; import and delete-everything endpoints; retention stated. Deps: B2.
Done: a second user sees nothing of the first. Verify: RLS tests as two users; delete leaves no rows.

**G3 Entity resolution.** Out: names in filings matched to people and organisations, conservatively:
a match needs name plus employer and period overlap, and shows its confidence. Deps: G2, D2.
Done: no match on name alone. Verify: tests with same-name decoys.

**G4 Questions.** Out: who worked with this person, who can explain this deal, second-degree path,
diligence on a person, expertise map, reasons to reconnect, all computed in the database and code;
one "ask your network" screen where these can be queried directly, as the brief requires.
Deps: G3. Done: each returns a result with the path that justifies it. Verify: tests on the seed graph.

**G5 Woven in.** Out: the brief's two named examples (incoming executive: who worked or studied
with them or sits one step away; material event: the person best placed to explain it, and why) on
Push cards, and "who to call" on the Pull page; `NETWORK_ENABLED` enforced in
the API per deployment and per user, and in the client. Deps: G4. Done: `finn-core` exposes no
Network data or routes. Verify: API tests from the `finn-core` origin; no model call ever carries
network data (router test from C2).

**Gate G5.** Security review: the privacy model end to end.

## Phase H: hardening

**H1 Security review.** Checklist: authorisation per endpoint, RLS as each role, input fuzzing, CSP,
rate limits, dependency audit, secret scan of history, injection red-team. Done: no open finding.
**H2 Failure drills.** NSE refusing, Supabase down, model quota gone, backend asleep: each degrades
to a labelled last-good view. Done: all four demonstrated.
**H3 Phones.** Android Chrome and iOS Safari, 360 px, light and dark, Lighthouse, accessibility.
**H4 Measurements.** Digest p95, cold Pull time, calls and cache hit rate per Pull, into
`DECISIONS.md`. **Freeze**: fixes only from here.

## Phase I: submission

**I1** Architecture diagram. **I2** README (try-it link, setup, tests). **I3** A short writeup in each covering email, written from `DECISIONS.md`; the Founding one adds
architecture (pipelines, security and privacy, models and agents, cloud) in a few lines and links to
`docs/ARCHITECTURE.md` with the diagram; synthetic network data stated plainly with how it would be
done for real.
**I4** Build-history links. **I5** Final check from the links in the draft emails, on a phone, on
mobile data. **I6** Two emails.

## What only Karthik can do

Run workflows and `check_setup.py`; commit and push; create the Render service and two Vercel
projects; attach the source documents; approve theses and the portfolio; audit two promise ledgers;
ask the placement cell about two applications; test on his phone.
