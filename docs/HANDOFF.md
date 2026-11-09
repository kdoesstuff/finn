# FINN: complete briefing for the build session

Written 9 Nov 2026 (evening, IST) at the end of the foundations session. This is the single source of
truth for continuing the build. Read it in full before doing anything else.

It is given to you together with: the two challenge briefs (AI Engineer and Founding AI Engineer), the
"Announcement Categories & Financial Glossary", the two IIT Delhi job notification forms, ENAM's campus
deck "AI-led Transformation" (Aug 2026) and enam.com. Where this file and those documents disagree on
what ENAM asked for, the documents win; where they disagree on what has been built or measured, this
file and the repo win.

---

## 0. How to use this briefing (instructions to the assistant)

You are the lead engineer on this build, working with Karthik. Work in this order:

1. **Verify before you trust.** Every decision and measurement below was made in one session. Before
   planning, re-check the important ones by *testing*, not by re-reading: run the test suite, run the
   setup checker, re-run the classifier measurement, confirm the repo matches section 6, and spot-check
   the facts in sections 8 to 12 that the plan will depend on. Where something is wrong, outdated or
   could be done better, say so plainly, give the evidence, and propose the change. Do not silently
   keep a decision just because it is written here, and do not change one without telling Karthik why.
2. **Settle the open decisions** in section 14 with Karthik, using the recommendations as a starting
   point. Ask the important ones together, once, with your recommendation first.
3. **Plan.** Produce the complete task pipeline (section 16 gives the skeleton and the rules): every task
   from here to submission, in execution order, each with its definition of done and how it will be
   verified. Get Karthik's agreement on the plan before building.
4. **Build task by task.** One task at a time, each finished to its definition of done, tested, reviewed
   for security and committed before the next starts. Keep a working, deployed version from the first
   end-to-end slice onwards.

**The bar.** Karthik's instruction: no lower aim. A completely finished product with the best output
quality, production-level security and detail, verified end to end and free of bugs. Hold to that, and
protect it with one rule: every stage ends deployed and working, so ambition never puts the demo at
risk. The brief itself says "a demo that doesn't run is the worst outcome".

**Honesty rules for this build.** Never present a guess as a fact, in code, in the product or in the
writeup. Facts about the world as it is now (prices, limits, who holds a role, what an API returns) are
checked, not remembered. When you cannot verify something, label it.

---

## 1. The challenge

ENAM Holdings is a Mumbai family office (est. 1984 heritage; value investors in the Buffett-Munger mould;
about 50-100 people) building an in-house AI team. Its build challenge, released **Sun 8 Nov 2026**,
is **due Sun 15 Nov 2026** (no time given: plan to submit Sat 14 Nov night). Deliverables:

- A **mobile-first working prototype** of **FINN**, a financial investment agent (deployed link, easy to
  try on a phone)
- The **public GitHub repo**
- The **AI build history** (chat links: this build session's chat, plus any coding-agent sessions)
- A **writeup in the covering email**

FINN has three layers:
- **Push:** proactively tells the investor what changed across a 15-20 stock NSE/BSE portfolio and why it
  matters. A windowed digest (default last 24 h, configurable) with routine filings collapsed, plus
  triggered alerts (material announcements of chosen types; unusual EOD moves with configurable
  thresholds, e.g. volume > ~2x average, price beyond ±X%). Named examples: management change with a bio
  of the incoming person; quarterly results with Revenue, EBITDA, PBT, PAT QoQ and YoY.
- **Pull:** on-demand research on **any NSE ticker** (they may test one we did not pick), grounded **only in
  primary sources** (annual reports, concall transcripts; no news, broker notes or model memory). Menu:
  business snapshot, financial snapshot, trajectory, balance sheet, cash quality, narrative vs numbers,
  guidance, bull vs bear. The worked example they "value most": **promises vs delivery over the last four
  quarters**.
- **Network** (Founding brief only): an intelligence layer on the investor's own network (people met,
  colleagues, classmates, employers), woven **into** Push and Pull: who worked with the incoming CFO, who
  is best placed to explain an M&A, second-degree reach, diligence on people, expertise map, reasons to
  reconnect. Profiles may be legitimately accessed, a public dataset or realistic synthetic data, stated
  clearly in the writeup.

**Grading:** creativity, product sense, judgment and architecture, not completeness. "Thin-but-working
beats broad-but-broken." The interaction model is deliberately open: "try more than the obvious", "show a
point of view about how an investor should interact with this". "No AI slop": core, concise, beautifully
presented, interactive. **Efficiency earns bonus points**: cheap models for bulk work, strong models only
where reasoning needs them, caching, chunking. Free tiers are enough.

| | AI/ML Engineer | Founding AI Engineer |
| --- | --- | --- |
| Layers required | Push + Pull ("one or two workflows" nailed) | Push + Pull + Network, all three working, Network woven in |
| Writeup | What was built, key decisions and trade-offs, what was left out, next | Same, plus architecture: data pipelines, security and privacy, use of LLMs and agents, cloud; a diagram welcome |
| Email subject (to assessment@enam.com) | `IIT Delhi – AI Engineer - 2027` | `IIT Delhi – Founding AI Engineer - 2027` |
| CTC | 21-28 L (18 fixed) | 42-56 L (36 fixed) |
| Extra expectation | | Make architecture decisions independently; mentor and set direction |

Karthik (IIT Delhi, B.Tech Mathematics & Computing, graduating 2027; GitHub `kdoesstuff`) has applied
for **both**. **Decided:** one codebase built to the Founding spec, Network behind a switch
(`NETWORK_ENABLED`), deployed twice: `finn-core` (Push + Pull) for the AI/ML email and `finn` (full) for
the Founding email; two emails with the two subject lines (confirm with the placement cell).

Relevant background Karthik can speak to in interviews: EXL internship (May-Jul 2026) building a
text-to-SQL analytics agent (React/TypeScript, Plotly, Databricks, semantic schema retrieval with
OpenAI text-embedding-3 1536-dim embeddings in Milvus/pgvector over ~50 tables, Docker/Helm/Kubernetes);
QuantDesk (kdoesstuff.github.io/QuantDesk: Vite + React + TS, token-based design system, an insights
engine that reports only large, well-supported findings with minimum sample sizes); an options pricing
and hedging engine (Python, yfinance with offline snapshot fallback, Streamlit; a team course project).
His hands-on ML experience is light: prefer approaches he can explain.

---

## 2. The ENAM lens (what the product must feel like)

Sources: enam.com (About, Culture, Investment Philosophy, Management Team), the campus deck, a 2022 CFA
Society talk by Vallabh Bhanshali. A longer version is the "ENAM Playbook for the FINN Build" doc
(https://claude.ai/artifact/3fwnFMsb84LYDnSLLWg7Kn).

- **Philosophy:** long-term (8-10 year average hold, 25% long-term IRR goal), margin of safety, bottom-up,
  invest in management and capital allocation, contrarian, degree of upside over hit rate. They also run
  a short-term book (1-12 months) and F&O, so price and volume alerts are legitimate.
- **Culture:** integrity, humility (circle of competence), objectivity, "forever students" who admit
  mistakes. Understated; low-profile founders; relationship-oriented.
- **Ethical exclusions (hard rule):** intoxication (alcohol), gambling, tobacco, meat and poultry, hotels,
  anything that harms living creatures (read as including weapons and defence manufacturing).
- **Their AI roadmap (deck):** Wave 1 "The Brain" encodes 40 years of decisions and biases (selection,
  timing, sizing, valuation) into a screener, position monitor and decision copilot. Wave 2 "The Arms":
  News & Sentiment Dashboard, **Earnings Call Analyzer (promises vs delivery, credibility scoring)**,
  Broker Report Synthesizer, Trade Signal Dashboard (MF flows, insider trades, bulk/block deals), Excel
  Model Builder. Position FINN as a Wave 2 arm designed to plug into Wave 1. Their technology "house":
  AI vision as the roof; Investing, Research, Backoffice as pillars; Data, Cloud, Security and Talent as
  the base.
- **Agreed product principles:**
  1. Rank in ENAM's order: management and governance, then business, then price, then paperwork.
  2. Every holding carries a short thesis; items are tagged supports / challenges / neutral to it.
  3. Promise vs delivery is the centrepiece of Pull.
  4. Downside first: leverage, pledging, cash conversion, contingent liabilities, auditor remarks, RPTs.
  5. Evidence always: every number links to its filing; parsed numbers before model output.
  6. Say what you don't know; never fill gaps from model memory.
  7. Quiet by default: "Nothing material across your portfolio" is a valid output; routine shown as a count.
  8. Relationships are an asset: Network is private, consent-based, never sent to an external model.
  9. Learn and unlearn: feedback and decision notes are kept as future Wave 1 training data.
  10. Values as a filter: excluded sectors; flag a holding that moves into one.
- **Vocabulary:** thesis, management quality, capital allocation, promise vs delivery, credibility,
  margin of safety, circle of competence, governance, cash conversion. **Avoid:** alpha, sentiment
  scores, "AI-powered", hype, emoji, anything that looks like a retail trading app.

---

## 3. Working environment and conventions

- **Repo:** https://github.com/kdoesstuff/finn (public, MIT). Karthik's local clone is at
  `C:\Users\Karthik\OneDrive\Desktop\Enam-finn\finn`, possibly moved to `C:\dev\finn` (recommended, to
  keep OneDrive away from `node_modules` and `.venv`). Whichever is connected to the session through the
  Claude desktop app is current.
- **Roles:** the assistant writes code into the connected folder; Karthik reviews in VS Code, commits and
  pushes. Commit messages state a decision ("Rank filings by tier; collapse routine filings"), not an
  activity. Git identity: Kedhar Karthik Naidu Rejeti, `kdoesstuff` no-reply email (set per clone).
- **`.github/` is protected from the assistant's file tools.** Workflow files go into
  `workflows-to-install/`; Karthik runs `Move-Item -Force workflows-to-install\*.yml .github\workflows\`.
- **Network reach differs by machine (tested):**
  - The assistant's cloud workspace: package registries and GitHub only. Cannot reach NSE, BSE, Yahoo,
    screener or any LLM API.
  - The assistant's shell on Karthik's laptop (device sandbox): cannot reach NSE either.
  - **GitHub Actions runners reach NSE, Yahoo and screener**: all fetching runs there.
  - Karthik's own laptop has normal internet (`check_setup.py` runs there).
- **Getting workflow output into the repo** (PowerShell; give literal commands, `<placeholders>` break
  PowerShell because `<` is an operator):
  ```
  $id = gh run list --workflow=capture-fixtures.yml --limit 1 --json databaseId --jq '.[0].databaseId'
  gh run watch $id
  gh run download $id -n fixtures -D pipeline\tests\fixtures_new
  ```
  `gh run download` will not overwrite existing files: download into a fresh folder, then merge.
- **Settings and secrets:** one local `.env` at the repo root (git-ignored); `.env.example` documents
  every setting with no values. `pipeline/finn/config.py` reads `.env` locally and platform environment
  variables in the cloud (real environment variables win). `python pipeline/scripts/check_setup.py`
  tests every key with one small request (`--models` lists each key's models). `gh secret set -f .env`
  copies all settings to GitHub Actions secrets. **Models are configuration, not code**: code asks for a
  role, never names a model.
- **Repo security already on:** secret scanning, push protection, Dependabot alerts and security updates,
  CodeQL default setup; workflow permissions read-write; all actions at v7.
- **Line endings:** `.gitattributes` forces LF.

---

## 4. Accounts and services (all set up and working on 9 Nov 2026)

`check_setup.py`: **8 of 8 working**; 20 settings copied to GitHub secrets.

| Service | Use | Notes |
| --- | --- | --- |
| Google AI Studio (Gemini) | Document reading, embeddings, rescue tier | **Key format `AQ.`** (Google's new auth keys; the old `AIza` keys are rejected since Sep 2026). Works on the **native** endpoint with header `x-goog-api-key`; can fail on Gemini's OpenAI-compatible endpoint. Use native calls or Google's SDK only. Free tier. |
| Groq | Fast jobs, injection guard | OpenAI-compatible, `https://api.groq.com/openai/v1` |
| Hyde gateway (GLM) | Reasoning | OpenAI-compatible, `GLM_BASE_URL=https://inference.hyde.tech/v1`, model `hyde/glm-5.3-flash`; Karthik's IIT Delhi access, valid until December; key aliased `enam`; no quota shown; test calls 0.4-0.7 s |
| OpenRouter | Last-resort fallback | Key named ENAM, credit capped at $0 (free models only), expiring after the review window |
| Supabase | Postgres, auth, row-level security, storage, pgvector | Project `clwjxnbfqnxxvynjpica`, region Mumbai (ap-south-1), Free plan, Nano compute. **New key types**: `SUPABASE_PUBLISHABLE_KEY` (`sb_publishable_`, browser-safe only with RLS) and `SUPABASE_SECRET_KEY` (`sb_secret_`, server only); not JWTs, send in the `apikey` header. `vector` extension enabled. Legacy keys retire in 2027; do not use them. |
| Sentry | Error tracking and tracing | Org `kdoesstuff`, EU data storage; projects `finn-api` (FastAPI) and `finn-web` (React), both linked to the GitHub repo; Error monitoring + Tracing only. **Session replay deliberately off** (it would record the investor's private network). Scrub PII. |
| Render, Vercel | Backend and frontend hosting | Accounts created with GitHub; no services yet |
| GitHub | Repo, Actions (the data pipeline), secrets | |

---

## 5. Models and routing (final, from this project's measured limits)

Limits read from AI Studio's Rate Limit page for this project on 9 Nov 2026 (they matched published
figures except Gemma's 16K tokens/min) and Groq's rate-limit docs. **Each model has its own quota, so
pairs add capacity.**

| Role (setting) | Model | RPM / tokens per min / per day | Notes |
| --- | --- | --- | --- |
| Read documents (`GEMINI_MODEL`) | gemini-3.5-flash-lite | 15 / 250K / 500 | 1M context, native PDF |
| Overflow reader (`GEMINI_OVERFLOW_MODEL`) | gemini-3.1-flash-lite | 15 / 250K / 500 | Separate quota: 1,000 documents/day together |
| Rescue tier (`GEMINI_QUALITY_MODEL`) | gemini-3.8-flash | 5 / 250K / 20 | Stronger (ParseBench 71.2% vs 59.5%; Artificial Analysis index 59); only for failed validations |
| Second rescue (`GEMINI_QUALITY_FALLBACK_MODEL`) | gemini-3.6-flash | 5 / 250K / 20 | 40 rescues/day together |
| Short-job backup (`GEMINI_VOLUME_MODEL`) | gemma-4-31b-it | 30 / **16K** / 14,400 | Too few tokens/min for whole transcripts; backs up Groq's short jobs |
| Fast jobs (`GROQ_MODEL`, `GROQ_FALLBACK_MODEL`) | openai/gpt-oss-120b, then openai/gpt-oss-20b | each 30 / 8K / 1,000 | Same quota, so the larger is free quality |
| Injection guard (`GUARD_MODEL`) | meta-llama/llama-prompt-guard-2-86m (Groq) | 30 / 15K / 14,400 | Screens untrusted filing text before it reaches a model |
| Reasoning (`GLM_MODEL`) | hyde/glm-5.3-flash | Hyde quota unknown | Artificial Analysis index 57, 1M context, always-on thinking; on HTTP 429 fall back to the rescue tier, then OpenRouter |
| Embeddings (`GEMINI_EMBED_MODEL`, `GEMINI_EMBED_DIM`) | gemini-embedding-2 at 768 dims | 100 / 30K / 1,000 | Matryoshka truncation; 8,192 tokens per input; batch endpoint; computed once and cached |
| Fallback (`OPENROUTER_MODEL`) | nvidia/nemotron-3-ultra-550b-a55b:free | 20 / - / 50 (1,000 once $10 of credit has ever been bought) | Largest free model listed; the daily limit applies to all `:free` models together |

**Routing rule:** deterministic rules and parsing first; document reader, then the overflow reader on
quota exhaustion; on a failed validation, rescue tier then second rescue; reasoning on GLM with
fallback; every call cached by a hash of its inputs; requests paced to each model's per-minute limit;
the injection guard in front of any model that reads filing text; **network data never sent to any
external model**.

**Rejected:** hyde/kimi-k3 (about 64 s to first answer token, ~43 tokens/s, listed as deprecated by
Artificial Analysis); any `-latest` alias (moves silently).

**To verify by testing (task in the plan):** a small evaluation on one real transcript: the same
extraction prompt on the reader, the rescue tier and GLM, comparing quality and latency. Report the
result in the writeup. Most of these models post-date the foundations session's knowledge.

Sources: AI Studio Rate Limit page (9 Nov 2026); console.groq.com/docs/rate-limits;
imisofts.com/blog/gemini-api-free-tier-limits; benchlm.ai/compare/gemini-3-5-flash-lite-vs-gemini-3-8-flash;
benchlm.ai/models/gemma-4-31b; eesel.ai/blog/gemini-3-8-flash; eesel.ai/blog/glm-5-3-flash;
artificialanalysis.ai/models/kimi-k3; apidog.com/blog/what-is-gemini-embedding-2.

---

## 6. Repo state at handoff

```
.env.example                  every setting, where to get it, measured limits
.gitattributes                LF everywhere
.github/workflows/            probe-sources, probe-documents, probe-integrated, capture-fixtures (all manual)
docs/HANDOFF.md               this briefing
README.md                     setup steps
pipeline/
  finn/
    taxonomy.py               categories and tiers (1 management/governance, 2 business, 3 context, 4 routine)
    models.py                 Announcement, Classification, Bar, Signal, DigestItem
    classify.py               NSE label map + text rules; marks leftovers for a model
    rank.py                   scores, plain-language reasons, digest sections, NSE/BSE dedupe, summary line
    alerts.py                 volume multiple and sigma-scaled moves with minimum history
    results.py                Quarter / BankQuarter, EBITDA definition, QoQ/YoY rows, bank template
    xbrl.py                   results XBRL parser (legacy and Integrated Filing formats)
    config.py                 settings from .env or platform secrets; model roles
  scripts/
    probe_sources.py, probe_documents.py, probe_integrated.py   source discovery (evidence for the writeup)
    capture_fixtures.py       saves real NSE samples (`python capture_fixtures.py integrated extras` runs some steps)
    measure_classifier.py     classifier coverage on a real week of filings
    check_setup.py            tests every key; `--models` lists available models
  tests/
    test_core.py, test_xbrl.py   46 tests, all passing
    fixtures/                    real NSE data (section 9)
  requirements.txt (requests, python-dotenv, yfinance, pytest), pyproject.toml
```

Not yet built: fetchers as a package, scheduled ingest, database schema, model layer, Pull, Network,
API, frontend, deployment, writeups.

---

## 7. What is built and measured

- **Classifier** (`classify.py`). Evidence order: a very specific text rule (priority >= 85: routine
  overrides, auditor exits, results ads), then NSE's exact `desc` label (80 labels mapped), then
  the best remaining rule (content beats label), then a model. Management changes extract role
  (CEO/CFO/MD/chair/COO/secretarial/director/auditor) and action. Adds a `governance` category (RPTs,
  fraud, forensic audit, delayed results) to the glossary's categories.
  **Measured on 4,795 real filings (4-9 Nov 2026; 37 rules):** text rule 55.1%, exact NSE label 23.9%, fuzzy label
  11.4%, **model needed 9.5%** (General Updates 214, Updates 131, Outcome of Board Meeting 107).
  Spot-checks found four misreadings (inter-se promoter transfers and SAST Reg 29 disclosures read as M&A,
  a new facility read as M&A, an NCLT-sanctioned merger read as litigation); all fixed and kept as
  regression tests. Re-run: `python pipeline/scripts/measure_classifier.py`.
- **Ranker** (`rank.py`). Tier base scores with modifiers, each item carrying its reasons. Auditor exit,
  payment default, insolvency, forensic audit, fraud = 100; key-role exit 95; pledge 92; open offer 90;
  results 85. Price/volume signals within 3 days after a material filing add 15 and attach; unexplained
  moves get their own section. NSE/BSE duplicates merged. Sections: attention >= 75, worth 40-74, routine
  < 40 (collapsed into counts). Summary line, e.g. "Nothing material across your portfolio."
- **Alerts** (`alerts.py`). Volume vs 20-day average (needs 15 days); move as % and as sigma vs 60-day
  realised volatility (needs 40 returns); rule "pct", "sigma" or "either". **Tested only on synthetic
  bars so far.**
- **Results** (`xbrl.py`, `results.py`). Revenue, EBITDA, PBT, PAT in ₹ crore, QoQ and YoY, margin change
  in bps. EBITDA = PBT before exceptional items + finance costs + D&A − other income (stated on the
  card). Sign flips described in words ("turned positive", "loss narrowed"). Bank template: net interest
  income, operating profit, provisions, PAT. **Verified against reported figures:** TCS Q3 FY25 revenue
  ₹63,973 cr, PAT ₹12,380 cr; Asian Paints Q3 FY25 revenue ₹8,549 cr, PAT ₹1,110 cr; HDFC Bank Q3 FY25 NII
  ₹38,126 cr; TCS Q2 FY27 (Jul-Sep 2026) consolidated revenue ₹73,188 cr, PAT ₹13,884 cr. All 39 fixture
  filings (15 legacy, 24 Integrated Filing) parse, and every parsed period is 80-95 days long (the
  year-to-date guard). Re-verified on 9 Nov by re-running the parser over the fixtures.
  **Gap:** there are two templates, general and bank. NBFCs (Manappuram, Bajaj Finance) file in the
  general Ind AS format, where "revenue" is interest income and EBITDA is meaningless because finance
  costs are their cost of goods; a **lender template** (interest income, finance costs, net interest
  income, impairment, PAT) is needed. Confirm the format from Manappuram's XBRL when it files on 12 Nov.
- **Tests:** 46 passing (`cd pipeline; python -m pytest -q`). The 9 Nov verification found the
  upgraded `test_xbrl.py` (Integrated Filing cases) had not reached the laptop; it was delivered
  then. The committed suite must show 46, not 44.
- **`check_setup.py` gap:** it confirms the embedding model is offered but never makes an embedding
  call, so `GEMINI_EMBED_DIM` is untested; add one `embedContent` call at the configured dimension.

---

## 8. Data sources (probed from GitHub Actions, 9 Nov 2026)

NSE needs a session: GET `https://www.nseindia.com` first (sets cookies), then call
`https://www.nseindia.com/api/...` with a browser User-Agent and a Referer; space requests ~0.7 s apart.

| Need | Source | Works | Notes |
| --- | --- | --- | --- |
| Filings | `api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` (+`&symbol=X`) | Yes | ~1,000/day in results season; 400 days per symbol. Fields: `symbol`, `sm_name`, `desc` (fixed label), `attchmntText` (one-liner), `attchmntFile` (PDF), `an_dt`, `seq_id`, `smIndustry`, `sm_isin` |
| Filing PDFs | `attchmntFile` on nsearchives.nseindia.com | Yes | |
| Results, pre-2025 | `api/corporates-financial-results?index=equities&symbol=X&period=Quarterly` | Yes | **Ends Dec 2024**; has `bank`, `consolidated`, `toDate`, `xbrl` |
| **Results, 2025 onward** | `api/integrated-filing-results?index=equities&symbol=X&page=N` | Yes | Paginated (`data`, `size`, `page`, `totalCount`); mixes `Integrated Filing- Financials` and `- Governance`; fields `consolidated`, `audited`, `qe_Date`, `type_Sub` (Original/Revision), `revised_Date`, `xbrl`, `ixbrl` |
| EOD prices (all stocks) | `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` | Yes | UDiFF columns: `TckrSymb`, `SctySrs`, `ClsPric`, `PrvsClsgPric`, `TtlTradgVol`, `TtlTrfVal`; no delivery column |
| Price history | yfinance `SYMBOL.NS` | Yes | 5 years in one call; secondary |
| Pledges | `api/corporate-pledgedata?index=equities` | Yes | `percPromoterHolding`, `percPromoterShares` (pledged share of promoter holding), `percSharesPledged`, `shp` |
| Insider trades | `api/corporates-pit?index=equities&symbol=X` | Per symbol only | Market-wide query returns no rows |
| Annual reports | `api/annual-reports?index=equities&symbol=X` | Yes | PDF links up to FY2025-26; `api/annual-reports-xbrl` has structured data |
| Transcripts | Filings with `desc` "Analysts/Institutional Investor Meet/Con. Call Updates" and "Transcript" in the text | Yes | Quarterly pattern: "Schedule of meet", "Link of Recording", "Transcript" |
| Results dates | `api/corporate-board-meetings?index=equities&from_date=..&to_date=..` | Yes | `bm_symbol`, `bm_date`, `bm_desc` |
| Also available, not yet parsed | `event-calendar`, `results-comparision` (NSE's own QoQ table: a cross-check), `corporate-share-holdings-master`, `corporates-corporateActions`, `corporate-credit-rating`, `related-party-transactions-master` | Yes | Samples in fixtures. 187 NSE API paths were found in NSE's pages in total. |
| screener.in | `screener.in/company/X/consolidated/` | Yes | Document links to company sites (may return 403) and `bseindia.com/stockinfo/AnnPdfOpen.aspx` (works) |
| BSE API | `api.bseindia.com/...` | **No (403)** | Blocked even with a browser session. BSE PDF links still download. The brief accepts NSE or BSE, and the research requirement is "any NSE ticker", so NSE alone is complete for this build. |

---

## 9. Fixtures (real NSE data in `pipeline/tests/fixtures/`)

`nse_announcements.json` (4,795 filings, 4-9 Nov 2026 with the 9th partial, with `desc_counts`); `results_{TCS,HDFCBANK,ASIANPAINT}.json`;
`xbrl/` (15 legacy quarterly files, Dec 2023-Dec 2024); `xbrl_if/` (24 Integrated Filing files, Dec 2025-Sep
2026, standalone and consolidated, with revisions); `integrated_*.json`; `bhavcopy.csv` (6 Nov 2026);
`pledges.json`; `insider.json`; `annual_reports_TCS.json`; `tcs_call_filings.json`; `transcript_TCS.pdf`;
`board_meetings.json` (3,414 meetings); `event_calendar.json`; `results_comparison_TCS.json`;
`shareholding_TCS.json`; `corp_actions_TCS.json`; `credit_rating_TCS.json`; `rpt_TCS.json`;
`insider_attempts.json` (the three insider-feed queries tried: only per-symbol returns rows);
`capture_log.txt` (what the last capture run saved). Two probe outputs, `pipeline/scripts/probe_documents.json`
and `probe_integrated.json`, sit on Karthik's laptop git-ignored; they hold the raw evidence for
section 8 (BSE 403 body, 187 API paths, the Integrated Filing endpoint search).

---

## 10. Traps found in real data

1. **XBRL year-to-date trap.** Results files hold the quarter (`OneD`) and the year to date (`FourD`), and
   filers stamp both contexts with the quarter's dates. The true period is in each context's
   `DateOfStartOfReportingPeriod` / `DateOfEndOfReportingPeriod` facts. `xbrl.py` uses those and picks the
   ~3-month context; a test guards it.
2. **Results moved to Integrated Filings in 2025**; the old index stops at Dec 2024.
3. **Revisions exist** (Asian Paints revised Mar 2026 twice): use the latest revision per quarter and basis.
4. **Values are whole rupees**; show ₹ crore (÷10^7).
5. **Banks file a different format** ("Banking Format"): InterestEarned, InterestExpended,
   OperatingExpenses, ProvisionsOtherThanTaxAndContingencies, ProfitLossFromOrdinaryActivitiesBeforeTax;
   consolidated bank PAT is `ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates`;
   consolidated NPA fields are zero (NPAs are in standalone filings).
6. **Consolidated PAT** is the figure attributable to owners (`ProfitOrLossAttributableToOwnersOfParent`).
7. **`hasXbrl` is "True" on every announcement**: no signal.
8. `attchmntText` is often just "X has informed the Exchange about <label>"; generic labels ("General
   Updates", "Updates", ~70 "Outcome of Board Meeting held on <date>") need the PDF read (cheap-model job,
   portfolio names only).
9. **Not M&A despite the words:** inter-se promoter transfers, SAST Reg 29 disclosures. **M&A, not
   litigation:** an NCLT-sanctioned merger.
10. **Gemini `AQ.` keys:** native endpoint only (section 4).

---

## 11. Portfolio (draft, pending Karthik's approval)

**Reporting results 10-14 Nov 2026** (dates re-verified on 9 Nov from `board_meetings.json`): Kalyan
Jewellers (Tue 10), MRF (Tue 10), Tata Power (Wed 11), Triveni Turbine (Wed 11), Manappuram Finance (Thu
12, NBFC: needs the lender template, see section 7), Page Industries (Thu 12), NMDC (Thu 12), ABB India
(Fri 13), Eicher Motors (Fri 13), Natco Pharma (Fri 13).
**Already reported (deep history for Pull):** TCS, HDFC Bank, Asian Paints (Sep 2026 results in fixtures),
Elgi Equipments (results filed 6 Nov, in the announcements fixture), Asahi India Glass (results board
meeting 3 Nov, before the fixture window), Persistent Systems, Navin Fluorine, Larsen & Toubro (these
three have no results meeting in the fixture; confirm from NSE before relying on them).
**Research names (outside the portfolio):** Polycab India, Bajaj Finance, Dixon Technologies.

- **HAL was removed:** it builds military aircraft (ENAM's rule against harming living creatures); the
  same rule excludes BDL and other defence manufacturers. Also excluded though reporting this week: IGL
  Spirits (alcohol), EIH (hotels), IRCTC (hospitality), Avanti Feeds (aquaculture); ITC (tobacco, hotels).
- **Verified demo events (re-checked in the fixtures on 9 Nov):** Kalyan Jewellers: 24.85% of promoter
  holding pledged, 16.68% of all shares (30 Sep 2026) for the pledging alert; **Asian Paints: 10.35% of
  promoter holding pledged, 6.25% of all shares**, a second, quieter pledge story in a blue chip (the
  earlier note that others were "near zero" was wrong); Asahi India Glass 3.38%, Elgi 0.87%, Manappuram
  0.44%, MRF 0.09%, the rest 0.00% of promoter holding. Manappuram: two resignation filings on 7 Nov
  2026, one naming the Group Chief Technology Officer, so it ranks as a change below the top team (65),
  not a key-role exit; HDFC Bank: "Change in Management" 6 Nov; Asian Paints: appointment of Leo Puri as
  independent director, filed 6 Nov (effective 7 Sep 2026); L&T: "Bagging/Receiving of orders" 9 Nov.
- **Not yet verified (general knowledge):** that Polycab, Bajaj Finance and Dixon give explicit numeric
  guidance; Manappuram's recent ownership change; MRF's sparse disclosure; Nemish Shah's holdings in Elgi
  and Asahi (third-party portfolio trackers). Confirm from transcripts and filings before relying on them.
- **Timing matters:** the ten names report 10-13 Nov. Ingestion must be live by then to capture their
  results as they happen; otherwise backfill from NSE after the fact.
- Criterion for Karthik: he will be asked about these companies in the interview.

---

## 12. Decisions made (verify, then keep or change with reasons)

| Area | Decision | Evidence |
| --- | --- | --- |
| Scope | One app to the Founding spec; Network behind a switch; two deployments, two emails | Founding brief is a superset |
| Deployment shape (decided 9 Nov) | **One** FastAPI backend on Render serving Push, Pull and Network through authenticated endpoints; **two** Vercel frontends (`finn-core`, `finn`) from one codebase with the Network switch, which the API also enforces per deployment and per user; all scheduled fetching in GitHub Actions; keep-warm ping during the review window. Supabase is reached only from the server with the secret key; RLS stays on as defence in depth, never as the only control. | Render's free workspace has 750 instance-hours/month, so two always-warm backends (~1,440 h) cannot fit; one (720 h) can. Karthik chose the full production route over a static-hosting shortcut. |
| Results templates | General, bank, and a **lender** template (NBFCs: interest income, finance costs, net interest income, impairment, PAT) | Two portfolio names are lenders; EBITDA is meaningless for them |
| Data source | NSE for everything; yfinance secondary; BSE PDF links as fallback | Probes (section 8) |
| Where fetching runs | GitHub Actions, scheduled | Only place that reaches NSE |
| Results numbers | Parsed from XBRL, never generated | Verified figures (section 7) |
| Classification | NSE label + rules first; model for the ~10% left | Measured on 4,795 filings |
| Ranking | Management/governance, business, price, routine | ENAM philosophy |
| Price alerts | % threshold (brief) plus sigma view (default "either") | A 4% day differs for a quiet large cap and a volatile small cap |
| Model routing | Section 5 | Project's measured limits |
| Database | Supabase, Mumbai, new key types, RLS on every table, pgvector at 768 dims | Free tier, auth and privacy built in |
| Observability | Sentry (EU), errors and tracing, no session replay | Privacy |
| Secrets | `.env` locally, platform secrets in the cloud, nothing hard-coded | |
| Repo | Public, MIT, scanning on | Brief requires a public repo |

---

## 13. Engineering standards (apply to every task)

- **Correctness:** unit tests for logic, fixture-based tests against real NSE data for parsers, an
  end-to-end test of each user journey; tests and lint run in CI on every push; no task is done with a
  failing or skipped test.
- **Security:** secrets only in `.env`/platform secrets; RLS on every Supabase table with policies tested
  as each role; the secret key only on the server; input validation on every API parameter (ticker
  pattern, date ranges, sizes); rate limits on the API; CORS allow-list; content security policy on the
  frontend; no `innerHTML`; dependency audit in CI; **prompt-injection defence**: filing text is
  untrusted, screened by the guard model, passed as data with clear delimiters, outputs validated
  against a schema; **privacy**: network data private per user, minimal fields, encrypted at rest,
  never sent to an external model, deletable on request, retention stated; Sentry scrubbing on.
- **Reliability:** retries with backoff and jitter on every external call; timeouts everywhere; graceful
  degradation (last good snapshot, clear "data as of" labels); idempotent ingest keyed by filing ID;
  caching by input hash; keep-warm for the sleeping backend during the review window.
- **Evidence:** every number shown links to its source document; model outputs carry the quotes they
  rest on; confidence and coverage shown ("3 of 4 transcripts found").
- **Performance:** the digest loads from stored data, never from a live model call; Pull streams progress
  and caches per company.
- **Mobile-first and accessible:** works from 360 px wide; touch targets; readable type; keyboard and
  screen-reader basics; light and dark.
- **Writeup evidence log:** keep `docs/DECISIONS.md` as you go (decision, alternatives, evidence) and
  record measurements (coverage, latency, cost per call, cache hit rate, model evaluation results) so the
  writeups are written from facts.

---

## 14. Open decisions (settle with Karthik first; recommendations given)

1. **Backend host: decided (section 12).** One Render free web service, Singapore region. Facts to design
   around: spins down after 15 minutes idle, wakes in about a minute, 750 instance-hours per workspace
   per month, 100-minute request timeout (ample for Pull). Rejected: Hugging Face Spaces (Docker Spaces
   now need a paid plan), Fly.io (no free tier for new users), GitHub Pages for the whole app (static
   only: cannot hold secrets or reach NSE; Karthik chose the full backend route), two Render services
   (exceeds 750 h). Google Cloud Run remains the paid-card fallback if Render misbehaves.
2. **Data flow:** Supabase as the store (recommended) with static JSON snapshots committed as an offline
   fallback so the demo works even if Supabase or NSE fail. The API is the only reader and writer; the
   frontend never holds a Supabase key.
3. **Reviewer access:** a one-tap "Try the demo" read-only investor (recommended) plus optional real
   sign-up (email magic link), so auth and per-user privacy are real but reviewers face no friction.
4. **Budget:** zero (current), or ~$10 OpenRouter credit (raises free-model limits from 50 to 1,000
   requests/day) as insurance during the review.
5. **Signature interaction (most important product decision):** recommended frame: a calm morning brief
   plus triage cards (what happened, why it matters to *this* investor, who to call), with thesis tags
   woven in, chat scoped to "ask about this company" inside Pull, and an optional 60-second audio brief.
   Explore alternatives before deciding; this is where ENAM looks hardest.
6. **Visual direction:** Karthik is researching references. Constraints: calm, typographic, one accent
   colour, official but a little dynamic; not a trading app. QuantDesk's token structure is the fallback.
7. **Investor persona and network input:** proposed: a portfolio manager at a Mumbai family office, ~15
   years' experience, ex-sell-side, IIT/IIM network. Network seeded from a file in LinkedIn's own "download
   your data" Connections.csv format (a real, consented way for a user to bring their network), synthetic
   for the demo, overlapping the portfolio and research names (ex-employees, auditors, suppliers,
   classmates of incoming executives).
8. **Portfolio approval** (section 11).
9. **Submission logistics:** two emails or one; whether the placement cell allows sitting for both.

---

## 15. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| NSE starts refusing GitHub's runners | Retries; cached last-good data; committed snapshots; a laptop fallback script |
| Free-tier quota exhausted during review | Paired models; caching; precomputed results for demo names; graceful messages |
| Backend asleep when a reviewer opens it | Keep-warm ping every 10 minutes from Actions during the review window (one service, so 720 h/month fits the 750 h allowance); the frontend shows a "waking up" state rather than an error; static fallback for the digest |
| Pull on an unknown ticker is slow | Stream progress; cache; precompute the research names |
| Model invents a number | Numbers only from parsing; schema validation; citations required; quote-check against source text |
| Prompt injection via filings | Guard model, delimiters, schema-validated outputs, no tool access from document-reading calls |
| Network privacy questioned | Synthetic data, consent model, RLS, never sent to models; documented in the writeup |
| Scope outruns time | Deployed, working slice at every stage; features added only on top of a green build |

---

## 16. Planning instructions: build the task pipeline

Produce the **complete, ordered task list** from now to submission. For every task give: the goal, inputs,
outputs, dependencies, the **definition of done**, and **how it will be verified** (tests, security
check, end-to-end check). Group tasks into phases ending in **gates**: a gate passes only when the
deployed build works end to end, all tests pass, and a security review of that phase is done.

Constraints for the order:
- Ingestion must be live **before 10-13 Nov** results, so the portfolio's real results flow through.
- An **end-to-end vertical slice** (one real filing from NSE to a card on a phone) should exist early;
  everything after builds on a deployed, working app.
- Product and interaction design (section 14, item 5) must be decided early enough to shape the API,
  not after it.
- Push + Pull reach a finished state before Network is added; Network is woven into existing screens,
  not added as a separate tab only.
- Final day: freeze, full end-to-end check on a real phone, writeups, submission.

A starting skeleton to refine (not a fixed plan):

- **Phase A, verification and decisions:** re-verify (section 0, step 1); settle open decisions; model
  evaluation on a real transcript; design direction and interaction model; portfolio approved.
- **Phase B, data foundation:** fetchers package (session, retries, cache, all sources in section 8,
  latest-revision results selection); database schema with RLS and migrations in the repo; scheduled
  ingest workflows (filings several times a day, EOD after close, board meetings daily); snapshot
  fallback; CI (tests, lint, type checks, dependency audit, secret scan).
- **Phase C, model layer:** routing with fallbacks, pacing, caching, guard model, schema-validated
  outputs, cost/latency logging; generic-filing reader for portfolio names; one-line summaries.
- **Phase D, Push:** digest API and alert rules (configurable thresholds and categories), results card,
  management-change card, pledge and governance cards, unexplained moves, "why am I seeing this?".
- **Phase E, Pull:** company resolution for any NSE ticker; document fetch; chunking and embeddings;
  financial snapshot and trajectory from XBRL; balance sheet and cash quality; guidance extraction from
  transcripts; promise ledger matched to delivered numbers; downside-first dossier; bull and bear;
  citations everywhere.
- **Phase F, frontend:** the chosen interaction model, mobile-first PWA, design system, all screens wired
  to the API, error and empty states, accessibility.
- **Phase G, Network:** synthetic profiles and connections file; graph with typed, weighted edges; entity
  resolution from filing names to people; who-to-call, second-degree reach, diligence, expertise map,
  reconnect prompts; woven into Push and Pull cards; privacy model.
- **Phase H, deployment and hardening:** one API on Render, two frontends on Vercel (core and full), the
  Network switch enforced at both layers, keep-warm, Sentry, security review, load and failure tests,
  phone testing.
- **Phase I, submission:** architecture diagram, README, short writeup (AI/ML) and full design writeup
  (Founding), build-history links, final check, emails.

Then execute task by task with Karthik, verifying each before moving on.
