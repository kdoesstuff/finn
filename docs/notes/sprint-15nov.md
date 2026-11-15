# Final sprint, 15 Nov 2026 (deadline: 23:59 IST tonight)

Four workstreams run at once, each in its own copy of the repo, merged by the lead. Every
increment must be committed, tested (pipeline, API, web suites under `CI=true`) and deployable on
its own: if time runs out, what is live must be coherent and honest.

## Ownership (do not edit another stream's files; ask the lead)

| Stream | Workspace | Owns | Migration |
| --- | --- | --- | --- |
| LLM (phase C) | `/home/claude/ws-llm` | `pipeline/finn/llm.py`, `pipeline/finn/guard.py`, `pipeline/tests/test_llm.py`, `docs/notes/llm.md`, pinned additions to `pipeline/requirements.txt` | none |
| Push (phase D) | `/home/claude/ws-push` | `pipeline/finn/digest.py`, `pipeline/finn/alerts.py`, `pipeline/finn/rank.py`, `web/src/brief/*`, push parts of `web/src/api/types.ts` and `validate.ts`, `docs/API.md` digest section, their tests | none |
| Pull (phase E) | `/home/claude/ws-pull` | `pipeline/finn/pull.py`, `pipeline/finn/documents.py`, `pipeline/finn/ledger.py`, `api/routes_pull.py`, `web/src/pull/*`, `docs/API.md` company section, their tests | `0003_pull.sql` |
| Network (phase G) | `/home/claude/ws-net` | `pipeline/finn/network.py`, `pipeline/finn/network_seed.py`, `db/seed/network.json`, `api/routes_network.py`, `web/src/network/*`, `docs/API.md` network section, their tests | `0004_network.sql` |

Shared files each stream may touch minimally (one clearly marked block each; the lead merges):
`api/app.py` (one `register(app, ...)` call per stream), `web/src/App.tsx` and
`web/src/screens/Chrome.tsx` (navigation), `pipeline/scripts/ingest.py` (one subcommand per stream),
`web/src/api/types.ts`, `web/src/api/validate.ts`, `web/src/api/client.ts` (new functions only).

## Interfaces

**LLM** (`finn.llm`), used by Pull (and Push if time allows). Never given network data.

```python
class ModelError(Exception): ...          # every model failed, or output never matched the schema

def complete_json(conn, role, prompt_version, instructions, document, schema, *,
                  max_output_tokens=4096) -> dict:
    """role: "reader" (long documents: GEMINI_MODEL -> GEMINI_OVERFLOW_MODEL -> GEMINI_QUALITY_MODEL
    -> GEMINI_QUALITY_FALLBACK_MODEL -> OPENROUTER_MODEL), "reasoner" (GLM_MODEL ->
    GEMINI_QUALITY_MODEL -> GEMINI_QUALITY_FALLBACK_MODEL -> OPENROUTER_MODEL), "fast" (GROQ_MODEL ->
    GROQ_FALLBACK_MODEL -> GEMINI_VOLUME_MODEL -> OPENROUTER_MODEL).
    `document` is untrusted text: screened by the guard, delimited, never given tools; the output must
    validate against `schema` (JSON Schema subset: type, properties, required, items, enum,
    additionalProperties false) with one repair attempt, then the next model.
    `conn` (or None in tests): cache in finn.llm_cache by sha256 of (role, prompt_version,
    instructions, document, schema); every call logged in finn.llm_calls; both as finn_ingest."""

def verify_quote(quote: str, source: str) -> bool:
    """The quote appears in the source after normalising whitespace, case and quote marks."""
```

**Pull API** (`api/routes_pull.py`, authenticated like `/v1/digest`, as `finn_api`):
`GET /v1/companies?q=` (up to 10 matches from `finn.companies` by symbol or name),
`GET /v1/company/{symbol}` (identity, latest price and recent moves, quarters from stored XBRL with
QoQ and YoY, recent filings ranked, documents, analyses: ledger, snapshot, bull_bear, each with
quotes and sources; `coverage`: "deep" for covered companies, "basic" otherwise, with what is
missing said plainly).

**Network API** (`api/routes_network.py`): only for sessions whose `dep` is `full`; a `core` session
gets 404 for every network route. `GET /v1/network/company/{symbol}`, `GET /v1/network/person/{id}`,
`GET /v1/network/ask?q=`, and `network.enrich(conn, investor_id, digest)` adds `who_to_call` to
digest items, called by the API only for `full` sessions.

## Rules carried over

No Co-Authored-By or session lines in commits; commit as `git -c user.name=Karthik -c
user.email=noreply@example.com`. Run every suite with `CI=true` before reporting. No real people's
names anywhere in the network data. Primary sources only for Pull: every sentence carries a quote
that string-matches its source, or it is dropped. What is not built is said plainly in the UI and in
`docs/notes/<stream>.md`.
