"""Measure the classifier on a real day's filings.

Reports how many filings each layer handles (content rule, NSE label, fuzzy
label, model), how many summaries say nothing beyond NSE's label, how filings
group into events, how the ranker splits events, and which labels still need a
model. The numbers go in the writeup as the evidence for the model-routing claim.

Run:  python scripts/measure_classifier.py [path to nse_announcements.json]
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn.classify import classify  # noqa: E402
from finn.models import Announcement  # noqa: E402
from finn.rank import ATTENTION, WORTH, build_digest, group_events, score_item  # noqa: E402
from finn.text import own_words  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nse_announcements.json"


def load(path: Path) -> list[Announcement]:
    rows = json.loads(path.read_text())["rows"]
    return [
        Announcement(
            id=r["seq_id"], symbol=r["symbol"], company=r["sm_name"],
            ts=datetime.strptime(r["an_dt"], "%d-%b-%Y %H:%M:%S"), source="NSE",
            label=r["desc"], subject=r.get("attchmntText") or "", url=r.get("attchmntFile") or "",
            file_size=r.get("fileSize") or "",
        )
        for r in rows
    ]


def layer(rule_id: str, needs_model: bool, restates_label: bool = False) -> str:
    if needs_model:
        return "model"
    if rule_id.startswith("nse-desc"):
        return "NSE label"
    if rule_id.endswith("@content"):
        # A text rule that matched a summary which only restates NSE's label is a label match in effect.
        return "text rule on label words" if restates_label else "text rule"
    return "fuzzy label"


def measure(anns: list[Announcement]) -> dict[str, Any]:
    layers: collections.Counter[str] = collections.Counter()
    sections: collections.Counter[str] = collections.Counter()
    cats: collections.Counter[str] = collections.Counter()
    leftovers: collections.Counter[str] = collections.Counter()
    attention_kinds: collections.Counter[str] = collections.Counter()
    for a in anns:
        c = classify(a)
        layers[layer(c.rule_id, c.needs_model, not own_words(a.subject, a.label))] += 1
        cats[c.category] += 1
        if c.needs_model:
            leftovers[a.label] += 1
        _, score, _ = score_item(a, c)
        section = "attention" if score >= ATTENTION else "worth" if score >= WORTH else "routine"
        sections[section] += 1
        if section == "attention":
            attention_kinds[f"{c.category}/{c.subtype or c.role or '-'}"] += 1
    events = group_events(anns)
    digest = build_digest(anns, [])
    restated = sum(1 for a in anns if not own_words(a.subject, a.label))
    return {"total": len(anns), "layers": layers, "sections": sections, "categories": cats,
            "needs_model_by_label": leftovers, "attention_kinds": attention_kinds,
            "restated": restated, "listed": sum(len(e.filings) for e in events), "events": len(events),
            "multi": sum(1 for e in events if len(e.filings) > 1),
            "event_sections": {k: len(digest[k]) for k in ("attention", "worth", "routine")}}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    m = measure(load(path))
    n = m["total"]
    print(f"{n} filings")
    print("By layer:   " + ", ".join(f"{k} {v} ({v / n:.1%})" for k, v in m["layers"].most_common()))
    print(f"Summary only restates NSE's label: {m['restated']} ({m['restated'] / n:.1%})")
    print("By section: " + ", ".join(f"{k} {v} ({v / n:.1%})" for k, v in m["sections"].most_common()))
    print(f"Events: {m['listed']} filings listed ({n - m['listed']} exact re-uploads counted once) "
          f"in {m['events']} events, {m['multi']} with more than one filing")
    e = m["event_sections"]
    print(f"Events by section: attention {e['attention']}, worth {e['worth']}, routine {e['routine']}")
    print("Attention is made of: " + ", ".join(f"{k} {v}" for k, v in m["attention_kinds"].most_common(12)))
    print("Still needs a model: " + ", ".join(f"{k} {v}" for k, v in m["needs_model_by_label"].most_common(10)))


if __name__ == "__main__":
    main()
