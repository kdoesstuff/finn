# FINN API contract (v1)

The only door to FINN's data. The web app never talks to the database. This file is the contract
between the API (`api/`) and the web app (`web/`); change it first, then both sides.

Base URL: the Render service (e.g. `https://finn-api-53vw.onrender.com`). All responses are JSON,
UTF-8. Times are ISO 8601 with the Indian offset (`2026-11-06T22:06:58+05:30`).

## Errors

Every error has one shape:

```json
{"error": {"code": "unauthorised", "message": "Sign in again: your session has expired."}}
```

| HTTP | code | When |
| --- | --- | --- |
| 400 / 422 | `bad_request` | A parameter is missing, malformed or out of range (message names it) |
| 401 | `unauthorised` | No token, a bad token or an expired one |
| 403 | `forbidden` | The token is valid but may not do this (e.g. a write as the demo investor) |
| 404 | `not_found` | Unknown route or resource |
| 429 | `rate_limited` | Too many requests; `Retry-After` header gives seconds |
| 503 | `unavailable` | The database is unreachable; the web app falls back to its saved copy |

## Sessions

Reviewers use a one-tap, read-only demo investor (decision 2). There is no sign-up.

`POST /v1/session/demo` (no body)

```json
{"token": "<opaque, signed>", "expires_at": "2026-11-16T03:07:00+05:30",
 "investor": {"name": "Demo investor", "demo": true, "network": false}}
```

- The token is sent back as `Authorization: Bearer <token>` on every other `/v1` call. It is not a
  cookie (the API and the web app are on different sites, where browsers block third-party cookies).
- The token is signed by the server and carries the investor, an expiry (12 hours), read-only for
  the demo, and which deployment issued it (`core` or `full`, from the request's `Origin`, which
  must be on the allow-list). `investor.network` is true only for a `full` deployment and an
  investor with the network switched on; Network endpoints (task G5) check both.

## Health

`GET /health` (no auth; used by the keep-warm ping and the web app's "waking up" check)

```json
{"ok": true, "db": true, "data_as_of": "2026-11-15T15:07:41+05:30", "version": "bf56e5f"}
```

`data_as_of` is when the last successful filings ingest finished; `db: false` (HTTP 200) means the
API is up but cannot reach the database.

## Digest

`GET /v1/digest?hours=24`

- `hours`: the window, 1 to 744 (31 days). Default 24.

```json
{
  "window": {"hours": 24, "from": "2026-11-14T15:07:00+05:30", "to": "2026-11-15T15:07:00+05:30"},
  "data_as_of": "2026-11-15T15:07:41+05:30",
  "summary": "1 item needs your attention. 8 worth knowing; 18 routine filings set aside.",
  "portfolio": {"holdings": 18, "pledges": [Pledge]},
  "attention": [Item],
  "worth": [Item],
  "routine": {"count": 18, "by_kind": {"earnings_call": 8, "newspaper": 4, "unclassified": 3, "agm_egm": 2,
                                       "compliance": 1}},
  "unexplained_moves": [Move]
}
```

`Item` is one event: the filing that best says what happened, plus every other filing about it.

```json
{
  "id": "106851770",
  "symbol": "ASIANPAINT",
  "company": "Asian Paints Limited",
  "ts": "2026-11-06T22:06:58+05:30",
  "headline": "Appointment of Mr Leo Puri as Independent Director of the company w.e.f. September 07, 2026",
  "label": "Appointment",
  "url": "https://nsearchives.nseindia.com/corporate/ASIANPAINT_06112026220521_SE_intimation.pdf",
  "category": "management_change",
  "subtype": "",
  "role": "director",
  "action": "appointment",
  "detail_in_document": false,
  "tier": 1,
  "score": 55,
  "alert": false,
  "reasons": ["Board change below the top team"],
  "related": [
    {"id": "106851762", "ts": "2026-11-06T22:02:45+05:30", "label": "Change in Director(s)",
     "headline": "Change in Director(s)", "url": "https://nsearchives.nseindia.com/corporate/..."}
  ],
  "results": null,
  "moves": []
}
```

- `headline` is the company's own words from the filing summary, with NSE's template ("X has
  informed the Exchange about ...") removed; when the summary only restates NSE's label,
  `headline` is the label and `detail_in_document` is true (the PDF says what happened).
- `url` is always the source document on NSE (evidence for every item).
- `reasons` explain the rank ("why am I seeing this"), in ranked order.
- Items within a section are already ordered: most important first.
- `results` is null except on a quarterly results filing whose quarter is stored (task D1); then it
  holds the numbers from the filing's XBRL, and `headline` is written from them ("Q2 FY27 results:
  revenue ₹73,188 cr, up 11.2% YoY; PAT ₹12,075 cr, up 1.4% YoY"). No number is ever estimated: if
  the quarter is not stored yet, `results` is null and the headline is the company's own words.
- `moves` are the price and volume moves this filing may explain: sessions after it (the first two)
  or, for a filing published after the close, that day's session. The same move can sit on two
  items about one company.

`Results` (all values in ₹ crore; `template` is `standard`, or `bank` for banks and lenders filing
the banking format, which has no revenue or EBITDA):

```json
{
  "quarter": "Q2 FY27",
  "period_end": "2026-09-30",
  "basis": "consolidated",
  "template": "standard",
  "unit": "₹ crore",
  "rows": [
    {"metric": "EBITDA", "value": 19210.0, "margin": 26.2,
     "qoq": {"pct": 4.1, "note": "", "margin_bps": 30}, "yoy": {"pct": 9.8, "note": "", "margin_bps": -40}}
  ],
  "notes": ["EBITDA = PBT before exceptional items + finance costs + depreciation and amortisation - other income"],
  "source": "https://nsearchives.nseindia.com/corporate/xbrl/..."
}
```

- `rows` are Revenue, EBITDA, PBT and PAT (standard) or Net interest income, Operating profit,
  Provisions and PAT (bank), in that order. `margin` is a % of revenue (null for revenue and in the
  bank template); `qoq` and `yoy` give `pct`, or null with a `note` when a % would mislead ("turned
  positive", "loss narrowed", "not available"); `margin_bps` is the margin's change, or null.

`Move` (a session's close-to-close change or volume crossing the investor's thresholds, from
`finn.prefs`; defaults 5% or 3 sigma, and 2x the 20-day volume):

```json
{"symbol": "ABB", "company": "ABB India Limited", "day": "2026-11-09", "kind": "move", "value": -7.0,
 "threshold": 5.0, "sigma": -3.4, "fired_by": "both",
 "detail": "Closed down 7.0%, a 3.4 sigma day against its last 60 sessions"}
```

- `kind` is `move` (`value` is the day's % change) or `volume` (`value` is the multiple of the
  average); `sigma` is the move in units of the stock's recent daily volatility, null for volume or
  with too little history; `fired_by` says which rule crossed (`pct`, `sigma` or `both`; empty for
  volume). Days NSE adjusted for a split, bonus or rights issue are not moves.
- `unexplained_moves` are moves in the window that no filing explains: newest first.

`Pledge` (holdings whose promoters have pledged shares, from NSE's pledge disclosures; holdings with
nothing pledged are not listed):

```json
{"symbol": "KALYANKJIL", "company": "Kalyan Jewellers India Limited", "pct_of_promoter": 24.85,
 "promoter_stake_pct": 62.85, "as_of": "2026-09-30", "published": "2026-11-09T16:31:54+05:30",
 "change_pct_points": null}
```

- `pct_of_promoter` is the share of the promoters' own stake that is pledged; `as_of` is the
  shareholding date the disclosure refers to, `published` when NSE published it.
  `change_pct_points` is the change since NSE's previous disclosure, null when there is none.

## Company research (Pull)

`GET /v1/companies?q=` finds up to 10 companies by symbol or name (exact symbol first, then symbol
prefix, then name); `q` is 1-60 characters. `covered` says whether FINN keeps deep data on it.

```json
{"query": "tata", "companies": [{"symbol": "TATAPOWER", "name": "Tata Power Company Limited", "covered": true}]}
```

`GET /v1/company/{symbol}` is the company page, for any NSE company FINN has seen (404 otherwise; a
malformed symbol is 422). Every listed company has prices (every bhavcopy row is stored) and its
filings since 1 October; covered companies also have up to nine quarters of results from their XBRL
filings (`results`, newest first, consolidated where filed; banks use the bank template), their
documents, and analyses built from those documents. `coverage.missing` says in plain words what the
page does not have. `price` and `results` are `null` when there is nothing to show; each entry of
`analyses` is `null` until it has been built. Every claim inside an analysis carries the quote it
rests on, its page and the source document's link (see "Analyses" below).

```json
{
  "symbol": "TCS",
  "name": "Tata Consultancy Services Limited",
  "isin": "INE467B01029",
  "industry": "Computers - Software & Consulting",
  "data_as_of": "2026-11-09T23:31:05+05:30",
  "coverage": {"level": "deep", "reason": "holding", "missing": ["Not built yet: business snapshot."]},
  "price": {"day": "2026-11-06", "close": 2498.5, "change_1d_pct": -0.4, "change_1m_pct": 3.1,
            "change_since_pct": 6.2, "since": "2026-06-25", "volume": 2104567, "avg_volume_20d": 2400311},
  "results": {
    "template": "standard", "basis": "consolidated", "unit": "₹ crore",
    "latest": {"template": "standard", "period_end": "2026-09-30", "basis": "consolidated", "unit": "₹ crore",
               "rows": [{"metric": "Revenue", "value": 73188.0,
                         "qoq": {"pct": 2.1, "note": ""}, "yoy": {"pct": 11.2, "note": ""}}],
               "notes": ["EBITDA = ..."], "source": "https://nsearchives.nseindia.com/corporate/xbrl/x.xml"},
    "quarters": [{"period_end": "2026-09-30", "revenue": 73188.0, "ebitda": 19554.0, "ebitda_margin": 26.7,
                  "pbt": 18120.0, "pat": 13410.0, "pat_margin": 18.3,
                  "source": "https://nsearchives.nseindia.com/corporate/xbrl/x.xml"}],
    "notes": ["EBITDA = ..."]
  },
  "filings": {"days": 90, "items": [Item], "more": 0, "routine": {"count": 12, "by_kind": {"earnings_call": 5}}},
  "documents": [{"kind": "transcript", "title": "Q2 FY27 earnings call", "period": "2026-09-30",
                 "published": "2026-10-14", "url": "https://nsearchives.nseindia.com/corporate/t.pdf", "pages": 18}],
  "analyses": {"ledger": {"summary": "kept 5 of 8 measurable promises"}, "snapshot": null, "bull_bear": null}
}
```

The quarters of a bank carry `nii`, `operating_profit`, `provisions` and `pat` instead of revenue,
EBITDA and PBT. The `latest` card is the digest's results card, computed by the same code.

### Analyses

Built offline from the company's own documents (`python scripts/ingest.py analyse`), never from
outside knowledge. Each has `sources` (the documents read: kind, title, url), `model`, and
`generated_at`, besides its own fields:

- `ledger`: `summary` ("kept 5 of 8 measurable promises"), `counts` (kept, missed, partly,
  too_early, not_measurable), `statements` (each: `said_in` (the call's quarter end), `quote`,
  `page`, `url`, `metric`, `target`, `horizon`, `status`, `evidence`: what decided the status, either
  a later quote (`kind` "quote", with `quote`, `page`, `url`) or delivered numbers (`kind`
  "numbers", with `metric`, `value`, `period_end`, `url`), or `null` when not measurable), and
  `gaps` (documents that could not be read, in plain words).
- `snapshot`: `points`, each a sentence with its `quote`, `page` and `url`, grouped by `topic`
  (business, segments, revenue mix).
- `bull_bear`: `bull` and `bear`, each a list of points in the same form.

## Limits

- Rate limit: 60 requests a minute per client for `/v1`, 10 a minute for `/v1/session/demo`.
- Request bodies over 16 KB are refused. Every database call has a 5-second statement timeout.
- CORS: only the two web origins on the allow-list (`ALLOWED_ORIGINS_CORE`, `ALLOWED_ORIGINS_FULL`).

## Saved copy (fallback)

`scripts/export_snapshot.py` writes the demo investor's digest for a 7-day window, in exactly the
`/v1/digest` shape plus `"snapshot": true` and `"generated_at"`, to `web/public/snapshot.json`. The web
app shows it, clearly labelled with its time, when the API cannot answer.

## Network (full edition only)

The Founding brief's Network layer. Every route below, and `who_to_call` in the digest, exists only
for a session started from the `full` site (`dep: "full"`) whose investor has the network switched on.
A `core` session gets `404 not_found` with the same message as a route that does not exist. Reads run
as `finn_api` in the investor's scope (row-level security); nothing is written; network data is
never sent to a model. The demo investor's network is synthetic: about 150 fictional people
(`db/seed/network.json`, labelled `"synthetic": true`).

**`who_to_call` on digest items** (full only): up to two people per item, best placed to explain it.

```jsonc
"who_to_call": [
  {"person_id": "p061", "name": "Pranav Seshadri",
   "why": "Plant Head at Tata Power since 2019: knows how projects and capacity are run there; worked in operations.",
   "degree": 1, "via": null,
   "caution": "Works there now: ask about what is already public, never about unpublished price-sensitive information."}
]
```

`degree` is 1 for a direct contact, 2 for someone a contact knows (`via` names the contact).
`caution` is set for current employees of the listed company (SEBI's insider-trading rules).

**`GET /v1/network/company/{symbol}?category=`** (`category`: a digest category such as `capex`,
`results`, `management_change`; optional). Who worked there and who is best placed to explain an event
of that kind, each with the path that justifies it:

```jsonc
{"symbol": "TATAPOWER", "company": "Tata Power", "sector": "power", "synthetic": true,
 "you_worked_there": [],
 "worked_there": [Answer], "best_placed": [Answer]}
// Answer:
{"person_id": "p061", "name": "Pranav Seshadri", "headline": "Plant Head, Tata Power", "degree": 1,
 "why": "...", "how": "Classmate, IIM Ahmedabad (PGP 2010) (tie strength 5 of 5)", "via": null,
 "caution": "...", "path": [{"from": "you", "to": "Pranav Seshadri", "to_id": "p061",
                             "kind": "classmate", "strength": 5, "context": "Classmate, IIM Ahmedabad (PGP 2010)"}]}
```

**`GET /v1/network/person/{id}`** (`p001`...): diligence on one person.

```jsonc
{"id": "p030", "name": "...", "headline": "...", "location": "Mumbai", "degree": 1, "synthetic": true,
 "career": ["Credit Analyst, HDFC Bank (2010-2016)", "Head of Credit, HDFC Bank (since 2016)"],
 "schools": ["IIM Ahmedabad, PGP (2010)"], "how": "...", "path": [Step],
 "overlaps": ["IIM Ahmedabad, same year (2010)"],
 "what_to_ask": ["How HDFC Bank's risk and credit side works (now), and what changed after they joined."]}
```

**`GET /v1/network/ask?q=`** (1 to 200 characters): a short question, answered with the matching
type: `company` (adds `company`, as above), `person` (adds `person`), `expertise` (a sector, a function
or both), `reconnect` (strong ties gone quiet, with a recent filing where they worked as the reason to
call), or `help` (adds `examples`).

```jsonc
{"question": "Who knows auto components?", "kind": "expertise", "title": "Who knows auto components",
 "answers": [Answer]}
```
