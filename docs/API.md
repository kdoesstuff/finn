# FINN API contract (v1)

The only door to FINN's data. The web app never talks to the database. This file is the contract
between the API (`api/`) and the web app (`web/`); change it first, then both sides.

Base URL: the Render service (e.g. `https://finn-api.onrender.com`). All responses are JSON,
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
  "portfolio": {"holdings": 18},
  "attention": [Item],
  "worth": [Item],
  "routine": {"count": 18, "by_kind": {"earnings_call": 8, "newspaper": 4, "unclassified": 3}},
  "unexplained_moves": []
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
  ]
}
```

- `headline` is the company's own words from the filing summary, with NSE's template ("X has
  informed the Exchange about ...") removed; when the summary only restates NSE's label,
  `headline` is the label and `detail_in_document` is true (the PDF says what happened).
- `url` is always the source document on NSE (evidence for every item).
- `reasons` explain the rank ("why am I seeing this"), in ranked order.
- Items within a section are already ordered: most important first.
- `unexplained_moves` stays empty until price alerts (task D4).

## Limits

- Rate limit: 60 requests a minute per client for `/v1`, 10 a minute for `/v1/session/demo`.
- Request bodies over 16 KB are refused. Every database call has a 5-second statement timeout.
- CORS: only the two web origins on the allow-list (`ALLOWED_ORIGINS_CORE`, `ALLOWED_ORIGINS_FULL`).

## Saved copy (fallback)

`scripts/export_snapshot.py` writes the demo investor's digest for a 7-day window, in exactly the
`/v1/digest` shape plus `"snapshot": true` and `"generated_at"`, to `web/public/snapshot.json`. The web
app shows it, clearly labelled with its time, when the API cannot answer.
