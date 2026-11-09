"""Find where NSE serves results filed in SEBI's Integrated Filing format (2025 onward).

NSE's old results index ends in early 2025, when quarterly results moved to the
Integrated Filing. This collects every /api/ path referenced by NSE's
integrated-filing and announcements pages, tries the likely ones for one
symbol, and records what each returns.

Run:  python scripts/probe_integrated.py   (writes probe_integrated.json)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta
from urllib.parse import urljoin

from probe_sources import TIMEOUT, nse_session

SYMBOL = os.environ.get("PROBE_SYMBOL", "TCS")
PAGES = [
    "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
    "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
    "https://www.nseindia.com/get-quotes/equity?symbol=" + SYMBOL,
]
S = nse_session()


def discover() -> dict:
    found: dict[str, list[str]] = {}
    scripts_seen: set[str] = set()
    for page in PAGES:
        try:
            html = S.get(page, timeout=TIMEOUT).text
        except Exception as exc:
            found.setdefault("_errors", []).append(f"{page}: {exc}")
            continue
        sources = [html]
        for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
            url = urljoin(page, src)
            if url in scripts_seen or "nseindia.com" not in url:
                continue
            scripts_seen.add(url)
            try:
                sources.append(S.get(url, timeout=TIMEOUT).text)
                time.sleep(0.3)
            except Exception:
                pass
        for text in sources:
            for path in re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]+)""", text):
                found.setdefault(path, [])
                if page not in found[path]:
                    found[path].append(page)
    return found


def try_endpoint(path: str) -> dict:
    to, frm = date.today(), date.today() - timedelta(days=400)
    attempts = []
    for params in (
        {"index": "equities", "symbol": SYMBOL},
        {"index": "equities", "symbol": SYMBOL, "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{to:%d-%m-%Y}"},
        {"index": "equities", "symbol": SYMBOL, "period": "Quarterly"},
        {"index": "equities", "symbol": SYMBOL, "type": "Integrated Filing- Financials"},
    ):
        try:
            r = S.get("https://www.nseindia.com" + path, params=params, timeout=TIMEOUT)
            time.sleep(0.5)
            entry = {"params": params, "status": r.status_code, "bytes": len(r.content)}
            try:
                data = r.json()
                rows = data.get("data", data) if isinstance(data, dict) else data
                entry["keys"] = list(data)[:12] if isinstance(data, dict) else "list"
                if isinstance(rows, list) and rows:
                    entry["rows"] = len(rows)
                    entry["first"] = {k: str(v)[:150] for k, v in list(rows[0].items())[:30]} if isinstance(rows[0], dict) else str(rows[0])[:300]
            except ValueError:
                entry["text"] = r.text[:150]
            attempts.append(entry)
            if entry.get("rows"):
                break
        except Exception as exc:
            attempts.append({"params": params, "error": str(exc)[:150]})
    return {"path": path, "attempts": attempts}


def main() -> None:
    found = discover()
    paths = [p for p in found if p.startswith("/api/")]
    likely = [p for p in paths if re.search(r"integrat|result|xbrl|financ", p, re.I)]
    for guess in ("/api/integrated-filing-results", "/api/integrated-filing", "/api/corporate-integrated-filing",
                  "/api/integrated-filing-results-data", "/api/integratedFiling"):
        if guess not in likely:
            likely.append(guess)
    tried = [try_endpoint(p) for p in likely[:25]]
    out = {"all_api_paths": sorted(paths), "tried": tried, "errors": found.get("_errors", [])}
    with open("probe_integrated.json", "w") as f:
        json.dump(out, f, indent=1)

    lines = ["| Endpoint | Rows | First fields |", "| --- | --- | --- |"]
    for t in tried:
        best = next((a for a in t["attempts"] if a.get("rows")), t["attempts"][-1] if t["attempts"] else {})
        lines.append(f"| {t['path']} | {best.get('rows', best.get('status', ''))} | "
                     f"{str(list(best.get('first', {}).keys())[:8]) if isinstance(best.get('first'), dict) else ''} |")
    table = "\n".join(lines)
    print(f"{len(paths)} API paths referenced by NSE pages")
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"## Integrated filing probe\n\n{len(paths)} API paths found.\n\n{table}\n")


if __name__ == "__main__":
    main()
