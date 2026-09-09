"""Writes from the UI. Kept out of the Streamlit module so it can be tested."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from .fields import FieldError, normalize_time, parse_rr

MEDIA_ROOT = Path(__file__).resolve().parent.parent / "media"

EDITABLE = {"trade_date", "entry_time", "trade_type", "planned_rr",
            "outcome", "notes", "psyche", "improvement"}


def _coerce(column: str, value):
    if column == "entry_time":
        return normalize_time(str(value))
    if column == "planned_rr":
        return parse_rr(str(value))
    if column == "trade_date":
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        try:
            return datetime.fromisoformat(str(value)).date().isoformat()
        except ValueError as exc:
            raise FieldError(f"{value!r}: expected a date") from exc
    if column in {"notes", "psyche", "improvement"}:
        text = (value or "") if isinstance(value, str) else value
        return (text.strip() or None) if isinstance(text, str) else None
    return value


def update_field(conn: sqlite3.Connection, trade_id: int, column: str, value) -> None:
    """Update one cell. Raises FieldError on bad input; nothing is written."""
    if column not in EDITABLE:
        raise FieldError(f"{column} is not editable")
    coerced = _coerce(column, value)

    with conn:
        conn.execute(f"UPDATE trade SET {column} = ? WHERE id = ?", (coerced, trade_id))


def set_tags(conn: sqlite3.Connection, trade_id: int, kind: str, names: list[str]) -> None:
    with conn:
        conn.execute(
            """DELETE FROM trade_tag WHERE trade_id = ? AND tag_id IN
               (SELECT id FROM tag WHERE kind = ?)""",
            (trade_id, kind),
        )
        if names:
            placeholders = ",".join("?" * len(names))
            conn.executemany(
                "INSERT OR IGNORE INTO trade_tag (trade_id, tag_id) VALUES (?, ?)",
                [(trade_id, row[0]) for row in conn.execute(
                    f"SELECT id FROM tag WHERE kind = ? AND name IN ({placeholders})",
                    [kind] + names)],
            )


def add_screenshot(
    conn: sqlite3.Connection, trade_id: int, timeframe: str,
    data: bytes, original_name: str,
) -> str:
    """Copy an uploaded image into the media dir and record it."""
    if timeframe not in {"ltf", "htf"}:
        raise FieldError(f"unknown timeframe {timeframe!r}")

    used = [r[0] for r in conn.execute(
        "SELECT ordinal FROM trade_screenshot WHERE trade_id = ? AND timeframe = ?",
        (trade_id, timeframe))]
    ordinal = next((n for n in range(1, 9) if n not in used), None)
    if ordinal is None:
        raise FieldError(f"already 8 {timeframe.upper()} screenshots on this trade")

    today = datetime.now()
    folder = MEDIA_ROOT / f"{today:%Y}" / f"{today:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix.lower() or ".png"
    rel = Path(f"{today:%Y}") / f"{today:%m}" / f"{uuid.uuid4().hex}{suffix}"
    (MEDIA_ROOT / rel).write_bytes(data)

    with conn:
        conn.execute(
            """INSERT INTO trade_screenshot
               (trade_id, timeframe, ordinal, rel_path, original_name, sha256, bytes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, timeframe, ordinal, str(rel), original_name,
             hashlib.sha256(data).hexdigest(), len(data)),
        )
    return str(rel)


def remove_screenshot(conn: sqlite3.Connection, trade_id: int, timeframe: str,
                      ordinal: int) -> None:
    row = conn.execute(
        "SELECT rel_path FROM trade_screenshot WHERE trade_id=? AND timeframe=? AND ordinal=?",
        (trade_id, timeframe, ordinal)).fetchone()
    with conn:
        conn.execute(
            "DELETE FROM trade_screenshot WHERE trade_id=? AND timeframe=? AND ordinal=?",
            (trade_id, timeframe, ordinal))
    # The row is the record; the file is only removed once the row is gone.
    if row:
        (MEDIA_ROOT / row[0]).unlink(missing_ok=True)


def screenshots(conn: sqlite3.Connection, trade_id: int) -> dict[str, list[sqlite3.Row]]:
    out: dict[str, list[sqlite3.Row]] = {"ltf": [], "htf": []}
    for row in conn.execute(
        "SELECT * FROM trade_screenshot WHERE trade_id = ? ORDER BY timeframe, ordinal",
        (trade_id,),
    ):
        out[row["timeframe"]].append(row)
    return out


def create_trade(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    entry_time: str,
    trade_type: str,
    planned_rr: float,
    outcome: str,
    notes: str | None = None,
    psyche: str | None = None,
    improvement: str | None = None,
    tags: dict[str, list[str]] | None = None,
) -> int:
    """Insert a trade and its tags in one transaction.

    Everything is validated before the INSERT, so a bad field leaves no
    half-written row behind.
    """
    values = (
        _coerce("trade_date", trade_date),
        normalize_time(entry_time),
        trade_type,
        parse_rr(str(planned_rr)),
        outcome,
        _coerce("notes", notes),
        _coerce("psyche", psyche),
        _coerce("improvement", improvement),
    )
    with conn:
        cursor = conn.execute(
            """INSERT INTO trade
               (trade_date, entry_time, trade_type, planned_rr, outcome,
                notes, psyche, improvement)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        trade_id = cursor.lastrowid
        for kind, names in (tags or {}).items():
            if not names:
                continue
            placeholders = ",".join("?" * len(names))
            conn.executemany(
                "INSERT OR IGNORE INTO trade_tag (trade_id, tag_id) VALUES (?, ?)",
                [(trade_id, row[0]) for row in conn.execute(
                    f"SELECT id FROM tag WHERE kind = ? AND name IN ({placeholders})",
                    [kind] + list(names))],
            )
    return trade_id


IDENTITY = ("trade_date", "entry_time", "trade_type", "outcome")


def delete_trade(conn: sqlite3.Connection, trade_id: int,
                 *, expect: tuple | None = None) -> dict:
    """Permanently delete a trade and everything hanging off it.

    Three things this gets right, in order of how badly they bite:

    * **Files last.** Image paths are collected inside the transaction but
      unlinked only after it commits, so a rollback can never leave a surviving
      trade whose screenshots were already destroyed.
    * **Children explicitly.** Both dependants declare ON DELETE CASCADE, but
      cascade is runtime behaviour that a single missed `PRAGMA foreign_keys`
      would silently disable, leaving orphans. Deleting them by hand is correct
      either way, and the orphan check before COMMIT proves it.
    * **Identity re-checked.** `trade.id` is a plain INTEGER PRIMARY KEY with no
      AUTOINCREMENT, so ids are reused after a delete. `expect` lets the caller
      pass what its confirmation dialog displayed; if the row no longer matches,
      nothing is deleted.

    Returns counts of what was removed. Raises on any problem, having changed
    nothing.
    """
    with conn:                      # commits on success, rolls back on error
        row = conn.execute(
            f"SELECT {', '.join(IDENTITY)} FROM trade WHERE id = ?", (trade_id,)
        ).fetchone()
        if row is None:
            raise FieldError(f"Trade {trade_id} no longer exists.")

        if expect is not None and tuple(row) != tuple(expect):
            raise FieldError(
                "This row is not the trade the confirmation described — it "
                "changed underneath. Nothing was deleted."
            )

        paths = [r[0] for r in conn.execute(
            "SELECT rel_path FROM trade_screenshot WHERE trade_id = ?", (trade_id,))]

        n_shots = conn.execute(
            "DELETE FROM trade_screenshot WHERE trade_id = ?", (trade_id,)).rowcount
        n_tags = conn.execute(
            "DELETE FROM trade_tag WHERE trade_id = ?", (trade_id,)).rowcount
        conn.execute("DELETE FROM trade WHERE id = ?", (trade_id,))

        orphans = conn.execute(
            """SELECT (SELECT count(*) FROM trade_tag        WHERE trade_id = ?)
                    + (SELECT count(*) FROM trade_screenshot WHERE trade_id = ?)""",
            (trade_id, trade_id)).fetchone()[0]
        if orphans:
            raise RuntimeError(
                f"{orphans} dependent rows survived the delete; rolled back.")

    # Committed. Only now is it safe to touch the filesystem.
    removed, failed = 0, []
    for rel in paths:
        try:
            (MEDIA_ROOT / rel).unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            failed.append(f"{rel}: {exc}")

    return {"tags": n_tags, "screenshots": n_shots,
            "files_removed": removed, "files_failed": failed}
