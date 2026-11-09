# FINN build: handoff from the foundations session

Written 9 Nov 2026 at the end of the first build session (setup, data discovery and core logic).
Give this file to a new session together with the two briefs, the glossary, the two job descriptions
and ENAM's campus deck. Everything below was verified against real data unless marked otherwise.

---

## 1. The challenge in one paragraph

ENAM Holdings (Mumbai family office, value investors, Buffett-Munger style, ~50-100 people) set a build
challenge for two campus roles: **AI/ML Engineer** and **Founding AI Engineer**. Released 8 Nov 2026,
**due 15 Nov 2026**. Deliverable: a mobile-first working prototype of **FINN**, a financial investment
agent, plus a public GitHub repo, the AI build history (chat links) and a covering-email writeup.
FINN has **Push** (proactive digest and alerts on a 15-20 stock NSE portfolio), **Pull** (on-demand
research on any NSE company, grounded only in annual reports and concall transcripts) and, for the
Founding role only, **Network** (who in the investor's own network can explain this). Graded on
creativity, product sense, judgment and architecture, not completeness. "A demo that doesn't run is the
worst outcome."

| | AI/ML Engineer | Founding AI Engineer |
| --- | --- | --- |
| Layers required | Push + Pull ("one or two workflows" nailed) | Push + Pull + Network, all three with a working workflow; Network woven into Push/Pull |
| Writeup | What, decisions, trade-offs, left out, next | Same + architecture: data pipelines, security and privacy, LLMs and agents, cloud, diagram |
| Email subject | `IIT Delhi – AI Engineer - 2027` | `IIT Delhi – Founding AI Engineer - 2027` |
| CTC | 21-28 L | 42-56 L |

**Decided:** one codebase built to the Founding spec, with the Network layer behind a switch
(`NETWORK_ENABLED`), deployed twice: `finn-core` (Push + Pull) for the AI/ML email and `finn` (full) for
the Founding email. Build Push + Pull to a finished state first, then add Network.

**Karthik's stance:** aim for the upper bound on every feature, production-level security and detail, but
keep a deployed, working version at the end of every layer.

## 2. The ENAM lens (what the product should feel like)

Sources: enam.com (About, Culture, Investment Philosophy, Management Team), ENAM's Aug 2026 campus deck
"AI-led Transformation", a 2022 CFA Society talk by Vallabh Bhanshali. A fuller version is the
"ENAM Playbook for the FINN Build" doc from the first session.

- **Philosophy:** long-term (8-10 yr average hold, 25% IRR goal), margin of safety, bottom-up, invest in
  management and capital allocation, contrarian, degree of upside over hit rate. Also runs a short-term
  book and F&O, so price/volume alerts are legitimate.
- **Culture:** integrity, humility (circle of competence), objectivity, "forever students" who admit
  mistakes. Understated; founders are spiritual and low-profile.
- **Exclusions (hard rule for the demo portfolio):** intoxication (alcohol), gambling, tobacco, meat and
  poultry, hotels, anything that harms living creatures.
- **Their AI roadmap (campus deck):** Wave 1 "The Brain" encodes 40 years of decisions and biases
  (selection, timing, sizing, valuation) into a model with a screener, position monitor and decision
  copilot. Wave 2 "The Arms" are research tools: News & Sentiment Dashboard, **Earnings Call Analyzer
  (promises vs delivery, credibility scoring)**, Broker Report Synthesizer, Trade Signal Dashboard,
  Excel Model Builder. Position FINN as a Wave 2 arm built to plug into Wave 1.
- **Design principles agreed:**
  1. Rank by ENAM's order: management and governance, then business, then price, then paperwork.
  2. Every holding has a short thesis; alerts are tagged supports / challenges / neutral.
  3. Promise vs delivery is the centrepiece of Pull (their Earnings Call Analyzer).
  4. Downside first (leverage, pledging, cash conversion, contingent liabilities, auditor remarks, RPTs).
  5. Evidence always: every number links to its filing; parsed numbers before model output.
  6. Say what you don't know; never fill gaps from model memory.
  7. Quiet by default: "Nothing material today" is a valid output; collapsed routine shown as a count.
  8. Relationships are an asset (Network), private and consent-based.
  9. Learn and unlearn: feedback and decision notes become Wave 1 training data.
  10. Values as a filter: excluded sectors; flag a holding entering one.
- **Vocabulary to use:** thesis, management quality, capital allocation, promise vs delivery,
  credibility, margin of safety, circle of competence, governance, cash conversion. **Avoid:** alpha,
  sentiment scores, "AI-powered", hype, emoji, anything that looks like a retail trading app.

## 3. How this repo is worked on

- **Repo:** https://github.com/kdoesstuff/finn (public, MIT). Local clone on Karthik's Windows laptop at
  `C:\Users\Karthik\OneDrive\Desktop\Enam-finn\finn`, connected to Claude through the desktop app.
- **Roles:** Claude writes code into the folder; Karthik reviews in VS Code, commits and pushes. Commit
  messages state a decision, not an activity. Git identity: Kedhar Karthik Naidu Rejeti,
  `kdoesstuff` no-reply email.
- **`.github/` is protected from Claude's file tools.** New or changed workflow files go into
  `workflows-to-install/`, then Karthik runs `Move-Item -Force workflows-to-install\*.yml .github\workflows\`.
  That folder cannot be deleted by Karthik (created by the remote tool); git ignores it while empty.
- **Network reach differs by machine:**
  - Claude's cloud workspace: only package registries and GitHub. **Cannot reach NSE, BSE, Yahoo,
    screener or any LLM API.**
  - Claude's sandbox on the laptop (device shell): no reach to NSE either.
  - **GitHub Actions runners reach NSE, Yahoo and screener**, so all fetching runs there.
  - Karthik's own laptop has normal internet (used for `check_setup.py`).
- **Getting data from a workflow run into the repo:**
  ```
  $id = gh run list --workflow=<file>.yml --limit 1 --json databaseId --jq '.[0].databaseId'
  gh run watch $id
  gh run download $id -n <artifact> -D <folder>
  ```
  `gh run download` refuses to overwrite existing files: download into a fresh folder, then merge.
- **PowerShell:** `<placeholder>` breaks commands (`<` is an operator); give literal commands.
- **Models are configuration, not code:** every provider's base URL and model name live in `.env`
  (`GEMINI_MODEL`, `GROQ_MODEL`, `GLM_BASE_URL`, `GLM_MODEL`); code asks for a role, never a model name.
  GLM access is through Hyde's OpenAI-compatible gateway (inference.hyde.tech), model `hyde/glm-5.3-flash`.
- **Keys:** one local `.env` at the repo root (git-ignored; template `.env.example`).
  `python pipeline/scripts/check_setup.py` tests each key; `gh secret set -f .env` copies them to
  GitHub secrets. Code reads them through `pipeline/finn/config.py`.
- **Supabase:** project `clwjxnbfqnxxvynjpica` (Mumbai). Uses the **new** key types:
  `SUPABASE_PUBLISHABLE_KEY` (sb_publishable_, browser-safe with RLS) and `SUPABASE_SECRET_KEY`
  (sb_secret_, server only). They are not JWTs: send them in the `apikey` header only.
- **Repo security already on:** secret scanning, push protection, Dependabot alerts and security
  updates, CodeQL default setup, workflow permissions read-write.
- **Actions versions:** checkout, setup-python, upload-artifact all at **v7** (v4 targeted a retired Node).
- **OneDrive:** the folder syncs to OneDrive; move it out before `node_modules` arrives (open item).

## 4. Repo map (as of this handoff)

```
.env.example                  every setting, with where to get it
.gitattributes                LF everywhere
.github/workflows/            probe-sources, probe-documents, probe-integrated, capture-fixtures (all manual)
docs/HANDOFF.md               this file
pipeline/
  finn/
    taxonomy.py               categories and tiers (1 management, 2 business, 3 context, 4 routine)
    models.py                 Announcement, Classification, Bar, Signal, DigestItem
    classify.py               rules + NSE label map; marks leftovers for a model
    rank.py                   scores, reasons, digest sections, NSE/BSE dedupe, summary line
    alerts.py                 volume multiple and sigma-scaled price moves with minimum history
    results.py                Quarter / BankQuarter, EBITDA definition, QoQ/YoY rows, bank template
    xbrl.py                   results XBRL parser (legacy and Integrated Filing formats)
    config.py                 settings from .env or platform secrets
  scripts/
    probe_sources.py, probe_documents.py, probe_integrated.py   source discovery (kept for the writeup)
    capture_fixtures.py       saves real NSE samples; `python capture_fixtures.py integrated extras`
    measure_classifier.py     coverage of the classifier on a real week of filings
    check_setup.py            tests every key in .env
  tests/
    test_core.py, test_xbrl.py   46 tests, all passing
    fixtures/                 real NSE data (see section 6)
  requirements.txt, pyproject.toml
```

## 5. Data sources: what works from GitHub's servers

Probed 9 Nov 2026 from GitHub Actions. NSE needs a session: GET `https://www.nseindia.com` first
(sets cookies), then call `https://www.nseindia.com/api/...` with a browser User-Agent and a Referer.
Space requests ~0.7 s apart.

| Need | Source | Works | Notes |
| --- | --- | --- | --- |
| Filings (all companies, date range) | `api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` (+`&symbol=X`) | Yes | ~1,000 filings/day in results season; 400 days of history per symbol |
| Filing PDF | `attchmntFile` URL on nsearchives.nseindia.com | Yes | |
| Results index, pre-2025 | `api/corporates-financial-results?index=equities&symbol=X&period=Quarterly` | Yes | **Ends Dec 2024** |
| **Results, 2025 onward** | `api/integrated-filing-results?index=equities&symbol=X&page=N` | Yes | Paginated (`data`, `size`, `page`, `totalCount`); mixes `Integrated Filing- Financials` and `- Governance`; has `consolidated`, `audited`, `qe_Date`, `type_Sub` (Original/Revision), `xbrl`, `ixbrl` |
| Results XBRL | `xbrl` link in either index | Yes | One parser reads both formats |
| EOD prices, all stocks | `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` | Yes | UDiFF columns: `TckrSymb`, `SctySrs`, `ClsPric`, `PrvsClsgPric`, `TtlTradgVol`, `TtlTrfVal`; no delivery column |
| Price history | yfinance `SYMBOL.NS` | Yes | 5 years in one call; secondary source |
| Pledges | `api/corporate-pledgedata?index=equities` | Yes | `percSharesPledged`, `percPromoterHolding`, `shp` |
| Insider trades | `api/corporates-pit?index=equities&symbol=X` | **Per symbol only** | Market-wide query returns no rows |
| Annual reports | `api/annual-reports?index=equities&symbol=X` | Yes | PDF links up to FY2025-26; `api/annual-reports-xbrl` has structured AR data |
| Concall transcripts | NSE filings with desc `Analysts/Institutional Investor Meet/Con. Call Updates` and text "Transcript" | Yes | Per quarter: "Schedule of meet", "Link of Recording", "Transcript" |
| Upcoming results dates | `api/corporate-board-meetings?index=equities&from_date=..&to_date=..` | Yes | `bm_symbol`, `bm_date`, `bm_desc` |
| Also found (samples in fixtures) | `event-calendar`, `results-comparision` (NSE's own QoQ table), `corporate-share-holdings-master`, `corporates-corporateActions`, `corporate-credit-rating`, `related-party-transactions-master` | Yes | Not yet parsed |
| screener.in pages | `screener.in/company/X/consolidated/` | Yes | Document links point to company sites (may 403) and `bseindia.com/stockinfo/AnnPdfOpen.aspx` (works) |
| BSE API | `api.bseindia.com/...` | **No (403)** | Blocked even with a browser session; BSE *PDF* links still download |

The full list of 187 NSE API paths referenced by NSE's pages is in the probe output (`probe_integrated.json`
from run 42611747343).

## 6. Gotchas found in real data

1. **XBRL year-to-date trap.** Results files hold the quarter (`OneD`) and year-to-date (`FourD`).
   Filers stamp both contexts with the quarter's dates. The true period is in the
   `DateOfStartOfReportingPeriod` / `DateOfEndOfReportingPeriod` facts inside each context. `xbrl.py`
   uses those and picks the ~3-month context; a test guards it.
2. **Results moved to Integrated Filings in 2025.** The old index stops at Dec 2024.
3. **Revisions exist.** Asian Paints revised its Mar 2026 filing twice. Use the latest revision per quarter
   and basis.
4. **Values are whole rupees**; FINN shows ₹ crore (÷10^7).
5. **Banks file a different format** (`ResultType` "Banking Format": InterestEarned, InterestExpended,
   OperatingExpenses, ProvisionsOtherThanTaxAndContingencies, ProfitLossFromOrdinaryActivitiesBeforeTax).
   Consolidated bank PAT = `ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates`.
   Consolidated bank NPA fields are zero; NPAs are in standalone filings.
6. **Consolidated PAT** shown is attributable to owners (`ProfitOrLossAttributableToOwnersOfParent`).
7. **`hasXbrl` is "True" on every announcement**: carries no signal.
8. NSE filing text (`attchmntText`) is a one-liner, often "X has informed the Exchange about <label>".
   Generic labels ("General Updates", "Updates", ~70 "Outcome of Board Meeting held on <date>") need the
   PDF read; that is the cheap-model job.
10. **Gemini keys now start with `AQ.`** (Google's new "Auth keys"; the old `AIza...` keys are rejected
    since Sep 2026). They work on the **native** Gemini endpoint with the `x-goog-api-key` header (which
    `check_setup.py` and FINN use) and can fail on Gemini's OpenAI-compatible endpoint. Call Gemini
    natively or through Google's SDK, never through the OpenAI-compatible route.
9. **Inter-se promoter transfers** and **SAST Reg 29 disclosures** mention "acquisition"/"transfer of
   shares" but are not M&A. **NCLT sanctioning a merger** is M&A, not litigation. All fixed and tested.

## 7. What is built and measured

- **Classifier** (`classify.py`): exact NSE label map (~90 labels) + text rules + fuzzy label rules.
  Evidence order: a very specific content rule, then the exact NSE label, then the best remaining rule,
  then a model. Management changes extract role (CEO/CFO/MD/chair/COO/secretarial/director/auditor) and
  action. Added a `governance` category (RPTs, fraud, forensic audit, delayed results).
- **Measured on 4,795 real filings (3-9 Nov 2026):** 55.1% text rule, 23.9% exact NSE label, 11.4% fuzzy
  label, **9.5% need a model** (General Updates 214, Updates 131, Outcome of Board Meeting 107).
  Sections market-wide: routine 59%, attention 23% (mostly results in results season), worth 18%.
  Re-run with `python pipeline/scripts/measure_classifier.py`.
- **Ranker** (`rank.py`): tier base scores with modifiers and plain-language reasons; auditor exit,
  defaults, insolvency, forensic audit, fraud = 100; key-role exits 95; pledges 92; open offers 90;
  results 85. Signals within 3 days after a material filing add 15 and attach. Unexplained moves get
  their own section. NSE/BSE duplicates merged. Summary line ("Nothing material across your portfolio"
  when quiet). Sections: attention >= 75, worth 40-74, routine < 40 (collapsed into counts by kind).
- **Alerts** (`alerts.py`): volume vs 20-day average (needs 15 days), move as % and as sigma vs 60-day
  realised volatility (needs 40 returns); rule "pct", "sigma" or "either". Not yet run on real prices.
- **Results** (`results.py`, `xbrl.py`): Revenue, EBITDA, PBT, PAT with QoQ/YoY and margin change in bps;
  EBITDA = PBT before exceptional + finance costs + D&A − other income (stated on the card); % changes
  replaced by words on sign flips ("turned positive", "loss narrowed"). Bank template: NII, operating
  profit, provisions, PAT. Verified: TCS Q3 FY25 revenue ₹63,973 cr, PAT ₹12,380 cr; Asian Paints Q3 FY25
  revenue ₹8,549 cr, PAT ₹1,110 cr; HDFC Bank Q3 FY25 NII ₹38,126 cr; TCS Q2 FY27 (Jul-Sep 2026)
  consolidated revenue ₹73,188 cr, PAT ₹13,884 cr. All 39 fixture filings (15 legacy, 24 Integrated Filing) parse.
- **Tests:** 46, all passing (`cd pipeline; python -m pytest -q`).

## 8. Fixtures (real NSE data in `pipeline/tests/fixtures/`)

`nse_announcements.json` (4,795 filings, 3-9 Nov 2026, with `desc_counts`), `results_{TCS,HDFCBANK,ASIANPAINT}.json`,
`xbrl/` (15 legacy quarterly files, Dec 2023-Dec 2024), `xbrl_if/` (24 Integrated Filing files,
Dec 2025-Sep 2026, standalone and consolidated, including revisions), `integrated_*.json`,
`bhavcopy.csv` (6 Nov 2026), `pledges.json`, `insider.json`, `annual_reports_TCS.json`,
`tcs_call_filings.json`, `transcript_TCS.pdf`, `board_meetings.json` (3,414 meetings),
`event_calendar.json`, `results_comparison_TCS.json`, `shareholding_TCS.json`, `corp_actions_TCS.json`,
`credit_rating_TCS.json`, `rpt_TCS.json`.

## 9a. Keys and models (state at handoff)

`check_setup.py`: **8 of 8 working** (Gemini, Groq, GLM via Hyde, OpenRouter, Supabase publishable and
secret, Sentry API and web). All 13 settings copied to GitHub Actions secrets with `gh secret set -f .env`.

Models each key offers (9 Nov 2026), from `check_setup.py --models`:
- **Gemini text:** gemini-2.5-flash/-flash-lite/-pro, gemini-3-flash-preview, gemini-3.1-flash-lite,
  gemini-3.1-pro-preview, gemini-3.5-flash, gemini-3.5-flash-lite, gemini-3.6-flash, gemini-3.7-flash,
  gemini-3.8-flash, gemini-4-argon, gemini-flash-latest, gemini-pro-latest, gemma-4-26b/31b and others.
- **Gemini embeddings:** gemini-embedding-001, gemini-embedding-2, gemini-embedding-2-preview.
- **Groq:** openai/gpt-oss-20b, openai/gpt-oss-120b, qwen/qwen3.8-27b, meta-llama/llama-prompt-guard-2-22m/-86m,
  whisper-large-v3(-turbo).
- **GLM gateway (Hyde):** hyde/glm-5.3-flash, hyde/kimi-k3.
- **OpenRouter free:** nvidia/nemotron-3-ultra-550b-a55b, nemotron-3.5-super-vl, google/gemma-4-31b-it and others.

**Final assignment.** Limits below are this project's actual free-tier limits, read from AI Studio's
Rate Limit page on 9 Nov 2026 (they match published figures except Gemma's 16K tokens/min). Each model
has its own quota, so pairs of models add capacity.

| Role (setting) | Model | RPM / tokens per min / per day | Notes |
| --- | --- | --- | --- |
| Read documents (`GEMINI_MODEL`) | gemini-3.5-flash-lite | 15 / 250K / 500 | 1M context, native PDF |
| Overflow reader (`GEMINI_OVERFLOW_MODEL`) | gemini-3.1-flash-lite | 15 / 250K / 500 | Separate quota: 1,000 documents/day together |
| Rescue tier (`GEMINI_QUALITY_MODEL`) | gemini-3.8-flash | 5 / 250K / 20 | Stronger (ParseBench 71.2% vs 59.5%; AA index 59); for failed validations |
| Second rescue (`GEMINI_QUALITY_FALLBACK_MODEL`) | gemini-3.6-flash | 5 / 250K / 20 | 40 rescues/day together |
| Short-job backup (`GEMINI_VOLUME_MODEL`) | gemma-4-31b-it | 30 / **16K** / 14,400 | Too few tokens/min for whole transcripts; backs up Groq's short jobs |
| Fast jobs (`GROQ_MODEL`, `GROQ_FALLBACK_MODEL`) | openai/gpt-oss-120b, then gpt-oss-20b | each 30 / 8K / 1,000 | Same quota, so the larger model is free quality |
| Injection guard (`GUARD_MODEL`) | meta-llama/llama-prompt-guard-2-86m (Groq) | 30 / 15K / 14,400 | Filing text is untrusted input |
| Reasoning (`GLM_MODEL`) | hyde/glm-5.3-flash | Hyde shows no quota; test calls took 0.4-0.7 s | AA index 57, 1M context, always-on thinking; on HTTP 429 fall back to the rescue tier, then OpenRouter |
| Embeddings (`GEMINI_EMBED_MODEL`, `GEMINI_EMBED_DIM`) | gemini-embedding-2 at 768 dims | 100 / 30K / 1,000 | 8,192 tokens per input; batch endpoint; computed once and cached |
| Fallback (`OPENROUTER_MODEL`) | nvidia/nemotron-3-ultra-550b-a55b:free | ~50/day ($0-capped key) | Largest free model listed |

Routing rule for the model layer: rules first; document reader, then overflow reader on quota
exhaustion; on a failed validation, rescue tier then second rescue; reasoning on GLM with fallback;
every call cached by input hash; pace requests to each model's per-minute limit.

Rejected: hyde/kimi-k3 (about 64 s to first answer token, ~43 tokens/s, listed as deprecated by
Artificial Analysis); any `-latest` alias (moves silently). A quick confirmation run on one real
transcript is still worth doing and reporting in the writeup.

Sources: AI Studio Rate Limit page for this project (9 Nov 2026); imisofts.com/blog/gemini-api-free-tier-limits;
console.groq.com/docs/rate-limits;
benchlm.ai/compare/gemini-3-5-flash-lite-vs-gemini-3-8-flash; benchlm.ai/models/gemma-4-31b;
eesel.ai/blog/gemini-3-8-flash; eesel.ai/blog/glm-5-3-flash; artificialanalysis.ai/models/kimi-k3;
apidog.com/blog/what-is-gemini-embedding-2.

## 9. Decisions made

| Decision | Choice |
| --- | --- |
| Scope | One app, union of both briefs; Network behind a switch; two deployments |
| Primary data source | NSE for everything (filings, results, transcripts, pledges, prices via bhavcopy); yfinance secondary; BSE PDF links as fallback |
| Pipeline runtime | GitHub Actions (scheduled), because only it reaches NSE |
| Results numbers | Parsed from XBRL, never from a model |
| Model routing (proposed) | Rules first; Groq (gpt-oss-20b) for leftover classification and one-liners; Gemini Flash for long documents and embeddings; GLM (hyde/glm-5.3-flash through Karthik's Hyde gateway access, valid until December) for promise-vs-delivery reasoning; OpenRouter as fallback; cache by filing ID |
| Secrets | Local `.env` + `gh secret set -f .env`; `config.py` reads both |
| Licence | MIT |

## 10. Open decisions (need Karthik)

1. **Backend host:** Render free (recommended; sleeps when idle, keep-warm ping) vs Cloud Run (needs a card) vs HF Spaces.
2. **Data store:** Supabase (recommended: Postgres, auth, row-level security, storage, pgvector) with static
   JSON snapshots as an offline fallback.
3. **Reviewer access:** one-tap "Try the demo" read-only account plus optional real sign-up (recommended).
4. **Budget:** zero, or ~$10 OpenRouter credit as insurance against free-tier limits.
5. **Signature interaction:** recommended: morning brief + triage cards as the frame, thesis tags woven in,
   chat scoped to "ask about this company" inside Pull, optional 60-second audio brief.
6. **Design direction:** Karthik is researching; constraint: calm, typographic, one accent colour,
   official but a little dynamic. QuantDesk (kdoesstuff.github.io/QuantDesk) is the fallback design system.
7. **Investor persona and network input:** proposed: PM at a Mumbai family office, ~15 years, ex-sell-side,
   IIT/IIM network; network seeded from a file in LinkedIn's own "download your data" Connections.csv
   format (synthetic for the demo).
8. **Portfolio:** draft below, not yet approved.
9. Whether ENAM wants separate emails per role; whether the placement cell allows sitting for both.

## 11. Portfolio draft (pending approval)

Reporting results 10-14 Nov 2026 (live during review): ABB India, Eicher Motors, HAL, Page Industries,
Natco Pharma, Manappuram Finance (NBFC template), MRF, Triveni Turbine, Kalyan Jewellers (pledge history),
Tata Power.
Already reported (deep history for Pull): TCS, HDFC Bank, Asian Paints, Elgi Equipments, Asahi India
Glass (both long-held in Nemish Shah's disclosed holdings), Persistent Systems, Navin Fluorine, Larsen & Toubro.
Research names (outside the portfolio): Polycab India, Bajaj Finance, Dixon Technologies.
Excluded despite reporting this week: IGL Spirits (alcohol), EIH (hotels), IRCTC (hospitality), Avanti
Feeds (aquaculture); ITC (tobacco, hotels).
Selection criterion Karthik should apply: he will be asked about these companies in the interview.

## 12. Next steps, in order

1. Karthik: accounts and keys into `.env`, `check_setup.py` all green, `gh secret set -f .env`; settle open decisions.
2. Fetchers as a package (`finn/nse.py`): session with cookie warm-up, retries with backoff, polite spacing,
   on-disk cache keyed by URL; integrated + legacy results merged with latest-revision selection; bhavcopy;
   pledges; insider per symbol; board meetings; transcripts; annual reports.
3. Scheduled ingest workflows (EOD after market close, filings several times a day) writing to the store,
   plus a static JSON snapshot fallback.
4. Model routing layer with caching; cheap-model reading of generic filings for portfolio names only.
5. Pull: transcript chunking and retrieval, guidance extraction, promise ledger matched to parsed results,
   downside-first dossier, citations on every number; works for any NSE symbol.
6. Network: synthetic profiles overlapping the portfolio, typed edges with link strength, entity resolution
   from filing names to people, who-to-call, second-degree reach, reconnect prompts, expertise map.
7. Backend API, frontend (mobile-first PWA), deployment ×2, keep-warm, Sentry.
8. Writeups (short for AI/ML; full design document with diagram for Founding), build-history links (this
   chat and the next), final phone check.
