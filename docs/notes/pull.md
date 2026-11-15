# Pull (phase E), 15 Nov 2026 sprint

## What is built

- **Company page for any NSE company** (`GET /v1/company/{symbol}`, `pipeline/finn/pull.py`): name,
  industry, the last close and its moves (1 day, 1 month, since 25 Jun), filings of the last 90 days
  ranked by the brief's own ranker, and for covered companies up to nine quarters of results from
  their XBRL (standard or bank template, the brief's results card for the latest quarter), the
  documents read and the analyses. `coverage.missing` says in words what a page lacks. Search by
  symbol or name: `GET /v1/companies?q=`.
- **Documents** (`finn/documents.py`): the last four earnings-call transcripts (found among the
  company's own filings by its words "... about Transcript", assigned to the quarter that ended
  before the call, the latest re-filing kept) and the latest annual report's management discussion
  (up to 30 pages from where it starts). Read locally with pypdf 7.1.0, NFKC-normalised. Scans,
  damaged files and missing links are gaps in plain words, never guesses.
- **Promise ledger, snapshot, bull and bear** (`finn/ledger.py`, `ingest.py analyse`): forward-looking
  statements per call (model role "reader"); statements from the latest call are "too early" with no
  model call; older ones judged by the "reasoner" against FINN's own XBRL numbers and the later calls.
  A claim survives only if its quote is found in the cited document (page corrected if the model
  cited the wrong one), and a "delivered" number only if it appears in the numbers FINN gave the
  model, for a quarter after the promise. A verdict with no verifiable evidence becomes "not
  measurable". Snapshot and cases from the two latest calls and the annual report, every point
  quote-checked. Stored in `finn.analyses` (migration 0003, ingest writes, API reads).
- **Web**: Brief | Research navigation; search; the company page with the ledger first, then results
  (latest card and a scrollable nine-quarter table), snapshot, bull and bear, filings, documents.
  An analysis the app cannot read is dropped with a warning; the rest of the page stands. Every link
  to a source goes through the same NSE-archive check as the brief.

## Not built tonight, and how it would be

- **Embeddings and the ask box** (E3, E8's question box): the schema has `finn.chunks` with a
  768-dim pgvector index; chunks would be page-anchored and embedded once per document hash.
- **On-demand deep analysis for an uncovered company** (E7's cold path, streamed progress): today an
  uncovered company gets prices and filings and says so; a coverage request would add it to
  `finn.coverage` (`requested`) for the next `analyse` run.
- **Five-year annual trajectory, balance sheet and cash quality** (E4): nine quarters only; the
  annual figures and the balance sheet need the annual XBRL filings, not yet ingested.
- **Narrative vs numbers** as its own section (E6): the ledger's verdicts cover promised vs
  delivered; a separate narrative check was not built.

## Running it

`python scripts/ingest.py analyse [SYMBOL ...]` (default: every covered company), with
`SUPABASE_DB_URL` and the model settings of `finn/config.py` (`GEMINI_API_KEY`, `GROQ_API_KEY`,
`GLM_API_KEY`, `GLM_BASE_URL`, `GLM_MODEL`, `OPENROUTER_API_KEY`, and the model names if not the
defaults). Each company is its own run in `finn.ingest_runs`; model answers are cached by input, so a
re-run costs only what changed.
