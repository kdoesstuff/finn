# Requirements checklist

Every requirement in ENAM's two briefs (AI Engineer and Founding AI Engineer, released 8 Nov 2026),
the reference glossary and the campus deck, mapped to the task in `docs/PLAN.md` that delivers it.
"Both" means both briefs say it; "Founding" means only the Founding brief does. Status is updated
as tasks pass their gates.

## Deliverables

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| Mobile-first working prototype, easy to try on a phone (deployed link) | Both | B6, D7, E8, H3 | |
| Public GitHub repository | Both (Founding says "public") | Done: `kdoesstuff/finn`, public, MIT | Done |
| AI build history: coding-agent and LLM sessions, showing how problems were broken down, prompted, course-corrected, and what was accepted vs rewritten | Both (detail from Founding) | I4; course-corrections logged in `DECISIONS.md` as they happen | Ongoing |
| Short writeup in the covering email: what was built, key decisions and trade-offs, what was left out, where next | Both | I3 | |
| Writeup adds architecture: data pipelines, security and privacy, LLMs and agents, cloud; a simple diagram welcome | Founding | I1, I3 | |
| Email to assessment@enam.com, subject "IIT Delhi – AI Engineer - 2027" | AI Engineer | I6 (`finn-core`) | |
| Email to assessment@enam.com, subject "IIT Delhi – Founding AI Engineer - 2027" | Founding | I6 (`finn`) | |

## Companies and network

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| Mock portfolio of 15-20 NSE/BSE companies, mixed sectors and sizes | Both | Decision 7: 18 names | Done |
| 3-5 ad-hoc research companies, may be outside the portfolio | Both | Decision 7: Polycab, Bajaj Finance, Dixon | Done |
| Research generalises to any NSE ticker where data exists; not hard-wired to the demo set | Both | E1, E2, E7 (tested on three unseen tickers) | |
| Investor's network: decide what the investor gives FINN; build a mock network that overlaps the portfolio and research names | Founding | Decision 6; G1 | |

## Data sources

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| EOD price and volume for the portfolio (yfinance or equivalent) | Both | B1 (NSE bhavcopy, yfinance secondary), B3, B4 | |
| Corporate announcements from NSE/BSE; the glossary's categories are optional guidance | Both | B1, B3; classifier uses the glossary's categories plus `governance` | Classifier done |
| Fundamentals: annual reports and concall transcripts (screener.in or IR site) | Both | E2 (NSE filings first, BSE PDF links and screener as fallback) | |
| Network profiles: legitimately accessed, a public dataset or realistic synthetic; say which, and how it would be done for real | Founding | G1, I3 | |
| "Get them working; don't over-engineer them": the data layer is plumbing | Both | B1 kept to the sources the product uses | |

## Push

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| Windowed digest, default last 24 hours, investor picks the period | Both | D6, D7 | |
| Every filing across the portfolio, filtered and prioritised; routine collapsed or hidden | Both | `rank.py` (A3), D6, D7 | Ranking done |
| Triggered alerts on material announcements of types the investor chooses | Both | D6 (alert categories per investor), D7 | |
| Triggered alerts on unusual EOD moves: volume > ~2x average, price beyond ±X%; thresholds configurable | Both | `alerts.py` (A3), D4, D6 | Rules done |
| "Tell me the moment": alerts reach the investor | Both | D6 alerts feed with unread badge; web push is a stretch item | |
| Management change: short bio of the incoming person (e.g. from LinkedIn) | Both | D2 (filing's own profile first; outside sources labelled) | |
| ...and whether anyone in the network worked or studied with them, or sits one connection away | Founding | G4, G5 | |
| Quarterly results: Revenue, EBITDA, PBT, PAT, QoQ and YoY, from the actual filing | Both | `xbrl.py`, `results.py`; D1 adds the lender template | Parser done |
| Material event at a company the investor knows people at (M&A, capex, litigation): the person best placed to give context, and why | Founding | G4, G5 | |
| Every other type: decide between a one-line summary and the filing at the right priority | Both | `rank.py` reasons; C3 one-line summaries | Ranking done |

## Pull

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| On-demand analysis grounded in annual reports and transcripts | Both | E2-E7 | |
| Primary sources only: no broker notes, news, research reports or the model's outside knowledge | Both | E3, E5, E6 (retrieval-only prompts, quote checks), C2 | |
| Business snapshot: what it does, segments, revenue mix | Both | E6 | |
| Financial snapshot: headline numbers, margins, PAT, key ratios | Both | E4 | |
| Trajectory: multi-year direction | Both | E4 (five years plus eight quarters) | |
| Balance sheet: debt, leverage, working-capital cycle, funding | Both | E4 | |
| Cash quality: cash-flow trend and conversion | Both | E4 | |
| Narrative vs numbers | Both | E6 | |
| Guidance: what management explicitly guided | Both | E5, E6 | |
| Bull vs bear | Both | E6 | |
| Worked example they value most: promised vs delivered over the last four quarters | Both | E5 (the centrepiece); deck's "Earnings Call Analyzer" | |

## Network

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| Surfaces inside Push and Pull at the moments it matters, and can be queried directly | Founding | G5 (woven in), G4 (ask-your-network screen) | |
| Who should I call (worked there, at a competitor, supplier or customer, and what they would know) | Founding | G4 | |
| Second-degree reach and link strength | Founding | G2 (weighted edges), G4 | |
| Diligence on people: career path, overlaps, what to ask | Founding | G4 | |
| Expertise map by theme | Founding | G4 | |
| Keeping the network warm: reasons to reconnect | Founding | G4 | |
| "A quiet advantage, not a contact list. Show what it notices that the investor wouldn't" | Founding | D7 and G5 design | |

## Interaction, quality, cost

| Requirement | Source | Task | Status |
| --- | --- | --- | --- |
| Experiment with the interaction model; show a point of view | Both | Decision 4; D7, E8 | Decided |
| No AI slop: core, concise, beautifully presented, interactive; density and design count | Both | B6 design tokens, D7, E8, H3 | |
| Mobile-first | Both | B6, H3 | |
| Free tiers; efficiency earns bonus points: cheap models for bulk, strong where reasoning needs it, caching, chunking | Both | Decision 3 (zero spend); C1 router, cache and call log; C4 evaluation; H4 measurements | Rules-first done |
| Thin-but-working beats broad-but-broken; a demo that doesn't run is the worst outcome | Both | Gates after every phase; snapshot fallback (B6); keep-warm (B7); H2 failure drills | |
| All three layers have at least one working workflow; Network woven into Push or Pull | Founding | G5 | |

## Founding writeup: architecture topics

| Topic the brief names | Where it is answered | Task |
| --- | --- | --- |
| Data pipelines: fetch, refresh, store, link (e.g. a filing name to a person) | `docs/ARCHITECTURE.md` | B1-B4, G3, I1 |
| Network private to the investor; what personal data is stored and for how long; consent and access control | `docs/ARCHITECTURE.md` | G2, I1 |
| Which steps use a model, which model and why; where agents plan, call tools or act | `docs/ARCHITECTURE.md`, `DECISIONS.md` | C1-C4, I1 |
| Cloud services: what runs where and why | `docs/ARCHITECTURE.md` | B5-B7, I1 |

## From the campus deck (context, not requirements)

ENAM's Wave 2 "Earnings Call Analyzer" (promises vs delivery, credibility scoring) is what E5 builds;
Wave 1's "Position Monitor" (flags thesis weakening or management-quality shifts) is what D5's thesis
tags begin; the "Learning Loop" (every decision fed back) is what decision notes in D6 begin. Their
values exclusion (meat and poultry, alcohol, tobacco, hotels) is applied in decision 7 and D5.
