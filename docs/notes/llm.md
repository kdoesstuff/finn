# Model layer (phase C, 15 Nov 2026)

`pipeline/finn/llm.py` (router) and `pipeline/finn/guard.py` (injection screen). Code asks for a
role, never a model:

```python
from finn import llm
answer = llm.complete_json(conn, "reader", "ledger-v1", instructions, document_text, schema)
llm.verify_quote(answer["quote"], document_text)   # callers drop anything that fails this
```

## Roles and chains

A model is skipped when its key, its name or (GLM) an https gateway is not configured.

| Role | For | Chain |
| --- | --- | --- |
| `reader` | Long documents: transcripts, annual reports, results PDFs | `GEMINI_MODEL` → `GEMINI_OVERFLOW_MODEL` → `GEMINI_QUALITY_MODEL` → `GEMINI_QUALITY_FALLBACK_MODEL` → `OPENROUTER_MODEL` |
| `reasoner` | Promise vs delivery, narrative vs numbers, bull and bear | `GLM_MODEL` (via `GLM_BASE_URL`) → `GEMINI_QUALITY_MODEL` → `GEMINI_QUALITY_FALLBACK_MODEL` → `OPENROUTER_MODEL` |
| `fast` | Short jobs: classifying leftover filings, one-liners | `GROQ_MODEL` → `GROQ_FALLBACK_MODEL` → `GEMINI_VOLUME_MODEL` → `OPENROUTER_MODEL` |

Per model: a 429, a quota 403, a timeout or any other 4xx moves to the next model at once; a 5xx or
a dropped connection is retried once after 2 s. Gemini is called natively (`generateContent`,
key in the `x-goog-api-key` header, JSON mode except for Gemma, which has none); Groq, GLM and
OpenRouter through their OpenAI-compatible `/chat/completions` (JSON mode on Groq only). Gemini's
`responseSchema` is not used: its OpenAPI dialect differs from JSON Schema, and our own validator is
the authority either way.

## Answers

The model replies `{"result": ..., "suspicious_instructions": true|false}`. `result` must match the
caller's schema: a JSON Schema subset validated in `llm.validate` (type, properties, required,
`additionalProperties: false`, items, enum, min/max items, length, minimum, maximum). Any other
keyword is refused up front (`check_schema`), so no constraint is silently ignored. A reply that is
not JSON or does not match gets one repair attempt (the reply and the exact problem are sent back),
then the next model. If no model produces a valid answer: `ModelError`, with the reason per model.

## Injection defence (C2)

1. **The guard.** Llama Prompt Guard 2 (`GUARD_MODEL`, on Groq) scores the document in overlapping
   windows of 300 words (its context is 512 tokens; windows overlap by 50 words so an instruction
   cut in two lands whole in one). Up to 48 windows per call (about 14,000 words) are all screened;
   a longer document is sampled: first and last window, then every window with a phrase typical of
   injections ("ignore previous", "system prompt", "you are now", "disregard", chat-template
   tokens...), then evenly spaced ones. A score of 0.8 or more, or a MALICIOUS/JAILBREAK/INJECTION
   label, raises `InjectionDetected`: no model sees the document.
2. **Fail closed.** If the guard is configured and cannot answer (quota, outage), the call fails
   (`ModelError`) and the document waits for the next run rather than reaching a model unscreened.
   Without `GROQ_API_KEY` the screen is skipped with a warning (a laptop without the key).
3. **Fencing.** The document sits between `<<<DOCUMENT b>>>` and `<<<END DOCUMENT b>>>`, where `b`
   is a random token checked not to occur in the document, so the document cannot close its own
   fence. The system prompt says everything inside is data; the user prompt repeats the task after
   the document ("sandwich").
4. **Reported, not obeyed.** The model is told to set `suspicious_instructions` if the document
   addresses it; that is logged as a warning (never with document text).
5. **No tools, schema-checked output, quotes checked by callers** (`verify_quote`: the quote must
   appear in the source after normalising whitespace, case, quote marks, dashes and words hyphenated
   across lines; pieces around an ellipsis must appear in order; under 12 characters proves nothing).
   Network data is never passed to this module (C2's rule, enforced by the Network stream's design).

Limits, said plainly: the guard is a small classifier and can be fooled by novel phrasing or other
languages; sampling means a very long document's unscreened middle relies on layers 3 to 5; those
layers bound what an injection can do (no tools, a fixed schema, quotes that must exist in the
source) rather than detect it.

## Cache and log

- `finn.llm_cache`, keyed by sha256 of `[role, prompt_version, instructions, document, schema]`
  (JSON, sorted keys). The model is not in the key: any model's valid answer to the same question
  is reused. Bump `prompt_version` to ask again. A cache hit skips the guard (the document was
  screened when the answer was made) and is logged with `cache_hit = true`.
- `finn.llm_calls`: one row per request (model, tokens, latency, ok, fallback_from, a short error),
  plus one row per guard screen (role `guard`). Never a key or document text.
- Both written as `finn_ingest` by default (it already holds the grants in `0001_foundation.sql`: all
  rights on `llm_cache`, select and insert on `llm_calls`; no new migration). The API may pass
  `db_role="finn_api"`, which holds the same rights.

## Live check

`python scripts/llm_check.py [--db]` makes one small call per role and runs the screen on an
obvious injection and on an ordinary sentence; it prints the model, latency, whether the answer
validated and whether its quote is in the source. It exits 1 if a role fails, the injection is not
flagged, or no key is set. It needs the model keys and names in the environment: in GitHub Actions,
`GEMINI_API_KEY`, `GROQ_API_KEY`, `GLM_API_KEY`, `GLM_BASE_URL`, `GLM_MODEL`, `OPENROUTER_API_KEY`
(and any model-name overrides from `.env`) passed as `env:` from secrets.

## Not done tonight

- C4 model evaluation (same extraction on several models against a hand-marked list): not run;
  the chains above are the handoff's, unmeasured.
- Pacing to each model's per-minute limits: a 429 simply moves to the next model.
- C3 filing reader: the Pull stream calls `complete_json` directly; no reader for generic filings.
