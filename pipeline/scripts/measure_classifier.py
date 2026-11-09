"""Measure the classifier on a real day's filings.

Reports how many filings each layer handles (content rule, NSE label, fuzzy
label, model), how the ranker splits them, and which labels still need a model.
The numbers go in the writeup as the evidence for the model-routing claim.

Run:  python scripts/measure_classifier.py [path to nse_announcements.json]
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn.classify import classify  # noqa: E402
from finn.models import Announcement  # noqa: E402
from finn.rank import ATTENTION, WORTH, score_item  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nse_announcements.json"


def load(path: Path) -> list[Announcement]:
    rows = json.loads(path.read_text())["rows"]
    return [
        Announcement(
            id=r["seq_id"], symbol=r["symbol"], company=r["sm_name"],
            ts=datetime.strptime(r["an_dt"], "%d-%b-%Y %H:%M:%S"), source="NSE",
            label=r["desc"], subject=r.get("attchmntText") or "", url=r.get("attchmntFile") or "",
        )
        for r in rows
    ]


def layer(rule_id: str, needs_model: bool) -> str:
    if needs_model:
        return "model"
    if rule_id.startswith("nse-desc"):
        return "NSE label"
    return "text rule" if rule_id.endswith("@content") else "fuzzy label"


def measure(anns: list[Announcement]) -> dict:
    layers, sections, cats, leftovers = (collections.Counter() for _ in range(4))
    attention_kinds = collections.Counter()
    for a in anns:
        c = classify(a)
        layers[layer(c.rule_id, c.needs_model)] += 1
        cats[c.category] += 1
        if c.needs_model:
            leftovers[a.label] += 1
        _, score, _ = score_item(a, c)
        section = "attention" if score >= ATTENTION else "worth" if score >= WORTH else "routine"
        sections[section] += 1
        if section == "attention":
            attention_kinds[f"{c.category}/{c.subtype or c.role or '-'}"] += 1
    return {"total": len(anns), "layers": layers, "sections": sections, "categories": cats,
            "needs_model_by_label": leftovers, "attention_kinds": attention_kinds}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    m = measure(load(path))
    n = m["total"]
    print(f"{n} filings")
    print("By layer:   " + ", ".join(f"{k} {v} ({v / n:.1%})" for k, v in m["layers"].most_common()))
    print("By section: " + ", ".join(f"{k} {v} ({v / n:.1%})" for k, v in m["sections"].most_common()))
    print("Attention is made of: " + ", ".join(f"{k} {v}" for k, v in m["attention_kinds"].most_common(12)))
    print("Still needs a model: " + ", ".join(f"{k} {v}" for k, v in m["needs_model_by_label"].most_common(10)))


if __name__ == "__main__":
    main()
