# FINN

A mobile-first investment agent: it tells an investor what changed across their portfolio and why it matters (Push), researches any NSE company from its own filings and transcripts (Pull), and points to the person in the investor's own network best placed to explain it (Network).

Work in progress. Build notes so far: [docs/HANDOFF.md](docs/HANDOFF.md).

## Setup
```
cp .env.example .env                       # then fill in the keys (never committed)
cd pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows; on macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/check_setup.py              # tests every key with one small request
python -m pytest -q                        # 46 tests against real NSE fixtures
```
Copy the keys to GitHub Actions secrets in one step: `gh secret set -f .env`.
