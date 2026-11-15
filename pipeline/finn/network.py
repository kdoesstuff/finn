"""The investor's network: loading it, and the questions FINN answers from it.

Founding brief only. Everything is computed here, in code and SQL: network data never reaches a
model (this module does not import finn.llm, and a test checks that no module both imports finn.llm
and reads network tables). Every read runs as `finn_api` inside the investor's scope, so row-level
security returns that investor's network and nothing else. The API calls these only for sessions
of the `full` deployment, and only when the investor has the network switched on.

Questions:
- company(symbol): who worked there (now or before), who sits next to it (a sector peer, the value
  chain, a specialist), ranked for a kind of event, each with the reason and the path to them;
- person(id): diligence: career path, schools, overlaps with the investor, how the investor reaches
  them, what to ask;
- expertise(theme): who knows a sector or a function;
- reconnect(): strong ties gone quiet, with a reason to call now (a recent filing where they worked);
- ask(q): reads a short question and answers it with one of the above.

A current employee of a listed company is marked: ask them about what is already public, never about
unpublished price-sensitive information (SEBI's insider-trading rules).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from . import db
from .network_seed import COMPANIES, EXPLAINS, OUT_JSON, SECTOR_LABEL, VALUE_CHAIN

MAX_ANSWERS = 8
QUIET_AFTER_DAYS = 270
RECENT_FILING_DAYS = 30
CAUTION = ("Works there now: ask about what is already public, never about unpublished price-sensitive "
           "information.")
FUNCTION_LABEL = {
    "finance": "finance", "investor_relations": "investor relations", "strategy": "strategy",
    "operations": "operations", "engineering": "engineering", "sales": "sales", "legal": "legal and compliance",
    "hr": "people and HR", "risk": "risk and credit", "technology": "technology", "supply_chain": "supply chain",
    "research": "investment research", "audit": "audit",
}
WHY_FOR = {
    "results": "can explain what drove the numbers",
    "management_change": "knows how the board and leadership work there",
    "M&A": "knows how deals are done there",
    "capex": "knows how projects and capacity are run there",
    "fund_raise": "knows the company's funding and balance sheet",
    "credit_rating": "knows the balance sheet and its lenders",
    "litigation": "knows the legal side",
    "governance": "knows the governance and compliance side",
    "pledging": "knows the promoters' finances and the company's governance",
    "insider_trading": "knows the compliance side",
}


# --- Loading -----------------------------------------------------------------------------------

def load_network(conn: psycopg.Connection, investor_id: UUID, path: Path = OUT_JSON) -> dict[str, int]:
    """Replace the investor's network with the file's, in one transaction, as the admin (the API role
    may only read). Idempotent: loading the same file twice leaves the same rows."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    people = [data["persona"], *data["people"]]
    with conn.transaction():
        found = conn.execute("select 1 from finn.investors where id = %s", [investor_id]).fetchone()
        if not found:
            raise ValueError(f"no investor {investor_id}: run `ingest.py seed` first")
        conn.execute("delete from finn.network_people where investor_id = %s", [investor_id])
        with conn.cursor() as cur:
            cur.executemany("""insert into finn.network_people
                                 (investor_id, id, first_name, last_name, headline, location, degree, synthetic)
                               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            [(investor_id, p["id"], p["first_name"], p["last_name"], p.get("headline", ""),
                              p.get("location", ""), p["degree"], bool(p.get("synthetic", True))) for p in people])
            cur.executemany("""insert into finn.network_roles
                                 (investor_id, person_id, ord, org, symbol, sector, function, title, started, ended)
                               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            [(investor_id, p["id"], i, r["org"], r["symbol"], r["sector"], r["function"], r["title"],
                              r["started"], r["ended"]) for p in people for i, r in enumerate(p["roles"])])
            cur.executemany("""insert into finn.network_schools (investor_id, person_id, ord, school, degree, year)
                               values (%s, %s, %s, %s, %s, %s)""",
                            [(investor_id, p["id"], i, s["school"], s.get("degree", ""), s.get("year"))
                             for p in people for i, s in enumerate(p.get("schools", []))])
            cur.executemany("""insert into finn.network_edges
                                 (investor_id, from_id, to_id, kind, strength, since, last_contact, context)
                               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            [(investor_id, e["from"], e["to"], e["kind"], e["strength"], e["since"],
                              e["last_contact"], e["context"]) for e in data["edges"]])
    return {"people": len(data["people"]), "connections": len(data["edges"]),
            "first_degree": sum(1 for p in data["people"] if p["degree"] == 1)}


# --- The graph, read in the investor's scope --------------------------------------------------

@dataclass
class Person:
    id: str
    name: str
    headline: str
    location: str
    degree: int
    synthetic: bool
    roles: list[dict[str, Any]] = field(default_factory=list)
    schools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Graph:
    people: dict[str, Person]
    edges: list[dict[str, Any]]
    names: dict[str, str]  # symbol -> company name, for the companies mentioned in the network

    def edge_from_me(self, pid: str) -> dict[str, Any] | None:
        return next((e for e in self.edges if e["from"] == "me" and e["to"] == pid), None)

    def path(self, pid: str) -> list[dict[str, Any]]:
        """How the investor reaches a person: one step for a contact, two through the strongest bridge."""
        direct = self.edge_from_me(pid)
        if direct:
            return [_step("me", pid, direct, self)]
        options = []
        for e in self.edges:
            if e["to"] == pid and e["from"] != "me":
                first = self.edge_from_me(e["from"])
                if first:
                    options.append((min(first["strength"], e["strength"]), first, e))
        if not options:
            return []
        _, first, second = max(options, key=lambda o: (o[0], o[1]["strength"]))
        return [_step("me", first["to"], first, self), _step(first["to"], pid, second, self)]

    def tie(self, pid: str) -> float:
        """0 to 1: how reachable a person is (first degree by strength; second degree discounted)."""
        steps = self.path(pid)
        if not steps:
            return 0.0
        weakest = min(s["strength"] for s in steps)
        return (0.6 + 0.08 * weakest) * (1.0 if len(steps) == 1 else 0.5)


def _step(src: str, dst: str, edge: dict[str, Any], graph: Graph) -> dict[str, Any]:
    def name(pid: str) -> str:
        return "you" if pid == "me" else graph.people[pid].name

    return {"from": name(src), "to": name(dst), "to_id": dst, "kind": edge["kind"], "strength": edge["strength"],
            "context": edge["context"]}


def load_graph(conn: psycopg.Connection, investor_id: UUID) -> Graph | None:
    """The investor's network, or None when the investor has the network switched off."""
    with db.as_role(conn, "finn_api", investor_id):
        row = conn.execute("select network_enabled from finn.investors where id = finn.current_investor()").fetchone()
        if not row or not row[0]:
            return None
        people = {pid: Person(pid, f"{first} {last}", headline, location, degree, synthetic)
                  for pid, first, last, headline, location, degree, synthetic in conn.execute(
                      """select id, first_name, last_name, headline, location, degree, synthetic
                         from finn.network_people""")}
        for pid, org, symbol, sector, function, title, started, ended in conn.execute(
                """select person_id, org, symbol, sector, function, title, started, ended
                   from finn.network_roles order by person_id, ord"""):
            people[pid].roles.append({"org": org, "symbol": symbol, "sector": sector, "function": function,
                                      "title": title, "started": started, "ended": ended})
        for pid, school, degree, year in conn.execute(
                "select person_id, school, degree, year from finn.network_schools order by person_id, ord"):
            people[pid].schools.append({"school": school, "degree": degree, "year": year})
        edges = [{"from": f, "to": t, "kind": k, "strength": s, "since": since, "last_contact": lc, "context": c}
                 for f, t, k, s, since, lc, c in conn.execute(
                     """select from_id, to_id, kind, strength, since, last_contact, context
                        from finn.network_edges order by from_id, to_id""")]
        symbols = sorted({r["symbol"] for p in people.values() for r in p.roles if r["symbol"]})
        rows = conn.execute("select symbol, coalesce(name, symbol) from finn.companies where symbol = any(%s)",
                            [symbols]).fetchall()
        names: dict[str, str] = {symbol: name for symbol, name in rows}
    for s in symbols:  # FINN's short names for the covered companies; the exchange's for any other
        names[s] = COMPANIES[s][0] if s in COMPANIES else names.get(s, s)
    return Graph(people, edges, names)


# --- Describing ----------------------------------------------------------------------------------

def _period(role: dict[str, Any]) -> str:
    start = role["started"].year
    if role["ended"] is None:
        return f"since {start}"
    return f"{start}-{role['ended'].year}" if role["ended"].year != start else str(start)


def _role_line(role: dict[str, Any]) -> str:
    return f"{role['title']}, {role['org']} ({_period(role)})"


def _how(graph: Graph, pid: str) -> str:
    steps = graph.path(pid)
    if not steps:
        return "Not connected to you"
    if len(steps) == 1:
        return f"{steps[0]['context']} (tie strength {steps[0]['strength']} of 5)"
    return f"Through {steps[0]['to']} ({steps[0]['context'].lower()}): {steps[1]['context'].lower()}"


def _sector_of(symbol: str) -> str:
    return COMPANIES.get(symbol, ("", ""))[1]


def _answer(graph: Graph, pid: str, why: str, *, caution: bool = False) -> dict[str, Any]:
    p = graph.people[pid]
    steps = graph.path(pid)
    return {"person_id": pid, "name": p.name, "headline": p.headline, "degree": p.degree, "why": why,
            "how": _how(graph, pid), "via": steps[0]["to"] if len(steps) == 2 else None,
            "caution": CAUTION if caution else None, "path": steps}


# --- Questions -----------------------------------------------------------------------------------

def explain(graph: Graph, symbol: str, category: str | None = None, limit: int = MAX_ANSWERS,
            today: date | None = None) -> list[dict[str, Any]]:
    """Who is best placed to explain an event of this kind at this company, best first."""
    today = today or date.today()
    sector = _sector_of(symbol)
    company = graph.names.get(symbol) or COMPANIES.get(symbol, (symbol, ""))[0]
    wanted = EXPLAINS.get(category or "", ())
    best: dict[str, tuple[float, str, bool]] = {}
    for pid, p in graph.people.items():
        if pid == "me" or not graph.path(pid):
            continue
        for r in p.roles:
            current = r["ended"] is None
            if r["symbol"] == symbol:
                base = 1.0 if current else (0.85 if (today - r["ended"]).days < 5 * 365 else 0.7)
                where = (f"{r['title']} at {company} {_period(r)}" if current
                         else f"was {r['title']} at {company}, {_period(r)}")
            elif sector and r["symbol"] and r["sector"] == sector:
                base, where = 0.5, f"{r['title']} at {r['org']} ({_period(r)}), a {SECTOR_LABEL[sector]} peer"
            elif (sector and not r["symbol"] and r["sector"] == sector
                  and r["function"] in ("strategy", "research", "audit")):
                base, where = 0.45, f"{r['title']} at {r['org']} ({_period(r)}), a {SECTOR_LABEL[sector]} specialist"
            elif sector and frozenset({r["sector"], sector}) in VALUE_CHAIN and r["symbol"]:
                chain = VALUE_CHAIN[frozenset({r["sector"], sector})]
                base, where = 0.35, f"{r['title']} at {r['org']} ({_period(r)}), in {chain}"
            else:
                continue
            if r["function"] in wanted:
                base *= 1.3
            if not current and r["symbol"] != symbol:
                base *= 0.8
            score = base * graph.tie(pid)
            reason = WHY_FOR.get(category or "", f"knows {company} from close by")
            if r["symbol"] == symbol and r["function"] in FUNCTION_LABEL:
                reason = f"{reason}; worked in {FUNCTION_LABEL[r['function']]}"
            text = f"{where}: {reason}."
            caution = r["symbol"] == symbol and current
            if score > best.get(pid, (0.0, "", False))[0]:
                best[pid] = (score, text[0].upper() + text[1:], caution)
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], graph.people[kv[0]].name))[:limit]
    return [_answer(graph, pid, why, caution=caution) for pid, (_, why, caution) in ranked]


def company(graph: Graph, symbol: str, category: str | None = None, today: date | None = None) -> dict[str, Any]:
    """Everyone the investor can reach who worked at the company, and who can explain it."""
    name = graph.names.get(symbol) or COMPANIES.get(symbol, (symbol, ""))[0]
    inside = []
    for pid, p in graph.people.items():
        if pid == "me" or not graph.path(pid):
            continue
        roles = [r for r in p.roles if r["symbol"] == symbol]
        if roles:
            r = max(roles, key=lambda x: x["started"])
            now = r["ended"] is None
            inside.append(_answer(graph, pid, ("Works there now: " if now else "Worked there: ") + _role_line(r) + ".",
                                  caution=now))
    inside.sort(key=lambda a: (a["degree"], a["caution"] is None, a["name"]))
    you = [r for r in graph.people["me"].roles if r["symbol"] == symbol] if "me" in graph.people else []
    return {"symbol": symbol, "company": name, "sector": SECTOR_LABEL.get(_sector_of(symbol), ""),
            "you_worked_there": [_role_line(r) for r in you], "worked_there": inside,
            "best_placed": explain(graph, symbol, category, today=today), "synthetic": True}


def person(graph: Graph, pid: str) -> dict[str, Any] | None:
    """Diligence on one person: career, schools, overlaps with the investor, the path, what to ask."""
    p = graph.people.get(pid)
    if p is None or pid == "me":
        return None
    me = graph.people.get("me")
    overlaps = []
    if me:
        for r in p.roles:
            for mine in me.roles:
                if r["org"] != mine["org"]:
                    continue
                start = max(r["started"], mine["started"])
                end = min(r["ended"] or date.max, mine["ended"] or date.max)
                if start <= end:
                    overlaps.append(f"Both at {r['org']}, {start.year}-{end.year if end != date.max else 'now'}")
        for s in p.schools:
            for ms in me.schools:
                if s["school"] == ms["school"]:
                    same_year = s["year"] == ms["year"]
                    overlaps.append(f"{s['school']}" + (f", same year ({s['year']})" if same_year else ""))
    asks = []
    for r in sorted(p.roles, key=lambda x: x["started"], reverse=True):
        if r["symbol"]:
            when = "now" if r["ended"] is None else f"in {_period(r)}"
            asks.append(f"How {r['org']}'s {FUNCTION_LABEL.get(r['function'], r['function'])} side works "
                        f"({when}), and what changed after they joined.")
        elif r["sector"] in SECTOR_LABEL:
            asks.append(f"How {SECTOR_LABEL[r['sector']]} looks from {r['org']}: which companies they rate and why.")
        if len(asks) == 3:
            break
    if any(r["symbol"] and r["ended"] is None for r in p.roles):
        asks.append("Keep to what is public: nothing price-sensitive that has not been announced.")
    return {"id": pid, "name": p.name, "headline": p.headline, "location": p.location, "degree": p.degree,
            "synthetic": p.synthetic, "career": [_role_line(r) for r in sorted(p.roles, key=lambda x: x["started"])],
            "schools": [f"{s['school']}" + (f", {s['degree']}" if s["degree"] else "")
                        + (f" ({s['year']})" if s["year"] else "") for s in p.schools],
            "how": _how(graph, pid), "path": graph.path(pid), "overlaps": overlaps, "what_to_ask": asks}


def expertise(graph: Graph, sector: str | None = None, function: str | None = None) -> list[dict[str, Any]]:
    """Who knows a sector or a function, or both: people matching both first, then the nearest
    (either one), strongest tie first within each."""
    found = []
    for pid, p in graph.people.items():
        if pid == "me" or not graph.path(pid):
            continue
        scored = [(int(sector is not None and r["sector"] == sector)
                   + int(function is not None and r["function"] == function), r) for r in p.roles]
        matches, r = max(scored, key=lambda x: (x[0], x[1]["ended"] is None, x[1]["started"]))
        if matches == 0:
            continue
        partial = sector is not None and function is not None and matches == 1
        why = f"{_role_line(r)}." + (" (Nearest match: one of the two.)" if partial else "")
        found.append((-matches, -graph.tie(pid), p.name, pid, why))
    found.sort()
    return [_answer(graph, pid, why) for _, _, _, pid, why in found[:MAX_ANSWERS]]


def reconnect(conn: psycopg.Connection, investor_id: UUID, graph: Graph,
              today: date | None = None) -> list[dict[str, Any]]:
    """Strong ties gone quiet, with a reason to call now: a recent filing at a company they worked at."""
    today = today or date.today()
    quiet = []
    for e in graph.edges:
        gone_quiet = e["last_contact"] is not None and (today - e["last_contact"]).days > QUIET_AFTER_DAYS
        if e["from"] == "me" and e["strength"] >= 4 and gone_quiet:
            quiet.append(e)
    symbols = sorted({r["symbol"] for e in quiet for r in graph.people[e["to"]].roles if r["symbol"]})
    recent: dict[str, tuple[str, str]] = {}
    if symbols:
        since = datetime.combine(today - timedelta(days=RECENT_FILING_DAYS), datetime.min.time())
        with db.as_role(conn, "finn_api", investor_id):
            for symbol, subject, ts in conn.execute(
                    """select distinct on (symbol) symbol, coalesce(nullif(subject, ''), label), ts
                       from finn.filings where symbol = any(%s) and ts >= %s
                         and coalesce(category, 'unclassified') not in
                             ('unclassified', 'earnings_call', 'investor_meetings', 'postal_ballot', 'agm_egm')
                       order by symbol, ts desc""", [symbols, since]):
                recent[symbol] = (subject, ts.date().isoformat())
    answers = []
    for e in sorted(quiet, key=lambda x: (x["last_contact"], -x["strength"])):
        p = graph.people[e["to"]]
        months = (today - e["last_contact"]).days // 30
        hook = next(((r, recent[r["symbol"]]) for r in p.roles if r["symbol"] in recent), None)
        why = f"Strong tie, last in touch about {months} months ago."
        if hook:
            (r, (subject, day)) = hook
            verb = "work" if r["ended"] is None else "worked"
            why += f" {r['org']} filed '{subject[:90]}' on {day}; they {verb} there."
        answers.append((hook is not None, _answer(graph, e["to"], why)))
    answers.sort(key=lambda a: not a[0])
    return [a for _, a in answers[:MAX_ANSWERS]]


# --- Asking -------------------------------------------------------------------------------------

SECTOR_WORDS = {
    "it services": "it_services", "software": "it_services", "it ": "it_services", "tech services": "it_services",
    "bank": "banking", "nbfc": "lending", "lending": "lending", "gold loan": "lending", "power": "power",
    "energy": "power", "utility": "power", "utilities": "power", "mining": "mining", "iron ore": "mining",
    "capital goods": "capital_goods", "engineering": "capital_goods", "industrial": "capital_goods",
    "turbine": "capital_goods", "cable": "electricals", "wire": "electricals", "electrical": "electricals",
    "electronics": "electronics", "consumer": "consumer", "retail": "consumer", "paint": "consumer",
    "apparel": "consumer", "jewel": "consumer", "auto component": "auto_components", "tyre": "auto_components",
    "tire": "auto_components", "glass": "auto_components", "auto": "auto", "vehicle": "auto", "motorcycle": "auto",
    "pharma": "pharma", "drug": "pharma", "chemical": "chemicals", "fluor": "chemicals",
}
FUNCTION_WORDS = {
    "investor relations": "investor_relations", "finance": "finance", "cfo": "finance", "treasury": "finance",
    "legal": "legal", "compliance": "legal", "governance": "legal", "hr": "hr", "people": "hr", "talent": "hr",
    "strategy": "strategy", "operations": "operations", "plant": "operations", "projects": "operations",
    "risk": "risk", "credit": "risk", "procurement": "supply_chain", "supply chain": "supply_chain",
    "audit": "audit", "technology": "technology", "digital": "technology", "sales": "sales",
    "research": "research", "r&d": "engineering",
}
RECONNECT_WORDS = ("reconnect", "catch up", "back in touch", "gone quiet", "lost touch", "keep warm", "warm")
EXAMPLES = ["Who worked at Tata Power?", "Who can explain Navin Fluorine's new plant?", "Who knows auto components?",
            "Who should I reconnect with?", "Who knows legal and compliance in banking?"]


def _find_company(conn: psycopg.Connection, investor_id: UUID, q: str) -> str | None:
    text = f" {q.lower()} "
    for symbol, (name, _) in COMPANIES.items():
        short = name.lower().replace(" india", "").replace(" international", "")
        if re.search(rf"(?<![a-z0-9]){re.escape(symbol.lower())}(?![a-z0-9])", text) or short in text:
            return symbol
    for token in re.findall(r"[A-Za-z0-9&-]{2,20}", q):
        if token.upper() == token and len(token) >= 2:
            with db.as_role(conn, "finn_api", investor_id):
                if conn.execute("select 1 from finn.companies where symbol = %s", [token]).fetchone():
                    return token
    return None


def ask(conn: psycopg.Connection, investor_id: UUID, graph: Graph, q: str, today: date | None = None) -> dict[str, Any]:
    """Read a short question and answer it with the matching question type."""
    q = " ".join(q.split())[:200]
    low = f" {q.lower()} "
    if any(w in low for w in RECONNECT_WORDS):
        return {"question": q, "kind": "reconnect", "title": "Strong ties worth a call now",
                "answers": reconnect(conn, investor_id, graph, today)}
    for pid, p in graph.people.items():
        if pid != "me" and p.name.lower() in low:
            return {"question": q, "kind": "person", "title": p.name, "person": person(graph, pid), "answers": []}
    symbol = _find_company(conn, investor_id, q)
    if symbol:
        category = next((c for word, c in (("result", "results"), ("quarter", "results"), ("plant", "capex"),
                                           ("capacity", "capex"), ("project", "capex"), ("acqui", "M&A"),
                                           ("merger", "M&A"), ("deal", "M&A"), ("appoint", "management_change"),
                                           ("director", "management_change"), ("ceo", "management_change"),
                                           ("cfo", "management_change"), ("resign", "management_change"),
                                           ("case", "litigation"), ("court", "litigation"), ("fema", "governance"),
                                           ("pledge", "pledging")) if word in low), None)
        found = company(graph, symbol, category, today)
        return {"question": q, "kind": "company", "title": f"People who can explain {found['company']}",
                "company": found, "answers": found["best_placed"]}
    function = next((f for word, f in FUNCTION_WORDS.items() if word in low), None)
    sector = next((s for word, s in SECTOR_WORDS.items() if word in low), None)
    if sector or function:
        parts = (FUNCTION_LABEL.get(function or "", ""), SECTOR_LABEL.get(sector or "", ""))
        label = " in ".join(x for x in parts if x)
        return {"question": q, "kind": "expertise", "title": f"Who knows {label}",
                "answers": expertise(graph, sector, function)}
    return {"question": q, "kind": "help", "title": "Ask about a company, a person, a sector or a function",
            "answers": [], "examples": EXAMPLES}


# --- In the brief --------------------------------------------------------------------------------

def enrich(conn: psycopg.Connection, investor_id: UUID, digest: dict[str, Any], today: date | None = None,
           per_item: int = 2) -> dict[str, Any]:
    """Add `who_to_call` to every item of the digest (the full edition only; the caller checks the
    deployment). Does nothing when the investor has the network switched off."""
    graph = load_graph(conn, investor_id)
    if graph is None:
        return digest
    for item in [*digest.get("attention", []), *digest.get("worth", [])]:
        picks = explain(graph, item["symbol"], item.get("category"), limit=per_item, today=today)
        item["who_to_call"] = [{k: a[k] for k in ("person_id", "name", "why", "degree", "via", "caution")}
                               for a in picks]
    return digest
