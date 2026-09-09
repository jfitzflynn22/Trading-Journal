"""Connection handling and schema migration.

The database is a single local file. There is no server, no pool and no ORM --
just sqlite3 with the pragmas that SQLite gets wrong by default.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# journal.db in the project root, unless JOURNAL_DB says otherwise. The override
# is what lets you keep the file outside the checkout (so a git pull can never
# touch it), and what points a public demo at the generated demo database:
#
#     export JOURNAL_DB=~/Documents/my-journal.db
DEFAULT_DB = Path(os.environ.get("JOURNAL_DB") or (ROOT / "journal.db")).expanduser()
SCHEMA_SQL = ROOT / "schema.sql"
SEEDS_SQL = ROOT / "seeds.sql"

SCHEMA_VERSION = 3

# The chip palette. Named here once so a colour is changed in a single place.
PALETTE = {
    "purple":  "#725886",
    "blue":    "#3b6591",
    "green":   "#3f6f59",
    "yellow":  "#907133",
    "orange":  "#8e5835",
    "red":     "#9f4f49",
    "magenta": "#89556e",
    "grey":    "#2c2c2b",
}

# Fixed vocabularies -- not tags, so they live in their own table.
CHIP_COLORS: dict[str, dict[str, str]] = {
    "day": {
        "Monday": "red", "Tuesday": "orange", "Wednesday": "green",
        "Thursday": "blue", "Friday": "purple",
        # Not specified: weekends should not occur, but one bad date exists.
        "Saturday": "grey", "Sunday": "grey",
    },
    "trade_type": {
        "funded": "green", "evaluation": "red", "paper": "blue",
        "forwardtesting": "grey", "backtesting": "grey",
    },
    "outcome": {"win": "green", "loss": "red", "breakeven": "yellow"},
}

# Tag colours by kind. Values absent from the user's list are marked below.
TAG_COLORS: dict[str, dict[str, str]] = {
    "confluence": {
        "po3": "blue",
        "5m FVG": "red", "15m FVG": "red", "30m FVG": "red", "1hr FVG": "red",
        "2hr FVG": "red", "4hr FVG": "red", "Daily FVG": "red",
        "10m FVG": "red",          # pre-existing, used by 1 trade; inferred red
        "LTF SMT": "green", "HTF SMT": "green",
    },
    "dol": {
        "HTF DOL": "green", "Data": "orange", "9:30 open H/L": "blue",
        "LRL": "grey", "Engineered": "grey", "EQX/REQX": "grey", "ERL": "grey",
        "Imbalance": "grey", "Session Liquidity": "grey",
        "PDH/L": "grey", "PWH/L": "grey",
    },
    "entry": {
        "Mech": "grey", "PDI": "grey", "9:30 Judas": "grey",
        "5m Continuation": "grey", "15m+ Continuation": "grey",
        "15s IFVG": "red", "30s IFVG": "red", "1m IFVG": "red", "2m IFVG": "red",
        "3m IFVG": "red", "4m IFVG": "red", "5m IFVG": "red",
        "CISD": "magenta",
    },
}

# Vocabulary entries that did not exist yet, with the family they roll up into.
NEW_TAGS = [
    ("confluence", "Daily FVG", "FVG"),
    ("entry", "15s IFVG", "IFVG"),
    ("entry", "4m IFVG", "IFVG"),
    ("entry", "5m IFVG", "IFVG"),
]

_V3_TABLE = """
CREATE TABLE IF NOT EXISTS chip_color (
  dimension TEXT NOT NULL CHECK (dimension IN ('day','trade_type','outcome')),
  value     TEXT NOT NULL,
  color     TEXT NOT NULL,
  PRIMARY KEY (dimension, value)
) WITHOUT ROWID;
"""


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Add chip colours, and the vocabulary values the palette introduced.

    Colours are stored rather than hard-coded so they can be changed later
    without a release. `tag.color` already existed for exactly this purpose.
    """
    _apply_palette(conn)


def _apply_palette(conn: sqlite3.Connection) -> None:
    """Fill chip_color and tag.color. Idempotent, and called from two places:
    the v2->v3 upgrade and the fresh-database path, which does not run the
    numbered migrations at all."""
    with conn:
        conn.executescript(_V3_TABLE)

        for dimension, mapping in CHIP_COLORS.items():
            conn.executemany(
                "INSERT OR REPLACE INTO chip_color (dimension, value, color) VALUES (?,?,?)",
                [(dimension, value, PALETTE[name]) for value, name in mapping.items()],
            )

        for kind, name, family in NEW_TAGS:
            conn.execute(
                """INSERT INTO tag (kind, name, family, sort_order)
                   SELECT ?, ?, ?, COALESCE((SELECT max(sort_order) FROM tag WHERE kind = ?), 0) + 1
                   WHERE NOT EXISTS (SELECT 1 FROM tag WHERE kind = ? AND name = ?)""",
                (kind, name, family, kind, kind, name),
            )

        for kind, mapping in TAG_COLORS.items():
            for name, colour in mapping.items():
                conn.execute("UPDATE tag SET color = ? WHERE kind = ? AND name = ?",
                             (PALETTE[colour], kind, name))

        # Anything the palette missed keeps a readable default rather than none.
        conn.execute("UPDATE tag SET color = ? WHERE color IS NULL", (PALETTE["grey"],))

# v2: drop trade.be_reason. It appears in a CHECK constraint, and SQLite
# refuses ALTER TABLE DROP COLUMN on a column a constraint references, so the
# table has to be rebuilt. Dropping the table takes its triggers with it, and
# the view has to be recreated because it selects trade.*.
_V2 = """
BEGIN;

DROP VIEW IF EXISTS v_trade;

CREATE TABLE trade_v2 (
  id          INTEGER PRIMARY KEY,
  trade_date  TEXT NOT NULL CHECK (trade_date IS date(trade_date)),
  entry_time  TEXT NOT NULL CHECK (entry_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                   AND entry_time <= '23:59'),
  trade_type  TEXT NOT NULL CHECK (trade_type IN
                ('backtesting','forwardtesting','paper','evaluation','funded')),
  planned_rr  REAL NOT NULL CHECK (planned_rr > 0),
  outcome     TEXT NOT NULL CHECK (outcome IN ('win','loss','breakeven')),
  notes       TEXT,
  psyche      TEXT,
  improvement TEXT,
  external_id TEXT UNIQUE,
  import_batch_id INTEGER REFERENCES import_batch(id) ON DELETE SET NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO trade_v2 (id, trade_date, entry_time, trade_type, planned_rr,
                      outcome, notes, psyche, improvement, external_id,
                      import_batch_id, created_at, updated_at)
SELECT id, trade_date, entry_time, trade_type, planned_rr,
       outcome, notes, psyche, improvement, external_id,
       import_batch_id, created_at, updated_at
FROM trade;

DROP TABLE trade;
ALTER TABLE trade_v2 RENAME TO trade;

CREATE INDEX ix_trade_date      ON trade(trade_date, entry_time, id);
CREATE INDEX ix_trade_type_date ON trade(trade_type, trade_date);
CREATE INDEX ix_trade_created   ON trade(created_at DESC);

CREATE TRIGGER trg_trade_touch AFTER UPDATE ON trade FOR EACH ROW BEGIN
  UPDATE trade SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_fts_ai AFTER INSERT ON trade BEGIN
  INSERT INTO trade_fts(rowid, notes, psyche, improvement)
  VALUES (NEW.id, NEW.notes, NEW.psyche, NEW.improvement);
END;

CREATE TRIGGER trg_fts_ad AFTER DELETE ON trade BEGIN
  INSERT INTO trade_fts(trade_fts, rowid, notes, psyche, improvement)
  VALUES ('delete', OLD.id, OLD.notes, OLD.psyche, OLD.improvement);
END;

CREATE TRIGGER trg_fts_au AFTER UPDATE ON trade BEGIN
  INSERT INTO trade_fts(trade_fts, rowid, notes, psyche, improvement)
  VALUES ('delete', OLD.id, OLD.notes, OLD.psyche, OLD.improvement);
  INSERT INTO trade_fts(rowid, notes, psyche, improvement)
  VALUES (NEW.id, NEW.notes, NEW.psyche, NEW.improvement);
END;

CREATE VIEW v_trade AS
SELECT
  b.*,
  b.min_from_open - ((b.min_from_open %  5) +  5) %  5 AS bucket_5m,
  b.min_from_open - ((b.min_from_open % 15) + 15) % 15 AS bucket_15m
FROM (
  SELECT
    t.*,
    CASE t.outcome
      WHEN 'win'  THEN t.planned_rr
      WHEN 'loss' THEN -1.0
      ELSE 0.0
    END                                                 AS r,
    CAST(strftime('%w', t.trade_date) AS INTEGER)       AS dow,
    CASE t.trade_type
      WHEN 'backtesting'    THEN 'simulated'
      WHEN 'forwardtesting' THEN 'simulated'
      WHEN 'paper'          THEN 'simulated'
      ELSE 'live'
    END                                                 AS trade_type_group,
    (CAST(substr(t.entry_time,1,2) AS INTEGER)*60
     + CAST(substr(t.entry_time,4,2) AS INTEGER)) - 570 AS min_from_open
  FROM trade t
) b;

COMMIT;
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Open a connection with foreign keys on -- SQLite defaults them OFF.

    check_same_thread=False because Streamlit caches the connection across
    reruns and each rerun executes on a fresh thread. This is safe only because
    the app is single-user and local: Streamlit runs one script thread per
    session at a time, so access to the connection is already serialised.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # trg_trade_touch UPDATEs trade from inside an AFTER UPDATE ON trade
    # trigger. Recursion must stay off or that loops.
    conn.execute("PRAGMA recursive_triggers = OFF")
    return conn


def user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection, *, seed: bool = True) -> int:
    """Bring the database up to SCHEMA_VERSION. Returns the version applied.

    v1 is the whole schema, so migration is currently create-or-nothing. Later
    versions append numbered branches here rather than editing schema.sql.
    """
    current = user_version(conn)
    if current >= SCHEMA_VERSION:
        return current

    if current == 0:
        _require_fts5(conn)
        with conn:
            conn.executescript(SCHEMA_SQL.read_text())
            if seed:
                conn.executescript(SEEDS_SQL.read_text())
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        # A fresh database jumps straight to the current version, so it never
        # runs the numbered branches below -- and the chip colours live in one
        # of them. Without this every chip in a new install renders grey, which
        # is what happened before this line existed.
        _apply_palette(conn)
        return user_version(conn)

    if current == 1:
        # Rebuilding the table drops and recreates it while trade_tag and
        # trade_screenshot still reference it, so FK enforcement is off for the
        # duration. It cannot be toggled inside a transaction, hence out here.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.executescript(_V2)
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
        rebuild_fts(conn)
        current = 2

    if current == 2:
        _migrate_v3(conn)
        with conn:
            conn.execute("PRAGMA user_version = 3")
        current = 3

    return user_version(conn)


def _require_fts5(conn: sqlite3.Connection) -> None:
    options = {row[0] for row in conn.execute("PRAGMA compile_options")}
    has_fts5 = any(o.startswith("ENABLE_FTS5") for o in options)
    if not has_fts5:
        # Some builds report nothing useful in compile_options; probe directly.
        try:
            conn.execute("CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(x)")
            conn.execute("DROP TABLE temp.__fts_probe")
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                "This SQLite build lacks FTS5, which the schema requires for "
                "note search. Install a Python with FTS5 enabled, or drop the "
                "trade_fts table and its three triggers from schema.sql."
            ) from exc


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """External-content FTS is not filled by bulk inserts; rebuild after import."""
    with conn:
        conn.execute("INSERT INTO trade_fts(trade_fts) VALUES('rebuild')")


def init(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn
