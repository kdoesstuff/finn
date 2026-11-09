"""Check which public data sources answer from the machine this runs on.

NSE in particular often refuses requests from cloud servers. Before building
fetchers on any source, this records what each one returns from GitHub's
runners: status, size, time and a short sample. Writes a Markdown table to
the job summary and the full results to probe_results.json.

Run:  python scripts/probe_sources.py
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from datetime import date, timedelta

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
TIMEOUT = 20


def weekdays_back(n: int) -> list[date]:
    out, d = [], date.today()
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def probe(name: str, fn) -> dict:
    start = time.time()
    try:
        result = fn()
        result.setdefault("ok", False)
    except Exception as exc:  # a probe must never stop the others
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    result["name"] = name
    result["seconds"] = round(time.time() - start, 2)
    return result


def _summ(r: requests.Response, want_json: bool = True) -> dict:
    out = {"status": r.status_code, "bytes": len(r.content), "content_type": r.headers.get("content-type", "")}
    if want_json:
        try:
            data = r.json()
            out["ok"] = r.status_code == 200 and bool(data)
            if isinstance(data, dict):
                out["keys"] = list(data)[:8]
                rows = data.get("Table") or data.get("data") or []
                out["rows"] = len(rows) if isinstance(rows, list) else None
                if isinstance(rows, list) and rows:
                    out["sample"] = {k: str(v)[:80] for k, v in list(rows[0].items())[:8]}
            elif isinstance(data, list):
                out["rows"] = len(data)
                if data and isinstance(data[0], dict):
                    out["sample"] = {k: str(v)[:80] for k, v in list(data[0].items())[:8]}
        except ValueError:
            out["ok"] = False
            out["sample"] = r.text[:200]
    else:
        out["ok"] = r.status_code == 200
    return out


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Accept": "*/*"})
    s.get("https://www.nseindia.com", timeout=TIMEOUT)  # sets the cookies the API checks
    return s


def nse_announcements():
    s = nse_session()
    to, frm = date.today(), date.today() - timedelta(days=3)
    r = s.get(
        "https://www.nseindia.com/api/corporate-announcements",
        params={"index": "equities", "from_date": frm.strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")},
        headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"},
        timeout=TIMEOUT,
    )
    return _summ(r)


def nse_results():
    s = nse_session()
    r = s.get(
        "https://www.nseindia.com/api/corporates-financial-results",
        params={"index": "equities", "period": "Quarterly"},
        headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"},
        timeout=TIMEOUT,
    )
    return _summ(r)


def bse_headers() -> dict:
    return {"User-Agent": UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com",
            "Accept": "application/json, text/plain, */*"}


def bse_announcements():
    to, frm = date.today(), date.today() - timedelta(days=3)
    r = requests.get(
        "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
        params={"pageno": 1, "strCat": -1, "strPrevDate": frm.strftime("%Y%m%d"), "strScrip": "",
                "strSearch": "P", "strToDate": to.strftime("%Y%m%d"), "strType": "C", "subcategory": -1},
        headers=bse_headers(), timeout=TIMEOUT,
    )
    return _summ(r)


def bse_pdf():
    """Whether attachment PDFs download (needed for results and transcripts)."""
    to, frm = date.today(), date.today() - timedelta(days=3)
    r = requests.get(
        "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
        params={"pageno": 1, "strCat": -1, "strPrevDate": frm.strftime("%Y%m%d"), "strScrip": "",
                "strSearch": "P", "strToDate": to.strftime("%Y%m%d"), "strType": "C", "subcategory": -1},
        headers=bse_headers(), timeout=TIMEOUT,
    )
    rows = r.json().get("Table", [])
    name = next((x.get("ATTACHMENTNAME") for x in rows if x.get("ATTACHMENTNAME")), None)
    if not name:
        return {"ok": False, "error": "no attachment in recent filings"}
    pdf = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{name}",
                       headers=bse_headers(), timeout=TIMEOUT)
    return {"ok": pdf.status_code == 200 and pdf.content[:4] == b"%PDF", "status": pdf.status_code,
            "bytes": len(pdf.content), "sample": name}


def nse_bhavcopy():
    """Full-market end-of-day file (new UDiFF format). Tries the last few weekdays."""
    tried = []
    for d in weekdays_back(5):
        url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        tried.append(f"{d}:{r.status_code}")
        if r.status_code == 200 and r.content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                text = z.read(z.namelist()[0]).decode("utf-8", "replace")
            lines = text.splitlines()
            return {"ok": True, "status": 200, "bytes": len(r.content), "rows": len(lines) - 1,
                    "sample": lines[0][:200], "date": str(d)}
    return {"ok": False, "tried": tried}


def yahoo():
    import yfinance as yf

    df = yf.download("RELIANCE.NS", period="1mo", interval="1d", progress=False, auto_adjust=True)
    return {"ok": not df.empty, "rows": int(len(df)),
            "sample": "" if df.empty else str(df.tail(1).to_dict("records"))[:200]}


def screener():
    r = requests.get("https://www.screener.in/company/TCS/consolidated/", headers={"User-Agent": UA}, timeout=TIMEOUT)
    text = r.text
    return {"ok": r.status_code == 200 and "Concalls" in text, "status": r.status_code, "bytes": len(r.content),
            "has_concalls": "Concalls" in text, "has_annual_reports": "Annual reports" in text}


PROBES = [
    ("NSE announcements API", nse_announcements),
    ("NSE financial results API", nse_results),
    ("NSE bhavcopy archive (EOD, all stocks)", nse_bhavcopy),
    ("BSE announcements API", bse_announcements),
    ("BSE filing PDF download", bse_pdf),
    ("Yahoo Finance via yfinance", yahoo),
    ("screener.in company page", screener),
]


def main() -> None:
    results = [probe(name, fn) for name, fn in PROBES]
    with open("probe_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    lines = ["| Source | Works | Status | Rows / size | Seconds | Note |", "| --- | --- | --- | --- | --- | --- |"]
    for r in results:
        size = r.get("rows") if r.get("rows") is not None else r.get("bytes", "")
        note = r.get("error") or r.get("tried") or ""
        lines.append(f"| {r['name']} | {'yes' if r['ok'] else 'NO'} | {r.get('status', '')} | {size} | "
                     f"{r['seconds']} | {str(note)[:120]} |")
    table = "\n".join(lines)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Data source probe\n\n" + table + "\n")


if __name__ == "__main__":
    main()
