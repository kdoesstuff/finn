"""Write the demo investor's digest as the web app's saved copy (docs/API.md, "Saved copy").

    python scripts/export_snapshot.py --out ../web/public/snapshot.json [--hours 168]

The file is exactly the /v1/digest JSON, plus "snapshot": true and "generated_at", produced by the
same code the API runs (`finn.digest.digest_payload`) as the API role scoped to the demo investor.
Reads SUPABASE_DB_URL. The file is replaced in one step, so a reader never sees half of it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn import db, seed  # noqa: E402
from finn.digest import IST, MAX_HOURS, MIN_HOURS, digest_payload, iso  # noqa: E402

SNAPSHOT_HOURS = 168  # the contract's saved copy covers seven days


def hours(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number of hours: {text!r}") from None
    if not MIN_HOURS <= value <= MAX_HOURS:
        raise argparse.ArgumentTypeError(f"hours must be from {MIN_HOURS} to {MAX_HOURS}")
    return value


def snapshot(conn: Any, investor_id: UUID, window_hours: int = SNAPSHOT_HOURS,
             now: datetime | None = None) -> dict[str, Any]:
    """The saved copy: the digest, marked as a snapshot, with the time it was made."""
    now = (datetime.now(IST) if now is None else now).astimezone(IST).replace(microsecond=0)
    out: dict[str, Any] = dict(digest_payload(conn, investor_id, window_hours, now=now))
    out["snapshot"] = True
    out["generated_at"] = iso(now)
    return out


def write_atomically(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the demo investor's digest as the web app's saved copy.")
    parser.add_argument("--out", type=Path, required=True, help="where to write the JSON file")
    parser.add_argument("--hours", type=hours, default=SNAPSHOT_HOURS, help="window in hours (default 168)")
    args = parser.parse_args(argv)

    demo = UUID(seed.load()["investor"]["id"])
    conn = db.connect()
    try:
        data = snapshot(conn, demo, args.hours)
    finally:
        conn.close()
    write_atomically(args.out, data)
    print(f"{args.out}: {data['summary']} (window {data['window']['from']} to {data['window']['to']}, "
          f"data as of {data['data_as_of']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
