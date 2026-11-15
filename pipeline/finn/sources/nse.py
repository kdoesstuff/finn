"""NSE endpoints FINN uses, each as a pure parser (tested on recorded responses) and a thin fetcher.

Endpoints and field names were found by probing from GitHub's runners on 9 Nov 2026 (handoff
section 8). Results moved to SEBI's Integrated Filing in 2025: the legacy results index stops at
Dec 2024, so both are read and the latest revision of each quarter and basis wins.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..models import Announcement
from ..pledges import Pledge
from ..pledges import parse as parse_pledge
from .client import Source, SourceError

ARCHIVES = "https://nsearchives.nseindia.com"


def _d(day: date) -> str:
    return f"{day:%d-%m-%Y}"


def _dt(text: str, *formats: str) -> datetime | None:
    text = (text or "").strip()
    for f in formats:
        try:
            return datetime.strptime(text.title() if "%b" in f else text, f)
        except ValueError:
            continue
    return None


def _rows(data: Any) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("data") or data.get("rows") or []
        return rows if isinstance(rows, list) else []
    return []


# Announcements ------------------------------------------------------------------------------------

def parse_announcement(row: dict) -> Announcement:
    ts = _dt(row.get("an_dt", ""), "%d-%b-%Y %H:%M:%S") or _dt(row.get("sort_date", ""), "%Y-%m-%d %H:%M:%S")
    if ts is None:
        raise SourceError(f"announcement {row.get('seq_id')}: no usable timestamp")
    return Announcement(
        id=str(row["seq_id"]), symbol=row["symbol"], company=row.get("sm_name") or row["symbol"], ts=ts,
        source="NSE", label=row.get("desc") or "", subject=row.get("attchmntText") or "",
        url=row.get("attchmntFile") or "", file_size=row.get("fileSize") or "",
    )


def announcement_rows(client: Source, start: date, end: date, symbol: str | None = None) -> list[dict]:
    """NSE's raw announcement rows (ingest keeps the company fields that Announcement does not)."""
    params: dict[str, Any] = {"index": "equities", "from_date": _d(start), "to_date": _d(end)}
    if symbol:
        params["symbol"] = symbol
    return _rows(client.api("corporate-announcements", **params))


def announcements(client: Source, start: date, end: date, symbol: str | None = None) -> list[Announcement]:
    return [parse_announcement(r) for r in announcement_rows(client, start, end, symbol)]


# Companies ----------------------------------------------------------------------------------------

@dataclass
class Company:
    symbol: str
    name: str | None = None
    isin: str | None = None
    industry: str | None = None


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if text in ("", "-", "None", "null") else text


def company_from_announcement(row: dict) -> Company:
    """Name and industry only. The ISIN on filings can be stale: Asian Paints' filings in Nov 2026
    still carried INE021A01018 while that week's bhavcopy traded it as INE021A01026. ISINs come
    from the bhavcopy and the equity master, which are current."""
    return Company(row["symbol"], _clean(row.get("sm_name")), None, _clean(row.get("smIndustry")))


EQUITY_LIST_URL = f"{ARCHIVES}/content/equities/EQUITY_L.csv"


def parse_equity_list(csv_bytes: bytes) -> list[Company]:
    """NSE's list of listed equities: SYMBOL, NAME OF COMPANY, SERIES, ..., ISIN NUMBER, ...
    Column names carry stray spaces in NSE's file, so they are matched after stripping."""
    out = []
    for raw in csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))):
        r = {(k or "").strip().upper(): (v or "").strip() for k, v in raw.items()}
        symbol = r.get("SYMBOL", "")
        if symbol:
            out.append(Company(symbol, _clean(r.get("NAME OF COMPANY")), _clean(r.get("ISIN NUMBER"))))
    return out


def equity_list(client: Source) -> list[Company]:
    blob = client.content(EQUITY_LIST_URL)
    if blob is None:
        raise SourceError(f"{EQUITY_LIST_URL}: not found")
    return parse_equity_list(blob)


# Results ------------------------------------------------------------------------------------------

@dataclass
class ResultFiling:
    """One results XBRL as indexed by NSE: which quarter, which basis, where the file is."""

    symbol: str
    quarter_end: date
    consolidated: bool
    audited: str
    broadcast: datetime
    xbrl_url: str
    revision: bool = False
    source: str = "integrated"  # "integrated" (2025 onward) or "legacy" (to Dec 2024)


def parse_integrated(rows: list[dict]) -> list[ResultFiling]:
    out = []
    for r in rows:
        if "financ" not in str(r.get("type", "")).lower() or not str(r.get("xbrl", "")).endswith(".xml"):
            continue  # governance filings, or no machine-readable file
        qe = _dt(r.get("qe_Date", ""), "%d-%b-%Y")
        # NSE leaves broadcast_Date empty on revisions and stamps creation_Date instead.
        bc = next((t for t in (_dt(r.get(k) or "", "%d-%b-%Y %H:%M:%S")
                               for k in ("broadcast_Date", "creation_Date", "revised_Date")) if t), None)
        if qe is None or bc is None or r.get("consolidated") not in ("Consolidated", "Standalone"):
            continue
        out.append(ResultFiling(
            symbol=r.get("symbol", ""), quarter_end=qe.date(), consolidated=r["consolidated"] == "Consolidated",
            audited=r.get("audited") or "", broadcast=bc, xbrl_url=r["xbrl"],
            revision=str(r.get("type_Sub", "")).lower().startswith("revision"),
        ))
    return out


def parse_legacy(rows: list[dict]) -> list[ResultFiling]:
    out = []
    for r in rows:
        if r.get("period") != "Quarterly" or not str(r.get("xbrl", "")).startswith("http"):
            continue
        qe = _dt(r.get("toDate", ""), "%d-%b-%Y")
        bc = _dt(r.get("broadCastDate", ""), "%d-%b-%Y %H:%M:%S")
        if qe is None or bc is None:
            continue
        out.append(ResultFiling(
            symbol=r.get("symbol", ""), quarter_end=qe.date(), consolidated=r.get("consolidated") == "Consolidated",
            audited=r.get("audited") or "", broadcast=bc, xbrl_url=r["xbrl"], source="legacy",
        ))
    return out


def latest_per_quarter(filings: list[ResultFiling]) -> list[ResultFiling]:
    """The most recently broadcast filing for each (quarter, basis): revisions replace originals."""
    best: dict[tuple[date, bool], ResultFiling] = {}
    for f in filings:
        key = (f.quarter_end, f.consolidated)
        if key not in best or f.broadcast > best[key].broadcast:
            best[key] = f
    return sorted(best.values(), key=lambda f: (f.quarter_end, f.consolidated), reverse=True)


def integrated_index(client: Source, symbol: str, max_pages: int = 10) -> list[dict]:
    """Every row of the paginated Integrated Filing index for one company."""
    rows: list[dict] = []
    seen: set[Any] = set()
    for page in range(1, max_pages + 1):
        data = client.api("integrated-filing-results", index="equities", symbol=symbol, page=page)
        fresh = [r for r in _rows(data) if r.get("seq_Id") not in seen]
        if not fresh:
            break
        seen.update(r.get("seq_Id") for r in fresh)
        rows.extend(fresh)
        total = int(data.get("totalCount") or 0) if isinstance(data, dict) else 0
        if total and len(rows) >= total:
            break
    return rows


def result_filings(client: Source, symbol: str) -> list[ResultFiling]:
    """Latest filing per quarter and basis, from both indexes (legacy to Dec 2024, integrated after)."""
    integrated = parse_integrated(integrated_index(client, symbol))
    legacy = parse_legacy(_rows(client.api("corporates-financial-results", index="equities", symbol=symbol,
                                           period="Quarterly")))
    return latest_per_quarter(integrated + legacy)


# End-of-day prices ---------------------------------------------------------------------------------

@dataclass
class EodRow:
    symbol: str
    series: str
    day: date
    isin: str
    close: float
    prev_close: float
    volume: int
    turnover: float  # ₹


def bhavcopy_url(day: date) -> str:
    return f"{ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"


def parse_bhavcopy(csv_bytes: bytes, series: tuple[str, ...] = ("EQ", "BE")) -> list[EodRow]:
    """NSE's UDiFF bhavcopy (TckrSymb, SctySrs, ClsPric, PrvsClsgPric, TtlTradgVol, TtlTrfVal)."""
    out = []
    for r in csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))):
        if r.get("SctySrs") not in series:
            continue
        try:
            out.append(EodRow(
                symbol=r["TckrSymb"], series=r["SctySrs"], day=date.fromisoformat(r["TradDt"]),
                isin=r.get("ISIN") or "", close=float(r["ClsPric"]), prev_close=float(r["PrvsClsgPric"]),
                volume=int(float(r["TtlTradgVol"])), turnover=float(r["TtlTrfVal"]),
            ))
        except (KeyError, ValueError):
            continue
    return out


def unzip_single(blob: bytes) -> bytes:
    if blob[:2] != b"PK":
        raise SourceError("bhavcopy is not a zip file")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            if len(names) != 1 or z.getinfo(names[0]).file_size > 50_000_000:
                raise SourceError(f"unexpected bhavcopy archive: {names[:3]}")
            return z.read(names[0])
    except zipfile.BadZipFile as exc:  # a truncated download: a source problem, retried next run
        raise SourceError(f"bhavcopy archive is damaged: {exc}") from exc


def bhavcopy(client: Source, day: date) -> list[EodRow] | None:
    """Every equity's close and volume for one day, or None if NSE published no file (not a session)."""
    blob = client.content(bhavcopy_url(day))
    return None if blob is None else parse_bhavcopy(unzip_single(blob))


# Pledges, board meetings, annual reports, insider trades, corporate actions -------------------------

def pledges(client: Source) -> list[Pledge]:
    out = []
    for r in _rows(client.api("corporate-pledgedata", index="equities")):
        try:
            out.append(parse_pledge(r))
        except (KeyError, ValueError):
            continue
    return out


@dataclass
class BoardMeeting:
    symbol: str
    day: date
    purpose: str
    description: str
    announced: datetime | None
    company: Company | None = None


def parse_board_meetings(rows: list[dict]) -> list[BoardMeeting]:
    out = []
    for r in rows:
        day = _dt(r.get("bm_date", ""), "%d-%b-%Y")
        if day is None or not r.get("bm_symbol"):
            continue
        out.append(BoardMeeting(r["bm_symbol"], day.date(), r.get("bm_purpose") or "", r.get("bm_desc") or "",
                                _dt(r.get("bm_timestamp", ""), "%d-%b-%Y %H:%M:%S"),
                                Company(r["bm_symbol"], _clean(r.get("sm_name")), None, _clean(r.get("sm_indusrty")))))
    return out


def board_meetings(client: Source, start: date, end: date) -> list[BoardMeeting]:
    return parse_board_meetings(_rows(client.api("corporate-board-meetings", index="equities",
                                                 from_date=_d(start), to_date=_d(end))))


@dataclass
class AnnualReport:
    from_year: int
    to_year: int
    url: str
    published: datetime | None


def parse_annual_reports(rows: list[dict]) -> list[AnnualReport]:
    out = []
    for r in rows:
        try:
            fy = int(r["fromYr"]), int(r["toYr"])
        except (KeyError, ValueError):
            continue
        if str(r.get("fileName", "")).startswith("http"):
            out.append(AnnualReport(fy[0], fy[1], r["fileName"],
                                    _dt(r.get("broadcast_dttm", ""), "%d-%b-%Y %H:%M:%S")))
    return sorted(out, key=lambda a: a.to_year, reverse=True)


def annual_reports(client: Source, symbol: str) -> list[AnnualReport]:
    return parse_annual_reports(_rows(client.api("annual-reports", index="equities", symbol=symbol)))


def insider_trades(client: Source, symbol: str) -> list[dict]:
    """SEBI PIT disclosures for one company. NSE returns rows only per symbol, not market-wide."""
    return _rows(client.api("corporates-pit", index="equities", symbol=symbol))


@dataclass
class CorporateAction:
    symbol: str
    ex_date: date
    subject: str


def parse_corporate_actions(rows: list[dict]) -> list[CorporateAction]:
    out = []
    for r in rows:
        ex = _dt(r.get("exDate", ""), "%d-%b-%Y")
        if ex is not None:
            out.append(CorporateAction(r.get("symbol", ""), ex.date(), r.get("subject") or ""))
    return out


def corporate_actions(client: Source, symbol: str) -> list[CorporateAction]:
    return parse_corporate_actions(_rows(client.api("corporates-corporateActions", index="equities",
                                                    symbol=symbol)))
