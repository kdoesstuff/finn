"""Save real NSE samples as test fixtures, so parsers are built and tested against actual data.

Captures, into fixtures/:
  nse_announcements.json      every filing over the last few days, plus the full list of `desc` values
  results_<SYM>.json          the quarterly results index for each sample company
  xbrl/<SYM>_<period>.xml     the last five quarters of results XBRL (enough for QoQ and YoY)
  bhavcopy.csv                one day of the all-stocks EOD file
  pledges.json                promoter pledge data
  insider.json                insider trading disclosures (tries several parameter shapes)
  annual_reports_<SYM>.json   NSE's annual report index for one company
  transcript_<SYM>.pdf        one concall transcript, found among the company's filings

Run:  python scripts/capture_fixtures.py  (writes to ./fixtures)
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from probe_sources import TIMEOUT, UA, nse_session, weekdays_back

OUT = Path("fixtures")
SAMPLES = ["TCS", "HDFCBANK", "ASIANPAINT"]  # IT services, a bank, a manufacturer
S = nse_session()
LOG: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


def get_json(path: str, **params):
    r = S.get(f"https://www.nseindia.com/api/{path}", params=params, timeout=TIMEOUT)
    time.sleep(0.7)
    r.raise_for_status()
    return r.json()


def save(name: str, data) -> None:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (bytes, bytearray)):
        p.write_bytes(data)
    elif isinstance(data, str):
        p.write_text(data)
    else:
        p.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    log(f"saved {p} ({p.stat().st_size:,} bytes)")


def step(name, fn):
    try:
        fn()
    except Exception as exc:
        log(f"FAILED {name}: {type(exc).__name__}: {exc}")


def announcements():
    to, frm = date.today(), date.today() - timedelta(days=5)
    rows = get_json("corporate-announcements", index="equities", from_date=f"{frm:%d-%m-%Y}", to_date=f"{to:%d-%m-%Y}")
    descs: dict[str, int] = {}
    for r in rows:
        descs[r.get("desc", "")] = descs.get(r.get("desc", ""), 0) + 1
    save("nse_announcements.json", {"rows": rows, "desc_counts": dict(sorted(descs.items(), key=lambda x: -x[1]))})


def results_and_xbrl():
    for sym in SAMPLES:
        rows = get_json("corporates-financial-results", index="equities", symbol=sym, period="Quarterly")
        save(f"results_{sym}.json", rows)
        cons = [r for r in rows if r.get("consolidated") == "Consolidated" and str(r.get("xbrl", "")).startswith("http")]
        if not cons:  # some companies (often banks) file standalone only
            cons = [r for r in rows if str(r.get("xbrl", "")).startswith("http")]
        cons.sort(key=lambda r: datetime.strptime(r["toDate"], "%d-%b-%Y"), reverse=True)
        seen = set()
        for r in cons:
            if r["toDate"] in seen:
                continue
            seen.add(r["toDate"])
            x = S.get(r["xbrl"], timeout=TIMEOUT)
            time.sleep(0.7)
            end = datetime.strptime(r["toDate"], "%d-%b-%Y").date()
            save(f"xbrl/{sym}_{end:%Y-%m-%d}_{r.get('consolidated', 'NA')[:4]}.xml", x.content)
            if len(seen) == 5:
                break


def bhavcopy():
    for d in weekdays_back(6):
        url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
        r = S.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code == 200 and r.content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                save("bhavcopy.csv", z.read(z.namelist()[0]))
            return
    log("FAILED bhavcopy: no file in the last six weekdays")


def pledges():
    save("pledges.json", get_json("corporate-pledgedata", index="equities"))


def insider():
    to, frm = date.today(), date.today() - timedelta(days=10)
    variants = [
        {"index": "equities", "from_date": f"{frm:%d-%m-%Y}", "to_date": f"{to:%d-%m-%Y}"},
        {"index": "equities"},
        {"index": "equities", "symbol": "TCS"},
        {"index": "equities", "period": "1M"},
    ]
    attempts = []
    for v in variants:
        try:
            data = get_json("corporates-pit", **v)
            rows = data.get("data", []) if isinstance(data, dict) else data
            attempts.append({"params": v, "rows": len(rows), "keys": list(data)[:10] if isinstance(data, dict) else "list"})
            if rows:
                save("insider.json", {"params": v, "data": rows[:300]})
                break
        except Exception as exc:
            attempts.append({"params": v, "error": str(exc)[:200]})
    save("insider_attempts.json", attempts)


def annual_reports():
    save("annual_reports_TCS.json", get_json("annual-reports", index="equities", symbol="TCS"))


def transcript():
    to, frm = date.today(), date.today() - timedelta(days=200)
    rows = get_json("corporate-announcements", index="equities", symbol="TCS",
                    from_date=f"{frm:%d-%m-%Y}", to_date=f"{to:%d-%m-%Y}")
    calls = [r for r in rows if "Con. Call" in r.get("desc", "")]
    save("tcs_call_filings.json", calls)
    pick = next((r for r in calls if re.search(r"transcript", r.get("attchmntText", ""), re.I)), None)
    if not pick:
        log("no transcript among TCS call filings; saved the call filings list instead")
        return
    pdf = S.get(pick["attchmntFile"], timeout=TIMEOUT)
    save("transcript_TCS.pdf", pdf.content)


def main():
    OUT.mkdir(exist_ok=True)
    for name, fn in [("announcements", announcements), ("results and xbrl", results_and_xbrl),
                     ("bhavcopy", bhavcopy), ("pledges", pledges), ("insider", insider),
                     ("annual reports", annual_reports), ("transcript", transcript)]:
        step(name, fn)
    save("capture_log.txt", "\n".join(LOG))


if __name__ == "__main__":
    main()
