"""The demo investor's network: about 150 fictional people, generated from a fixed seed.

Everything here is synthetic and labelled so. The people are invented (first and last names drawn
from lists and combined; no generated name is a well-known person, and a test checks the blocklist).
The organisations are either the real listed companies FINN covers (public companies, named as
employers only) or clearly fictional firms. No fact about a real person is stated or implied: a
person in the network is never matched to anyone named in a filing (that would need entity
resolution with evidence, task G3); the network says only who worked where and how the investor
knows them.

    python -m finn.network_seed            # rewrites db/seed/network.json and db/seed/Connections.csv

The generator is deterministic: the same seed writes the same files, byte for byte.
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import config

SEED_VALUE = 20261115
OUT_JSON = config.ROOT / "db" / "seed" / "network.json"
OUT_CSV = config.ROOT / "db" / "seed" / "Connections.csv"

# The covered companies (db/seed/demo.json): real listed companies, used only as employers.
COMPANIES: dict[str, tuple[str, str]] = {
    "TCS": ("Tata Consultancy Services", "it_services"),
    "PERSISTENT": ("Persistent Systems", "it_services"),
    "HDFCBANK": ("HDFC Bank", "banking"),
    "BAJFINANCE": ("Bajaj Finance", "lending"),
    "MANAPPURAM": ("Manappuram Finance", "lending"),
    "TATAPOWER": ("Tata Power", "power"),
    "NMDC": ("NMDC", "mining"),
    "ABB": ("ABB India", "capital_goods"),
    "LT": ("Larsen & Toubro", "capital_goods"),
    "TRITURBINE": ("Triveni Turbine", "capital_goods"),
    "ELGIEQUIP": ("Elgi Equipments", "capital_goods"),
    "POLYCAB": ("Polycab India", "electricals"),
    "DIXON": ("Dixon Technologies", "electronics"),
    "ASIANPAINT": ("Asian Paints", "consumer"),
    "PAGEIND": ("Page Industries", "consumer"),
    "KALYANKJIL": ("Kalyan Jewellers", "consumer"),
    "EICHERMOT": ("Eicher Motors", "auto"),
    "MRF": ("MRF", "auto_components"),
    "ASAHIINDIA": ("Asahi India Glass", "auto_components"),
    "NATCOPHARM": ("Natco Pharma", "pharma"),
    "NAVINFLUOR": ("Navin Fluorine International", "chemicals"),
}

SECTOR_LABEL = {
    "it_services": "IT services", "banking": "banking", "lending": "lending (NBFCs)", "power": "power",
    "mining": "mining", "capital_goods": "capital goods", "electricals": "electricals",
    "electronics": "electronics manufacturing", "consumer": "consumer brands", "auto": "automobiles",
    "auto_components": "auto components", "pharma": "pharmaceuticals", "chemicals": "speciality chemicals",
}

# Sectors whose businesses meet in one value chain (said as a sector link, never as a claim that one
# named company supplies another).
VALUE_CHAIN = {
    frozenset({"auto", "auto_components"}): "the auto value chain (vehicle makers and their component makers)",
    frozenset({"power", "capital_goods"}): "the power equipment chain (utilities and the makers of their equipment)",
    frozenset({"power", "electricals"}): "the power distribution chain (utilities and cable makers)",
    frozenset({"capital_goods", "electricals"}): "industrial electrification",
    frozenset({"pharma", "chemicals"}): "the pharma supply chain (drug makers and chemical intermediates)",
    frozenset({"banking", "lending"}): "lending",
    frozenset({"electronics", "electricals"}): "electrical and electronics manufacturing",
}

# Fictional firms. Every name here is invented for this demo.
FUNDS = ["Saltpan Capital", "Kestrel Lane Advisors", "Brightwater Equity Partners", "Sahyadri Growth Fund",
         "Coromandel Research", "Anchorage Securities"]
AUDITORS = ["Ledgerline Assurance LLP", "Northgate Audit Partners", "Sterling Ledger & Co"]
CONSULTANCIES = ["Tamarind Strategy Group", "Quarry Point Consulting", "Banyan Chambers (law)"]
FICTIONAL = set(FUNDS + AUDITORS + CONSULTANCIES)

FIRST = ["Aarav", "Ishaan", "Kabir", "Vihaan", "Advait", "Reyansh", "Arnav", "Dhruv", "Siddhant", "Pranav",
         "Tanmay", "Nikhil", "Rohan", "Varun", "Akshay", "Harsh", "Omkar", "Parth", "Raghav", "Shaurya",
         "Ved", "Neel", "Ritvik", "Ananya", "Diya", "Isha", "Kavya", "Meera", "Nandini", "Riya", "Saanvi",
         "Tara", "Aditi", "Bhavna", "Charu", "Devika", "Gauri", "Ira", "Jhanvi", "Lavanya", "Mrinal",
         "Naina", "Pallavi", "Radhika", "Sanjana", "Trisha", "Vidya", "Zoya", "Farhan", "Imran"]
LAST = ["Achrekar", "Bhonsale", "Chitnis", "Dhavale", "Ekbote", "Gadgil", "Hiremath", "Inamdar", "Joglekar",
        "Karandikar", "Lele", "Mahajani", "Nadkarni", "Paranjpe", "Rajadhyaksha", "Sathaye", "Upasani",
        "Wagle", "Barve", "Deodhar", "Godbole", "Kelkar", "Limaye", "Phadke", "Sohoni", "Anantharaman",
        "Duraiswamy", "Ganapathy", "Kumaraswamy", "Thyagarajan", "Seshadri", "Bhattacharjee", "Dasgupta",
        "Sengupta", "Chadha", "Dhillon", "Grewal", "Talwar", "Wadhwa", "Kapadia", "Contractor", "Engineer",
        "Lokhandwala", "Merchant", "Pochkhanawala", "Rangnekar", "Vartak", "Zaveri", "Kamath", "Shenoy"]

# Well-known business people (including people named in the covered companies' recent filings): no
# generated name may equal one, and no generated surname may be one of these families' names.
BLOCKLIST_NAMES = {
    "Ratan Tata", "Mukesh Ambani", "Kumar Mangalam Birla", "Azim Premji", "Nandan Nilekani",
    "Narayana Murthy", "Gautam Adani", "Uday Kotak", "Anand Mahindra", "Rahul Bajaj", "Sanjiv Bajaj",
    "Adi Godrej", "Shiv Nadar", "Lakshmi Mittal", "Sajjan Jindal", "Leo Puri", "Sanjay Kumar Banga",
    "N V Sivakumar", "V Srinivasa Rangan", "Damodar Padhi", "Sashidhar Jagdishan", "K Krithivasan",
    "Siddhartha Lal", "Praveer Sinha", "S N Subrahmanyan", "Amit Syngle", "Inder Jaisinghani",
    "Sunil Vachani", "V P Nandakumar", "T S Kalyanaraman", "Sanjay Labroo", "Vishal Mafatlal",
}
BLOCKLIST_SURNAMES = {
    "Tata", "Ambani", "Birla", "Premji", "Nilekani", "Murthy", "Adani", "Kotak", "Mahindra", "Bajaj",
    "Godrej", "Nadar", "Mittal", "Jindal", "Puri", "Banga", "Sivakumar", "Rangan", "Padhi", "Jagdishan",
    "Krithivasan", "Lal", "Sinha", "Subrahmanyan", "Syngle", "Jaisinghani", "Vachani", "Nandakumar",
    "Kalyanaraman", "Labroo", "Mafatlal", "Genomal", "Nannapaneni", "Mammen", "Kalyani",
}

FUNCTIONS = {
    "finance": ["Deputy CFO", "Head of Treasury", "Financial Controller", "Finance Manager", "Head of FP&A"],
    "investor_relations": ["Head of Investor Relations", "Investor Relations Manager"],
    "strategy": ["Head of Strategy", "Strategy Manager", "Chief of Staff to the MD"],
    "operations": ["Plant Head", "Head of Operations", "Operations Manager", "Head of Projects"],
    "engineering": ["Chief Engineer", "Engineering Manager", "Head of R&D"],
    "sales": ["Head of Sales", "Regional Sales Head", "Key Accounts Lead"],
    "legal": ["General Counsel", "Head of Compliance", "Company Secretary's office, Senior Manager"],
    "hr": ["Head of HR", "HR Business Partner"],
    "risk": ["Chief Risk Officer's office, Senior Manager", "Head of Credit"],
    "technology": ["Head of Digital", "Engineering Director"],
    "supply_chain": ["Head of Procurement", "Supply Chain Manager"],
}

# First titles, for the years just after college: nobody starts as a head of anything.
JUNIOR = {
    "finance": "Finance Manager", "investor_relations": "Investor Relations Associate",
    "strategy": "Strategy Associate", "operations": "Production Engineer", "engineering": "Graduate Engineer",
    "sales": "Area Sales Manager", "legal": "Legal Associate", "hr": "HR Associate", "risk": "Credit Analyst",
    "technology": "Software Engineer", "supply_chain": "Purchase Engineer",
}

# Which functions can best explain which kind of event (digest categories, finn.taxonomy).
EXPLAINS = {
    "results": ("finance", "investor_relations", "strategy"),
    "management_change": ("hr", "legal", "strategy", "finance"),
    "M&A": ("strategy", "finance", "legal"),
    "capex": ("operations", "engineering", "strategy"),
    "fund_raise": ("finance", "strategy"),
    "credit_rating": ("finance", "risk"),
    "litigation": ("legal",),
    "governance": ("legal", "finance"),
    "pledging": ("finance", "legal"),
    "insider_trading": ("legal",),
}


@dataclass(frozen=True)
class Role:
    org: str
    symbol: str | None
    sector: str
    function: str
    title: str
    started: date
    ended: date | None

    def as_json(self) -> dict[str, Any]:
        return {"org": self.org, "symbol": self.symbol, "sector": self.sector, "function": self.function,
                "title": self.title, "started": self.started.isoformat(),
                "ended": self.ended.isoformat() if self.ended else None}


def _ym(year: int, month: int) -> date:
    return date(year, month, 1)


class _Gen:
    def __init__(self, seed: int = SEED_VALUE) -> None:
        self.rng = random.Random(seed)  # noqa: S311 - a reproducible fake dataset, nothing secret
        self.used: set[str] = set()
        self.people: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []

    def name(self) -> tuple[str, str]:
        for _ in range(10_000):
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            full = f"{first} {last}"
            if full not in self.used and full not in BLOCKLIST_NAMES and last not in BLOCKLIST_SURNAMES:
                self.used.add(full)
                return first, last
        raise RuntimeError("ran out of fictional names")

    def title(self, function: str) -> str:
        return self.rng.choice(FUNCTIONS[function])

    def company_role(self, symbol: str, function: str, start: int, end: int | None) -> Role:
        org, sector = COMPANIES[symbol]
        return Role(org, symbol, sector, function, self.title(function), _ym(start, self.rng.randint(1, 12)),
                    _ym(end, self.rng.randint(1, 12)) if end else None)

    def career_at(self, symbol: str, function: str, start: int, end: int | None, graduated: int) -> list[Role]:
        """A stint at one company: a first title for the early years, then a senior one, if it began
        within four years of graduating and lasted long enough to be promoted."""
        if start - graduated > 4 or (end is not None and end - start < 6):
            return [self.company_role(symbol, function, start, end)]
        org, sector = COMPANIES[symbol]
        promoted = start + self.rng.randint(5, 8)
        if end is not None:
            promoted = min(promoted, end - 1)
        junior = Role(org, symbol, sector, function, JUNIOR[function], _ym(start, self.rng.randint(6, 9)),
                      _ym(promoted, 3))
        senior = self.rng.choice([t for t in FUNCTIONS[function] if t != JUNIOR[function]])
        return [junior, Role(org, symbol, sector, function, senior, _ym(promoted, 4),
                             _ym(end, self.rng.randint(4, 12)) if end else None)]

    def other_role(self, org: str, sector: str, function: str, title: str, start: int, end: int | None) -> Role:
        return Role(org, None, sector, function, title, _ym(start, self.rng.randint(1, 12)),
                    _ym(end, self.rng.randint(1, 12)) if end else None)

    def person(self, roles: list[Role], schools: list[dict[str, Any]], degree: int, location: str = "") -> str:
        pid = f"p{len(self.people) + 1:03d}"
        first, last = self.name()
        current = next((r for r in reversed(roles) if r.ended is None), roles[-1])
        headline = f"{current.title}, {current.org}"
        if current.ended is not None:
            headline = "Formerly " + headline
        self.people.append({
            "id": pid, "first_name": first, "last_name": last, "headline": headline,
            "location": location or self.rng.choice(["Mumbai", "Pune", "Bengaluru", "Chennai", "Gurugram",
                                                       "Hyderabad", "Kolkata", "Ahmedabad", "Coimbatore"]),
            "degree": degree, "synthetic": True,
            "roles": [r.as_json() for r in sorted(roles, key=lambda r: r.started)],
            "schools": schools,
        })
        return pid

    def edge(self, src: str, dst: str, kind: str, strength: int, since: date, last_contact: date | None,
             context: str) -> None:
        self.edges.append({"from": src, "to": dst, "kind": kind, "strength": strength, "since": since.isoformat(),
                           "last_contact": last_contact.isoformat() if last_contact else None, "context": context})


def _last_contact(rng: random.Random, strength: int) -> date:
    # Strong ties are usually recent; a few strong ties have gone quiet (the "reconnect" cases).
    recent = strength >= 4 and rng.random() > 0.3
    months_ago = rng.choice([1, 2, 3, 5, 8]) if recent else rng.choice([9, 14, 20, 26, 34])
    year, month = 2026, 11 - months_ago
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, rng.randint(1, 28))


PERSONA = {
    "id": "me", "first_name": "Demo", "last_name": "investor", "degree": 0, "synthetic": True,
    "headline": "Portfolio Manager, Saltpan Capital", "location": "Mumbai",
    "roles": [
        Role("Tata Consultancy Services", "TCS", "it_services", "technology", "Software Engineer",
             date(2006, 7, 1), date(2008, 5, 1)).as_json(),
        Role("Anchorage Securities", None, "finance", "research", "Equity Research Analyst",
             date(2010, 6, 1), date(2017, 3, 1)).as_json(),
        Role("Saltpan Capital", None, "finance", "research", "Portfolio Manager", date(2017, 4, 1), None).as_json(),
    ],
    "schools": [{"school": "IIT Delhi", "degree": "B.Tech", "year": 2006},
                {"school": "IIM Ahmedabad", "degree": "PGP", "year": 2010}],
}


def generate(seed: int = SEED_VALUE) -> dict[str, Any]:
    g = _Gen(seed)
    rng = g.rng
    symbols = list(COMPANIES)
    sectors = sorted({s for _, s in COMPANIES.values()})
    iitd = [{"school": "IIT Delhi", "degree": "B.Tech", "year": 2006}]
    iima = [{"school": "IIM Ahmedabad", "degree": "PGP", "year": 2010}]
    first_degree: list[str] = []

    # Saltpan Capital colleagues (worked together, strong).
    for function in ("research", "research", "research", "finance", "legal", "research"):
        title = {"research": "Analyst", "finance": "Head of Operations", "legal": "Compliance Officer"}[function]
        start = rng.randint(2017, 2022)
        pid = g.person([g.other_role("Saltpan Capital", rng.choice(sectors), function, title, start, None)],
                       [{"school": rng.choice(["NMIMS", "SRCC", "IIM Lucknow", "XLRI"]), "degree": "MBA",
                         "year": start - rng.randint(1, 4)}], 1, "Mumbai")
        g.edge("me", pid, "worked_together", rng.randint(4, 5), _ym(start, 6), _last_contact(rng, 5),
               "Colleague at Saltpan Capital")
        first_degree.append(pid)

    # Anchorage Securities: sell-side colleagues, many since moved into the companies they covered.
    for i in range(15):
        sector = sectors[i % len(sectors)]
        in_sector = [s for s in symbols if COMPANIES[s][1] == sector]
        start = rng.randint(2009, 2013)
        roles = [g.other_role("Anchorage Securities", sector, "research", "Research Analyst", start,
                              rng.randint(2015, 2018))]
        last_end = int(roles[-1].ended.year) if roles[-1].ended else 2018
        if in_sector and rng.random() < 0.7:
            function = rng.choice(["investor_relations", "strategy", "finance"])
            roles.append(g.company_role(rng.choice(in_sector), function, last_end,
                                        None if rng.random() < 0.7 else rng.randint(last_end + 2, 2025)))
        else:
            roles.append(g.other_role(rng.choice(FUNDS[1:5]), sector, "research", "Fund Manager", last_end, None))
        pid = g.person(roles, [{"school": rng.choice(["IIM Bangalore", "IIM Calcutta", "FMS Delhi", "SPJIMR"]),
                                "degree": "MBA", "year": start - 1}], 1)
        strength = rng.randint(2, 5)
        g.edge("me", pid, "worked_together", strength, _ym(max(start, 2010), 7), _last_contact(rng, strength),
               f"Colleague at Anchorage Securities ({SECTOR_LABEL[sector]} desk)")
        first_degree.append(pid)

    # TCS, the investor's first job.
    for _ in range(6):
        start = rng.randint(2005, 2007)
        roles = g.career_at("TCS", "technology", start, rng.choice([None, 2012, 2015]), start)
        if roles[-1].ended:
            roles.append(g.company_role("PERSISTENT", rng.choice(["technology", "sales", "strategy"]),
                                        roles[-1].ended.year, None))
        pid = g.person(roles, iitd if rng.random() < 0.3 else [{"school": "NIT Trichy", "degree": "B.E.",
                                                               "year": start}], 1)
        strength = rng.randint(1, 4)
        g.edge("me", pid, "worked_together", strength, _ym(2006, 9), _last_contact(rng, strength),
               "Colleague at TCS, 2006-08")
        first_degree.append(pid)

    # IIM Ahmedabad classmates (PGP 2010): careers across the covered companies.
    for i in range(22):
        symbol = symbols[i % len(symbols)]
        function = rng.choice(["finance", "strategy", "sales", "operations", "hr", "legal", "risk"])
        if COMPANIES[symbol][1] in ("banking", "lending") and function in ("operations",):
            function = "risk"
        roles = []
        if rng.random() < 0.5:
            roles.append(g.other_role(rng.choice(CONSULTANCIES[:2]), COMPANIES[symbol][1], "strategy",
                                      "Consultant", 2010, rng.randint(2012, 2015)))
        begin = roles[-1].ended.year if roles and roles[-1].ended else 2010
        end = None if rng.random() < 0.65 else rng.randint(begin + 3, 2026)
        roles += g.career_at(symbol, function, begin, end, 2010)
        if end:
            peers = [s for s in symbols if COMPANIES[s][1] == COMPANIES[symbol][1] and s != symbol]
            other = rng.choice(peers or FUNDS[1:3])
            if other in COMPANIES:
                roles.append(g.company_role(other, function, end, None))
            else:
                roles.append(g.other_role(other, COMPANIES[symbol][1], "research", "Partner", end, None))
        pid = g.person(roles, iima, 1)
        strength = rng.randint(2, 5)
        g.edge("me", pid, "classmate", strength, date(2008, 6, 15), _last_contact(rng, strength),
               "Classmate, IIM Ahmedabad (PGP 2010)")
        first_degree.append(pid)

    # IIT Delhi batchmates (2006): engineers in industry.
    engineering = ["ABB", "LT", "TRITURBINE", "ELGIEQUIP", "DIXON", "TATAPOWER", "NMDC", "POLYCAB", "EICHERMOT",
                   "ASAHIINDIA", "NAVINFLUOR", "MRF"]
    for symbol in engineering:
        roles = g.career_at(symbol, rng.choice(["engineering", "operations", "supply_chain"]), 2006,
                            None if rng.random() < 0.6 else rng.randint(2014, 2024), 2006)
        if roles[-1].ended:
            same = [s for s in engineering if COMPANIES[s][1] == COMPANIES[symbol][1] and s != symbol]
            nxt = rng.choice(same) if same else rng.choice(engineering)
            roles.append(g.company_role(nxt, roles[0].function, roles[-1].ended.year, None))
        pid = g.person(roles, iitd, 1)
        strength = rng.randint(1, 5)
        g.edge("me", pid, "classmate", strength, date(2002, 8, 1), _last_contact(rng, strength),
               "Batchmate, IIT Delhi (B.Tech 2006)")
        first_degree.append(pid)

    # Met at conferences and results calls: investor-relations heads, sector experts, auditors.
    for i in range(20):
        if i < 12:
            symbol = symbols[(i * 5) % len(symbols)]
            roles = [g.company_role(symbol, rng.choice(["investor_relations", "finance", "strategy", "legal"]),
                                    rng.randint(2014, 2021), None)]
            name = COMPANIES[symbol][0]
            context = f"Met at {name}{chr(39) if name.endswith('s') else chr(39) + 's'} analyst meets"
        elif i < 17:
            sector = sectors[i % len(sectors)]
            roles = [g.other_role(rng.choice(CONSULTANCIES[:2]), sector, "strategy",
                                  f"Partner, {SECTOR_LABEL[sector]} practice", rng.randint(2012, 2018), None)]
            context = f"Met at an industry conference on {SECTOR_LABEL[sector]}"
        else:
            sector = sectors[(i * 3) % len(sectors)]
            roles = [g.other_role(rng.choice(AUDITORS), sector, "audit", f"Audit Partner, {SECTOR_LABEL[sector]}",
                                  rng.randint(2011, 2017), None)]
            context = "Met at an accounting-standards workshop"
        pid = g.person(roles, [{"school": rng.choice(["ICAI (CA)", "IIM Indore", "Delhi School of Economics",
                                                     "IIT Bombay"]), "degree": "", "year": rng.randint(2000, 2012)}], 1)
        strength = rng.randint(1, 3)
        g.edge("me", pid, "conference", strength, _ym(rng.randint(2016, 2025), rng.randint(1, 12)),
               _last_contact(rng, strength), context)
        first_degree.append(pid)

    # Former clients from the sell-side years: fund managers.
    for _ in range(10):
        sector = rng.choice(sectors)
        roles = [g.other_role(rng.choice(FUNDS[1:5]), sector, "research", "Fund Manager", rng.randint(2008, 2014),
                              None)]
        pid = g.person(roles, [{"school": rng.choice(["IIM Calcutta", "ISB", "JBIMS"]), "degree": "MBA",
                                "year": rng.randint(2004, 2010)}], 1)
        strength = rng.randint(2, 4)
        g.edge("me", pid, "former_client", strength, _ym(rng.randint(2011, 2016), 3), _last_contact(rng, strength),
               "Client of Anchorage Securities' research")
        first_degree.append(pid)

    # Second degree: people at the covered companies whom a first-degree contact worked with.
    contacts_at: dict[str, list[str]] = {}
    for p in g.people:
        for r in p["roles"]:
            if r["symbol"]:
                contacts_at.setdefault(r["symbol"], []).append(p["id"])
    for i in range(59):
        symbol = symbols[i % len(symbols)]
        function = rng.choice(list(FUNCTIONS))
        start = rng.randint(2008, 2020)  # experienced hires: a decade or so after college
        roles = [g.company_role(symbol, function, start, None)]
        school = rng.choice(["IIT Madras", "BITS Pilani", "IIM Kozhikode", "NLSIU", "Symbiosis"])
        pid = g.person(roles, [{"school": school, "degree": "", "year": start - rng.randint(8, 14)}], 2)
        bridge = rng.choice(contacts_at.get(symbol) or first_degree)
        kind = "worked_together" if bridge in contacts_at.get(symbol, []) else "introduced"
        context = (f"Worked together at {COMPANIES[symbol][0]}" if kind == "worked_together"
                   else "Introduced through a mutual contact")
        g.edge(bridge, pid, kind, rng.randint(2, 5), _ym(rng.randint(2012, 2024), 5), None, context)

    return {"synthetic": True, "seed": seed,
            "note": "Synthetic network for FINN's demo investor. Every person is fictional; employers are named only "
                    "as employers; no fact about any real person is stated.",
            "persona": PERSONA, "people": g.people, "edges": g.edges}


def connections_csv(data: dict[str, Any]) -> str:
    """LinkedIn's Connections.csv export format, for the first-degree contacts."""
    out = io.StringIO()
    out.write("Notes:\n\"Synthetic data for FINN's demo. Every person is fictional.\"\n\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"])
    since = {e["to"]: e["since"] for e in data["edges"] if e["from"] == "me"}
    for p in data["people"]:
        if p["degree"] != 1:
            continue
        current = next((r for r in reversed(p["roles"]) if r["ended"] is None), p["roles"][-1])
        on = date.fromisoformat(since[p["id"]]).strftime("%d %b %Y")
        w.writerow([p["first_name"], p["last_name"], "", "", current["org"], current["title"], on])
    return out.getvalue()


def write(path_json: Path = OUT_JSON, path_csv: Path = OUT_CSV, seed: int = SEED_VALUE) -> dict[str, Any]:
    data = generate(seed)
    path_json.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    path_csv.write_text(connections_csv(data), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = write()
    first = sum(1 for p in d["people"] if p["degree"] == 1)
    print(f"{len(d['people'])} people ({first} first degree), {len(d['edges'])} connections -> {OUT_JSON}")
