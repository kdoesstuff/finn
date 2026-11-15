"""A covered company's own documents for Pull: its last four earnings-call transcripts and its latest
annual report, fetched from NSE and read to text page by page (task E2).

Transcripts are found among the company's NSE filings: NSE files them under "Analysts/Institutional
Investor Meet/Con. Call Updates", the same label as call schedules and recording links, so the
company's own words ("... about Transcript") decide. Each call is assigned to the quarter it
discusses: the last quarter that ended before the call. A re-filed transcript replaces the earlier
one for its quarter.

Text is extracted locally with pypdf and normalised (NFKC: the "ﬁ" ligature becomes "fi", and so on)
before anything else sees it, so a quote a model copies can be checked against the same text. A
scanned PDF has no text layer; it is reported as a gap, never guessed at. Only the annual report's
management discussion is read (up to MDA_PAGES pages from where it starts), which keeps a 300-page
report inside a model's free quota.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import psycopg

from . import db
from .sources import nse
from .sources.client import Source, SourceError

log = logging.getLogger(__name__)

CALL_LABEL = "Analysts/Institutional Investor Meet/Con. Call Updates"
TRANSCRIPTS = 4
LOOKBACK_DAYS = 400  # four quarters of calls, with room for a late one
MDA_PAGES = 30
MAX_PDF_BYTES = 40_000_000
_TRANSCRIPT = re.compile(r"\btranscripts?\b", re.IGNORECASE)
_MDA = re.compile(r"management\s*['’]?s?\s+discussion\s+(and|&)\s+analysis", re.IGNORECASE)


@dataclass
class Document:
    symbol: str
    kind: str  # 'transcript' or 'annual_report'
    title: str
    url: str
    period: date | None  # the quarter a call discusses; the financial year's end for a report
    published: date | None
    pages: list[str] = field(default_factory=list)  # page n is pages[n - 1]
    first_page: int = 1  # page number of pages[0] in the original PDF
    sha256: str = ""

    def page(self, n: int) -> str:
        i = n - self.first_page
        return self.pages[i] if 0 <= i < len(self.pages) else ""

    def numbered(self, label: str = "") -> str:
        """The text with each page marked, for a model to cite: "[<label> page 3]"."""
        tag = f"{label} " if label else ""
        return "\n\n".join(f"[{tag}page {self.first_page + i}]\n{text}" for i, text in enumerate(self.pages))


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def quarter_discussed(call: date) -> date:
    """The last quarter that ended before the call: a call on 14 Oct discusses the quarter to 30 Sep."""
    d = call - timedelta(days=1)
    for month, day in ((12, 31), (9, 30), (6, 30), (3, 31)):
        end = date(d.year, month, day)
        if end <= d:
            return end
    return date(d.year - 1, 12, 31)


def is_transcript(label: str, subject: str) -> bool:
    return label.strip() == CALL_LABEL and bool(_TRANSCRIPT.search(subject))


def find_transcripts(source: Source, symbol: str, today: date) -> list[Document]:
    """The latest transcript per quarter, newest first, at most TRANSCRIPTS (no text yet)."""
    rows = nse.announcements(source, today - timedelta(days=LOOKBACK_DAYS), today, symbol=symbol)
    latest: dict[date, Document] = {}
    for a in sorted(rows, key=lambda r: r.ts):
        if a.symbol != symbol or not is_transcript(a.label, a.subject) or not a.url.startswith("https://"):
            continue
        q = quarter_discussed(a.ts.date())
        latest[q] = Document(symbol, "transcript", f"Earnings call, quarter to {q:%d %b %Y}", a.url, q, a.ts.date())
    return [latest[q] for q in sorted(latest, reverse=True)[:TRANSCRIPTS]]


def find_annual_report(source: Source, symbol: str) -> Document | None:
    reports = nse.annual_reports(source, symbol)
    if not reports:
        return None
    r = reports[0]
    return Document(symbol, "annual_report", f"Annual report {r.from_year}-{str(r.to_year)[-2:]}", r.url,
                    date(r.to_year, 3, 31), r.published.date() if r.published else None)


def pdf_pages(blob: bytes, start_at: re.Pattern[str] | None = None, limit: int | None = None) -> tuple[list[str], int]:
    """Normalised text of each page, and the number of the first page returned. With `start_at`,
    reading begins at the first page (after the contents, page 5 on) matching it, for `limit` pages."""
    from pypdf import PdfReader  # imported here: only this job needs it, the API never does

    reader = PdfReader(io.BytesIO(blob))
    out: list[str] = []
    first = 1
    started = start_at is None
    for i, page in enumerate(reader.pages, start=1):
        text = normalise(page.extract_text() or "")
        if not started:
            if i >= 5 and start_at is not None and start_at.search(text):
                started, first = True, i
            else:
                continue
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    if not started:  # no such section: the first pages instead
        return pdf_pages(blob, None, limit)
    return out, first


def fetch_text(source: Source, doc: Document) -> str | None:
    """Downloads and reads `doc`; returns why it could not be read, or None when it was."""
    try:
        blob = source.content(doc.url)
    except SourceError as exc:
        return f"{doc.title}: NSE did not serve it ({exc})"
    if not blob:
        return f"{doc.title}: NSE has no file at its link"
    if len(blob) > MAX_PDF_BYTES:
        return f"{doc.title}: the file is larger than {MAX_PDF_BYTES // 1_000_000} MB"
    doc.sha256 = hashlib.sha256(blob).hexdigest()
    try:
        if doc.kind == "annual_report":
            doc.pages, doc.first_page = pdf_pages(blob, _MDA, MDA_PAGES)
        else:
            doc.pages, doc.first_page = pdf_pages(blob)
    except Exception as exc:  # noqa: BLE001 - a damaged PDF is a gap in one document, never a crash
        return f"{doc.title}: the PDF could not be read ({type(exc).__name__})"
    if sum(len(p) for p in doc.pages) < 200:
        return f"{doc.title}: the PDF has no text layer (a scan); it was not read"
    return None


def store(conn: psycopg.Connection, docs: list[Document]) -> None:
    """Records each read document (metadata only; the text is used in the run, not stored)."""
    with db.as_role(conn, "finn_ingest"):
        for d in docs:
            conn.execute(
                """insert into finn.documents (symbol, kind, title, period, published, url, sha256, pages)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (url) do update set title = excluded.title, period = excluded.period,
                     published = excluded.published, sha256 = excluded.sha256, pages = excluded.pages,
                     fetched_at = now()""",
                [d.symbol, d.kind, d.title, d.period.isoformat() if d.period else None, d.published, d.url,
                 d.sha256 or None, d.first_page + len(d.pages) - 1 if d.pages else None])


def gather(source: Source, symbol: str, today: date | None = None) -> tuple[list[Document], Document | None, list[str]]:
    """Transcripts (newest first) and the annual report, read; and the gaps, in plain words."""
    today = today or datetime.now().date()
    gaps: list[str] = []
    try:
        transcripts = find_transcripts(source, symbol, today)
    except SourceError as exc:
        transcripts = []
        gaps.append(f"NSE's filings for {symbol} could not be searched for transcripts ({exc})")
    if len(transcripts) < TRANSCRIPTS:
        gaps.append(f"{len(transcripts)} of the last {TRANSCRIPTS} earnings-call transcripts were found on NSE")
    read = []
    for t in transcripts:
        problem = fetch_text(source, t)
        if problem:
            gaps.append(problem)
        else:
            read.append(t)
    report: Document | None
    try:
        report = find_annual_report(source, symbol)
    except SourceError as exc:
        report = None
        gaps.append(f"NSE's annual reports for {symbol} could not be listed ({exc})")
    if report is not None:
        problem = fetch_text(source, report)
        if problem:
            gaps.append(problem)
            report = None
    elif not any(g.startswith("NSE's annual reports") for g in gaps):
        gaps.append("No annual report was found on NSE")
    return read, report, gaps
