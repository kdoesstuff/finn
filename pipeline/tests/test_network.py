"""The synthetic network (task G1), its privacy (G2) and the questions it answers (G4)."""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from psycopg import sql

from finn import db, network, network_seed
from tests.dbtools import INVESTOR_A, INVESTOR_B, denied, select_from

PIPELINE = Path(network.__file__).resolve().parent
NETWORK_TABLES = ("network_people", "network_roles", "network_schools", "network_edges")
TODAY = date(2026, 11, 15)


# --- G1: the generator ----------------------------------------------------------------------------

def test_the_generator_is_deterministic_and_the_committed_files_are_its_output():
    a, b = network_seed.generate(), network_seed.generate()
    assert a == b
    committed = json.loads(network_seed.OUT_JSON.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(a))
    assert network_seed.OUT_CSV.read_text(encoding="utf-8") == network_seed.connections_csv(a)


def test_about_150_fictional_people_all_labelled_synthetic():
    data = network_seed.generate()
    people = data["people"]
    assert 140 <= len(people) <= 160
    assert data["synthetic"] and all(p["synthetic"] for p in people)
    names = [f"{p['first_name']} {p['last_name']}" for p in people]
    assert len(set(names)) == len(names)
    assert not set(names) & network_seed.BLOCKLIST_NAMES
    assert not {p["last_name"] for p in people} & network_seed.BLOCKLIST_SURNAMES
    orgs = {r["org"] for p in people for r in p["roles"]}
    companies = {name for name, _ in network_seed.COMPANIES.values()}
    assert orgs <= companies | network_seed.FICTIONAL  # real companies only as employers; the rest invented


def test_careers_are_in_order_and_nobody_starts_at_the_top():
    for p in network_seed.generate()["people"]:
        for r in p["roles"]:
            assert r["ended"] is None or r["ended"] >= r["started"], (p["id"], r)
        first = p["roles"][0]
        graduated = max((s["year"] for s in p["schools"] if s["year"]), default=0)
        if first["symbol"] and int(first["started"][:4]) - graduated <= 1 and first["title"].startswith("Head"):
            raise AssertionError(f"{p['id']} starts as {first['title']} straight out of college")


def test_the_network_overlaps_every_covered_company():
    data = network_seed.generate()
    for symbol in network_seed.COMPANIES:
        at = [p for p in data["people"] if any(r["symbol"] == symbol for r in p["roles"])]
        assert len(at) >= 3, symbol
    degrees = {p["degree"] for p in data["people"]}
    assert degrees == {1, 2}
    ids = {p["id"] for p in data["people"]} | {"me"}
    assert all(e["from"] in ids and e["to"] in ids for e in data["edges"])
    second = {p["id"] for p in data["people"] if p["degree"] == 2}
    assert all(any(e["to"] == pid and e["from"] != "me" for e in data["edges"]) for pid in second)


def test_connections_csv_is_linkedins_format_for_first_degree_contacts():
    text = network_seed.connections_csv(network_seed.generate())
    lines = text.splitlines()
    assert lines[3] == "First Name,Last Name,URL,Email Address,Company,Position,Connected On"
    assert len(lines) - 4 == sum(1 for p in network_seed.generate()["people"] if p["degree"] == 1)


def test_network_data_never_reaches_a_model():
    """No pipeline module both reads the network and imports the model router."""
    for path in PIPELINE.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "network_" not in source and "finn.network" not in source and "from . import network" not in source:
            continue
        imported = {n.module or "" for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)}
        imported |= {a.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Import) for a in n.names}
        names = {a.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert "llm" not in names and not any(m.endswith("llm") for m in imported), path


# --- G2: loading and privacy ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def loaded(admin):
    with admin.transaction():
        admin.execute("update finn.investors set network_enabled = true where id = any(%s)", [[INVESTOR_A, INVESTOR_B]])
    counts = network.load_network(admin, INVESTOR_A)
    return counts


def test_loading_is_idempotent(admin, loaded):
    again = network.load_network(admin, INVESTOR_A)
    assert again == loaded and loaded["people"] == 150
    (n,), = admin.execute("select count(*) from finn.network_people where investor_id = %s", [INVESTOR_A]).fetchall()
    assert n == 151  # the people plus the investor's own profile


def test_a_second_investor_sees_nothing_of_the_first(admin, loaded):
    graph_a = network.load_graph(admin, INVESTOR_A)
    graph_b = network.load_graph(admin, INVESTOR_B)
    assert graph_a is not None and len(graph_a.people) == 151 and len(graph_a.edges) == 150
    assert graph_b is not None and graph_b.people == {} and graph_b.edges == []
    with db.as_role(admin, "finn_api"):  # no investor in scope: nothing at all
        for table in NETWORK_TABLES:
            assert admin.execute(select_from(table)).fetchall() == []


def test_the_api_role_only_reads_and_ingest_never_sees_the_network(admin, loaded):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        assert denied(admin, """insert into finn.network_people (investor_id, id, first_name, last_name, degree)
                                values (%s, 'p999', 'X', 'Y', 1)""", [INVESTOR_A])
        assert denied(admin, "delete from finn.network_edges")
        assert denied(admin, "update finn.network_people set headline = 'x'")
    with db.as_role(admin, "finn_ingest"):
        for table in NETWORK_TABLES:
            assert denied(admin, select_from(table))


def test_a_switched_off_network_is_not_read(admin, loaded):
    with admin.transaction():
        admin.execute("update finn.investors set network_enabled = false where id = %s", [INVESTOR_A])
    try:
        assert network.load_graph(admin, INVESTOR_A) is None
        digest = {"attention": [{"symbol": "TATAPOWER", "category": "capex"}], "worth": []}
        assert "who_to_call" not in network.enrich(admin, INVESTOR_A, digest)["attention"][0]
    finally:
        with admin.transaction():
            admin.execute("update finn.investors set network_enabled = true where id = %s", [INVESTOR_A])


def test_deleting_the_investor_deletes_the_network(admin, loaded):
    gone = UUID("0c0c0c0c-0000-4000-8000-00000000000c")
    with admin.transaction():
        admin.execute("insert into finn.investors (id, display_name, network_enabled) values (%s, 'C', true)", [gone])
    network.load_network(admin, gone)
    with admin.transaction():
        admin.execute("delete from finn.investors where id = %s", [gone])
    for table in NETWORK_TABLES:
        query = sql.SQL("select count(*) from finn.{} where investor_id = %s").format(sql.Identifier(table))
        (n,), = admin.execute(query, [gone]).fetchall()
        assert n == 0, table


# --- G4: questions --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def graph(admin, loaded):
    g = network.load_graph(admin, INVESTOR_A)
    assert g is not None
    return g


def test_who_can_explain_an_event_ranks_insiders_first_with_reasons(graph):
    answers = network.explain(graph, "TATAPOWER", "capex", today=TODAY)
    assert answers and len(answers) <= network.MAX_ANSWERS
    top = answers[0]
    assert "Tata Power" in top["why"] and top["path"]
    for a in answers:
        assert a["why"].endswith(".") and a["how"]
        if a["degree"] == 2:
            assert a["via"] and len(a["path"]) == 2
    insiders = [a for a in answers if "Tata Power" in a["why"].split(":")[0]]
    assert insiders and all(("since" not in a["why"].split(":")[0]) or a["caution"] for a in insiders)


def test_company_lists_who_worked_there_and_marks_current_employees(graph):
    found = network.company(graph, "TCS", today=TODAY)
    assert found["company"] and found["synthetic"] is True
    assert found["you_worked_there"] == ["Software Engineer, Tata Consultancy Services (2006-2008)"]
    now = [a for a in found["worked_there"] if a["why"].startswith("Works there now")]
    before = [a for a in found["worked_there"] if a["why"].startswith("Worked there")]
    assert now and before
    assert all(a["caution"] == network.CAUTION for a in now) and all(a["caution"] is None for a in before)


def test_person_diligence_has_career_overlaps_path_and_questions(graph):
    classmate = next(pid for pid, p in graph.people.items()
                     if any(s["school"] == "IIM Ahmedabad" for s in p.schools) and p.degree == 1)
    found = network.person(graph, classmate)
    assert found is not None and found["career"] and found["what_to_ask"]
    assert "IIM Ahmedabad, same year (2010)" in found["overlaps"]
    assert len(found["path"]) == 1 and found["path"][0]["from"] == "you"
    second = next(pid for pid, p in graph.people.items() if p.degree == 2)
    found_second = network.person(graph, second)
    assert found_second is not None and len(found_second["path"]) == 2
    assert network.person(graph, "me") is None and network.person(graph, "p999") is None


def test_expertise_by_sector_and_function(graph):
    auto = network.expertise(graph, sector="auto_components")
    assert auto and all("(" in a["why"] for a in auto)
    legal = network.expertise(graph, function="legal")
    assert legal


def test_reconnect_finds_strong_ties_gone_quiet(admin, graph):
    found = network.reconnect(admin, INVESTOR_A, graph, today=TODAY)
    assert found
    assert all("Strong tie, last in touch about" in a["why"] for a in found)


@pytest.mark.parametrize("q, kind", [
    ("Who worked at Tata Power?", "company"),
    ("who can explain NAVINFLUOR's new plant", "company"),
    ("Who knows auto components?", "expertise"),
    ("Who knows legal and compliance in banking?", "expertise"),
    ("Who should I reconnect with?", "reconnect"),
    ("what is the weather", "help"),
])
def test_ask_answers_each_question_shape(admin, graph, q, kind):
    answer = network.ask(admin, INVESTOR_A, graph, q, today=TODAY)
    assert answer["kind"] == kind
    if kind == "help":
        assert answer["examples"]
    elif kind != "person":
        assert answer["answers"]


def test_ask_finds_a_person_by_name(admin, graph):
    pid, p = next((pid, p) for pid, p in graph.people.items() if p.degree == 2)
    answer = network.ask(admin, INVESTOR_A, graph, f"Tell me about {p.name}", today=TODAY)
    assert answer["kind"] == "person" and answer["person"]["id"] == pid


def test_enrich_adds_who_to_call_to_every_item(admin, loaded):
    digest = {"attention": [{"symbol": "TATAPOWER", "category": "capex"},
                            {"symbol": "ABB", "category": "management_change"}],
              "worth": [{"symbol": "NOTCOVERED", "category": "results"}]}
    out = network.enrich(admin, INVESTOR_A, digest, today=TODAY)
    for item in out["attention"]:
        assert 1 <= len(item["who_to_call"]) <= 2
        assert set(item["who_to_call"][0]) == {"person_id", "name", "why", "degree", "via", "caution"}
    assert out["worth"][0]["who_to_call"] == []
