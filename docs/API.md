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

## Limits

- Rate limit: 60 requests a minute per client for `/v1`, 10 a minute for `/v1/session/demo`.
- Request bodies over 16 KB are refused. Every database call has a 5-second statement timeout.
- CORS: only the two web origins on the allow-list (`ALLOWED_ORIGINS_CORE`, `ALLOWED_ORIGINS_FULL`).

## Saved copy (fallback)

`scripts/export_snapshot.py` writes the demo investor's digest for a 7-day window, in exactly the
`/v1/digest` shape plus `"snapshot": true` and `"generated_at"`, to `web/public/snapshot.json`. The web
app shows it, clearly labelled with its time, when the API cannot answer.
