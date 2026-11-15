# FINN

A mobile-first investment agent: it tells an investor what changed across their portfolio and why it matters (Push), researches any NSE company from its own filings and transcripts (Pull), and points to the person in the investor's own network best placed to explain it (Network).

**Try it on a phone** (no sign-up; one tap opens a read-only demo investor with a fictional
portfolio of 18 real NSE companies):

- Full edition, with Network: https://finn-lac.vercel.app
- Core edition, Push and Pull: https://finn-hkmn.vercel.app

What to try: open the brief, the front page of your portfolio (how many filings FINN read and
where they went, every holding at a glance, results with their numbers, price moves, pledges, a
checked one-line note and a bio for management changes, each item with why it was chosen and a link
to the filing); tap a holding to narrow the page to it, pick **Since…** for any window in the last
31 days, set **Your alerts**, or press **Read in 30 seconds**; then **Research** and pick a covered company such as TCS
(the promise ledger first: what management guided on its last four calls against what was
delivered, every claim with its quote), and on the full edition **Your network** ("Who worked at
Tata Power?"). The network is synthetic and labelled so.

Data refresh: GitHub's scheduler has not started this repository's scheduled runs, so filings and
prices are refreshed by hand for now (`gh workflow run ingest.yml -f job=filings`; see
`docs/DECISIONS.md`, "The final sprint").

The API is at https://finn-api-53vw.onrender.com/health. How it fits together:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The plan is [docs/PLAN.md](docs/PLAN.md); decisions
and the evidence behind them are in [docs/DECISIONS.md](docs/DECISIONS.md); every brief requirement
is mapped to a task in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Setup
```
cp .env.example .env                       # then fill in the keys (never committed)
cd pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows; on macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/check_setup.py              # tests every key with one small request (10 checks)
python scripts/migrate.py status           # database migrations: status | apply | verify
python -m pytest -q                        # tests against real NSE fixtures; database tests need
                                           # FINN_TEST_DB_URL (a disposable Postgres), as CI sets
ruff check . ; mypy                        # lint and type check, as CI runs them
python scripts/measure_classifier.py       # classifier coverage on a real week of filings
```
Copy the keys to GitHub Actions secrets in one step: `gh secret set -f .env`.

The API and the web app:
```
python -m pytest api -q                    # from the repository root; FINN_TEST_DB_URL as above
cd web; npm ci; npm run typecheck; npm run lint; npm test; npm run e2e
```

| Part | Where it runs | Code |
| --- | --- | --- |
| Ingest (NSE to the database) | GitHub Actions, on a schedule | `pipeline/`, `.github/workflows/ingest.yml` |
| Database | Supabase (Postgres, Mumbai), reachable only by the two roles | `db/migrations/` |
| API | Render, free tier, Singapore | `api/`, `render.yaml` |
| Web app, two editions | Vercel: `finn-core` (Push and Pull), `finn` (with Network) | `web/` |
