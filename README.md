# FINN

A mobile-first investment agent: it tells an investor what changed across their portfolio and why it matters (Push), researches any NSE company from its own filings and transcripts (Pull), and points to the person in the investor's own network best placed to explain it (Network).

Work in progress. The plan is [docs/PLAN.md](docs/PLAN.md); decisions and the evidence behind them are in
[docs/DECISIONS.md](docs/DECISIONS.md); every brief requirement is mapped to a task in
[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Setup
```
cp .env.example .env                       # then fill in the keys (never committed)
cd pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows; on macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/check_setup.py              # tests every key with one small request (9 checks)
python -m pytest -q                        # tests against real NSE fixtures
ruff check . ; mypy                        # lint and type check, as CI runs them
python scripts/measure_classifier.py       # classifier coverage on a real week of filings
```
Copy the keys to GitHub Actions secrets in one step: `gh secret set -f .env`.
