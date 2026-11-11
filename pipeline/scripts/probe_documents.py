"""Second probe: do the documents behind the listings download, and what fields do they carry?

The first probe showed NSE's listings answer from GitHub's runners and BSE's
API refuses them. This one follows the links: filing PDFs, results XBRL,
concall transcripts and annual reports linked from screener, plus history
depth and the insider-trading feed. It prints each source's field names so
parsers are written against real data.

Run:  python scripts/probe_documents.py
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta

import requests
from probe_sources import TIMEOUT, UA, bse_headers, nse_session

SYMBOL = os.environ.get("PROBE_SYMBOL", "TCS")


def probe(name, fn):
    start = time.time()
    try:
        out = fn()
        out.setdefault("ok", False)
    except Exception as exc:
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    out["name"] = name
    out["seconds"] = round(time.time() - start, 2)
    return out


def _download(session, url, headers=None):
    r = session.get(url, headers=headers or {}, timeout=TIMEOUT)
    if r.content[:4] == b"%PDF":
        kind = "pdf"
    elif r.content.lstrip()[:5] in (b"<?xml", b"<xbrl"):
        kind = "xml"
    else:
        kind = "zip" if r.content[:2] == b"PK" else "other"
    return r, kind


S = None


def nse():
    global S
    if S is None:
        S = nse_session()
    return S


def nse_announcement_fields():
    to, frm = date.today(), date.today() - timedelta(days=3)
    r = nse().get("https://www.nseindia.com/api/corporate-announcements",
                  params={"index": "equities", "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{to:%d-%m-%Y}"},
                  timeout=TIMEOUT)
    rows = r.json()
    first = rows[0] if isinstance(rows, list) and rows else {}
    descs = sorted({x.get("desc", "") for x in rows})[:60] if isinstance(rows, list) else []
    return {"ok": bool(first), "fields": {k: str(v)[:100] for k, v in first.items()}, "rows": len(rows),
            "distinct_desc_sample": descs}


def nse_attachment_pdf():
    to, frm = date.today(), date.today() - timedelta(days=3)
    rows = nse().get("https://www.nseindia.com/api/corporate-announcements",
                     params={"index": "equities", "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{to:%d-%m-%Y}"},
                     timeout=TIMEOUT).json()
    url = next((x.get("attchmntFile") for x in rows if str(x.get("attchmntFile", "")).endswith(".pdf")), None)
    if not url:
        return {"ok": False, "error": "no pdf attachment found"}
    r, kind = _download(nse(), url)
    return {"ok": kind == "pdf", "status": r.status_code, "bytes": len(r.content), "kind": kind, "url": url}


def nse_symbol_history():
    to, frm = date.today(), date.today() - timedelta(days=400)
    r = nse().get("https://www.nseindia.com/api/corporate-announcements",
                  params={"index": "equities", "symbol": SYMBOL, "from_date": f"{frm:%d-%m-%Y}",
                          "to_date": f"{to:%d-%m-%Y}"}, timeout=TIMEOUT)
    rows = r.json()
    dates = sorted(x.get("an_dt", "") for x in rows) if isinstance(rows, list) else []
    return {"ok": bool(rows), "status": r.status_code, "rows": len(rows) if isinstance(rows, list) else None,
            "earliest": dates[0] if dates else None, "latest": dates[-1] if dates else None}


def nse_results_fields():
    r = nse().get("https://www.nseindia.com/api/corporates-financial-results",
                  params={"index": "equities", "symbol": SYMBOL, "period": "Quarterly"}, timeout=TIMEOUT)
    rows = r.json()
    first = rows[0] if isinstance(rows, list) and rows else {}
    return {"ok": bool(first), "rows": len(rows) if isinstance(rows, list) else None,
            "fields": {k: str(v)[:120] for k, v in first.items()}}


def nse_results_xbrl():
    rows = nse().get("https://www.nseindia.com/api/corporates-financial-results",
                     params={"index": "equities", "symbol": SYMBOL, "period": "Quarterly"}, timeout=TIMEOUT).json()
    url = next((x.get("xbrl") for x in rows if str(x.get("xbrl", "")).startswith("http")), None)
    if not url:
        return {"ok": False, "error": "no xbrl link in results rows"}
    r, kind = _download(nse(), url)
    text = r.content.decode("utf-8", "replace")
    tags = sorted(set(re.findall(r"<in-bse-fin:(\w+)", text) + re.findall(r"<in-capmkt:(\w+)", text)))
    wanted = ["RevenueFromOperations", "OtherIncome", "FinanceCosts", "DepreciationDepletionAndAmortisationExpense",
              "ProfitBeforeExceptionalItemsAndTax", "ExceptionalItemsBeforeTax", "ProfitBeforeTax",
              "ProfitLossForPeriod"]
    found = {w: any(w.lower() in t.lower() for t in tags) for w in wanted}
    return {"ok": kind == "xml" and any(found.values()), "status": r.status_code, "bytes": len(r.content),
            "url": url, "kind": kind, "wanted_found": found, "tag_count": len(tags), "tags_sample": tags[:80]}


def nse_insider():
    to, frm = date.today(), date.today() - timedelta(days=7)
    r = nse().get("https://www.nseindia.com/api/corporates-pit",
                  params={"index": "equities", "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{to:%d-%m-%Y}"},
                  timeout=TIMEOUT)
    data = r.json()
    rows = data.get("data", []) if isinstance(data, dict) else data
    first = rows[0] if rows else {}
    return {"ok": bool(rows), "status": r.status_code, "rows": len(rows),
            "fields": {k: str(v)[:80] for k, v in first.items()}}


def nse_pledge():
    r = nse().get("https://www.nseindia.com/api/corporate-pledgedata", params={"index": "equities"}, timeout=TIMEOUT)
    data = r.json()
    rows = data.get("data", []) if isinstance(data, dict) else data
    first = rows[0] if rows else {}
    return {"ok": bool(rows), "status": r.status_code, "rows": len(rows),
            "fields": {k: str(v)[:80] for k, v in first.items()}}


def screener_documents():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    html = s.get(f"https://www.screener.in/company/{SYMBOL}/consolidated/", timeout=TIMEOUT).text
    links = re.findall(r'href="(https?://[^"]+)"', html)
    doc_link = r"\.pdf|AttachLive|AnnualReport|Transcript|corpfiling|nsearchives"
    pdfish = [u for u in links if re.search(doc_link, u, re.I)]
    hosts = {}
    for u in pdfish:
        host = re.sub(r"^https?://([^/]+).*", r"\1", u)
        hosts[host] = hosts.get(host, 0) + 1
    results = []
    for host in list(hosts)[:4]:
        url = next(u for u in pdfish if host in u)
        try:
            hdrs = bse_headers() if "bseindia" in host else {"User-Agent": UA}
            r, kind = _download(s, url, hdrs)
            results.append({"host": host, "url": url, "status": r.status_code, "kind": kind, "bytes": len(r.content)})
        except Exception as exc:
            results.append({"host": host, "url": url, "error": str(exc)[:120]})
    return {"ok": any(x.get("kind") == "pdf" for x in results), "document_links": len(pdfish),
            "hosts": hosts, "downloads": results}


def bse_with_session():
    s = requests.Session()
    s.headers.update(bse_headers())
    s.get("https://www.bseindia.com/", timeout=TIMEOUT)
    to, frm = date.today(), date.today() - timedelta(days=3)
    r = s.get("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
              params={"pageno": 1, "strCat": -1, "strPrevDate": f"{frm:%Y%m%d}", "strScrip": "", "strSearch": "P",
                      "strToDate": f"{to:%Y%m%d}", "strType": "C", "subcategory": -1}, timeout=TIMEOUT)
    pdf = s.get("https://www.bseindia.com/xml-data/corpfiling/AttachLive/", timeout=TIMEOUT)
    return {"ok": r.status_code == 200, "status": r.status_code, "pdf_host_status": pdf.status_code,
            "sample": r.text[:150]}


def yahoo_history():
    import yfinance as yf

    df = yf.download(f"{SYMBOL}.NS", period="5y", interval="1d", progress=False, auto_adjust=True)
    return {"ok": len(df) > 1000, "rows": int(len(df)),
            "first": str(df.index.min().date()) if len(df) else None}


PROBES = [
    ("NSE announcement fields", nse_announcement_fields),
    ("NSE filing PDF download", nse_attachment_pdf),
    (f"NSE announcements for {SYMBOL}, last 400 days", nse_symbol_history),
    ("NSE results fields", nse_results_fields),
    ("NSE results XBRL download and tags", nse_results_xbrl),
    ("NSE insider trading feed", nse_insider),
    ("NSE pledge data", nse_pledge),
    ("screener document links and downloads", screener_documents),
    ("BSE API with a browser session", bse_with_session),
    (f"Yahoo 5y history for {SYMBOL}", yahoo_history),
]


def main():
    results = []
    for name, fn in PROBES:
        results.append(probe(name, fn))
        time.sleep(1)  # be polite to the exchanges
    with open("probe_documents.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    lines = ["| Check | Works | Status | Detail | Seconds |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        detail = r.get("error") or r.get("kind") or r.get("rows") or r.get("hosts") or ""
        if "earliest" in r:
            detail = f"{r.get('rows')} filings, {r.get('earliest')} to {r.get('latest')}"
        if "wanted_found" in r:
            detail = f"{sum(r['wanted_found'].values())}/{len(r['wanted_found'])} line items found"
        ok = "yes" if r["ok"] else "NO"
        lines.append(f"| {r['name']} | {ok} | {r.get('status', '')} | {str(detail)[:140]} | {r['seconds']} |")
    table = "\n".join(lines)
    detail = json.dumps(results, indent=1, default=str)
    print(table)
    print("\n=== FULL DETAIL ===")
    print(detail)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Document probe\n\n" + table + "\n\n<details><summary>Full detail</summary>\n\n```json\n"
                    + detail[:60000] + "\n```\n</details>\n")


if __name__ == "__main__":
    main()
