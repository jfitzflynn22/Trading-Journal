"""Analytics. Every number here is in R.

Two rules are enforced structurally rather than by convention:

  * every query is scoped to exactly one trade type or one explicitly-named
    pooled group -- there is no way to ask for "all trades";
  * win rate is never returned as a single number. Both the excluding- and
    including-breakeven forms come back together, each with its own
    denominator, so a caller cannot accidentally render an unlabelled one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

FLAG_THRESHOLD = 20

# Sentinel column for the everything-pooled scope: it filters on nothing, but
# it still goes through Scope so no query can bypass the scoping machinery.
ALL_SCOPE = "*"

# Sentinel column for a pool defined as a named list of trade types rather than
# as a value of trade_type_group. Needed because the view's grouping puts paper
# under 'simulated', and the dashboard's pool cuts across that line.
MEMBER_SCOPE = "+"

# The scope picker. Individual types first; the pooled options are deliberate
# opt-ins and never the default. 'live' exists in v_trade but is not offered --
# small samples are flagged anyway, so exposing it buys little.
# First entry is the default the picker opens on.
SCOPES: list[tuple[str, str, str]] = [
    ("all", "All trade types", ALL_SCOPE),
    ("funded", "Funded", "trade_type"),
    ("backtesting", "Backtesting", "trade_type"),
    ("evaluation", "Evaluation", "trade_type"),
    ("paper", "Paper", "trade_type"),
    ("forwardtesting", "Forwardtesting", "trade_type"),
    # The dashboard's scope, offered here too at the user's request. Its column
    # is MEMBER_SCOPE, so it pools by an explicit list of types rather than by
    # trade_type_group -- see SCOPE_MEMBERS.
    ("live_market", "Live", MEMBER_SCOPE),
    # Backtesting and forwardtesting only. Paper used to fall in here, via the
    # view's trade_type_group; it now sits under Live, where the decision is
    # made on a live market even though the money is not real.
    ("simulated", "Simulated", MEMBER_SCOPE),
]

# Scopes that exist but are not offered in the picker. The dashboard is fixed
# to one of these; the journal and analytics pages keep the picker's list.
# Scopes that exist but are not offered in the picker. Empty for now: the
# dashboard's backtested tile reads the picker's own 'simulated' scope, which
# holds exactly the two types it wants.
HIDDEN_SCOPES: list[tuple[str, str, str]] = []

# Which trade types each MEMBER_SCOPE pools. Listed explicitly so the pooling
# is a stated fact in one place rather than a WHERE clause built at a call
# site -- the same reason the other pooled scopes are named rather than ad hoc.
#
# These two partition the five trade types: every type is in exactly one, so
# the dashboard's live figures and its backtested figure never share a trade.
SCOPE_MEMBERS: dict[str, tuple[str, ...]] = {
    "live_market": ("funded", "paper", "evaluation"),
    "simulated": ("backtesting", "forwardtesting"),
}

_SCOPE_DEFS = SCOPES + HIDDEN_SCOPES

# Mirrors the trade_type_group CASE in v_trade (schema.sql). Kept here only so
# a member scope can report whether it crosses the live/simulated line; the
# view stays the authority for anything that queries on the group.
_GROUP_OF = {"backtesting": "simulated", "forwardtesting": "simulated",
             "paper": "simulated", "evaluation": "live", "funded": "live"}

# Pooled scopes carry short labels, so their membership is disclosed in the
# caption under the picker instead of in the button text. Only 'simulated'
# needs it: its label does not say what it pools, whereas "All trade types"
# says exactly what it is and had a caption only restating the button.
SCOPE_NOTES: dict[str, str] = {
    "live_market": "Funded + Evaluation + Paper",
    "simulated": "Backtesting + Forwardtesting",
}
SCOPE_LABELS = {key: label for key, label, _ in _SCOPE_DEFS}

DIMENSIONS: dict[str, tuple[str, str]] = {
    "dow": ("Day of week", "dow"),
    "bucket_15m": ("Time of day (15 min)", "bucket_15m"),
    "bucket_5m": ("Time of day (5 min)", "bucket_5m"),
}

DOW_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday")

# Shared by every aggregate below. Both win rates, always, each with its own n.
_METRICS = """
    COUNT(*)                                                          AS n_all,
    SUM(outcome='win')                                                AS n_wins,
    SUM(outcome='loss')                                               AS n_losses,
    SUM(outcome='breakeven')                                          AS n_be,
    SUM(outcome IN ('win','loss'))                                    AS n_decided,
    1.0*SUM(outcome='win') / NULLIF(SUM(outcome IN ('win','loss')),0) AS win_rate_excl_be,
    1.0*SUM(outcome='win') / COUNT(*)                                 AS win_rate_incl_be,
    AVG(r)                                                            AS expectancy_incl_be,
    SUM(r) / NULLIF(SUM(outcome IN ('win','loss')),0)                 AS expectancy_excl_be,
    AVG(CASE WHEN outcome='win' THEN planned_rr END)                  AS avg_winner_r,
    AVG(planned_rr)                                                   AS avg_planned_rr,
    1.0*SUM(outcome='breakeven') / COUNT(*)                           AS be_rate,
    SUM(CASE WHEN r > 0 THEN r ELSE 0 END)                            AS gross_profit_r,
    SUM(CASE WHEN r < 0 THEN -r ELSE 0 END)                           AS gross_loss_r,
    SUM(CASE WHEN r > 0 THEN r ELSE 0 END)
      / NULLIF(SUM(CASE WHEN r < 0 THEN -r ELSE 0 END), 0)            AS profit_factor
"""


@dataclass(frozen=True)
class Scope:
    """One trade type, or one named pool. Never 'everything'."""

    key: str

    @property
    def column(self) -> str:
        for key, _, column in _SCOPE_DEFS:
            if key == self.key:
                return column
        raise ValueError(f"unknown scope {self.key!r}")

    @property
    def label(self) -> str:
        return SCOPE_LABELS[self.key]

    @property
    def members(self) -> tuple[str, ...]:
        """The trade types this scope covers. One type unless it is pooled."""
        if self.column == MEMBER_SCOPE:
            return SCOPE_MEMBERS[self.key]
        return (self.key,)

    @property
    def is_pooled(self) -> bool:
        return self.column in {"trade_type_group", ALL_SCOPE, MEMBER_SCOPE}

    @property
    def mixes_live_and_simulated(self) -> bool:
        """True when the scope puts simulated trades and real money in one
        number. Member scopes are checked against the view's own grouping,
        which counts paper as simulated -- so a funded+paper pool says True
        even though both are taken against a live market."""
        if self.column == MEMBER_SCOPE:
            return len({_GROUP_OF.get(t, "live") for t in self.members}) > 1
        return self.column == ALL_SCOPE

    def where(self, alias: str = "") -> tuple[str, list]:
        if self.column == ALL_SCOPE:
            return "1=1", []
        prefix = f"{alias}." if alias else ""
        if self.column == MEMBER_SCOPE:
            members = self.members
            placeholders = ",".join("?" * len(members))
            return f"{prefix}trade_type IN ({placeholders})", list(members)
        return f"{prefix}{self.column} = ?", [self.key]


def format_scope(scope: Scope) -> str:
    """Pooled scopes always name their membership."""
    return scope.label


ALL_TIME = "All time"
CURRENT_MONTH = "Current month"
DATE_RANGES = [ALL_TIME, "1Y", "YTD", CURRENT_MONTH]


def range_floor(label: str, today: date | None = None) -> str | None:
    """Earliest trade_date included by a range label, or None for all time.

    Cuts on trade_date -- the market session date -- not on when the row was
    written, so "this month" means trades taken this month.
    """
    today = today or date.today()
    if label == CURRENT_MONTH:
        return today.replace(day=1).isoformat()
    if label == "YTD":
        return date(today.year, 1, 1).isoformat()
    if label == "1Y":
        try:
            return today.replace(year=today.year - 1).isoformat()
        except ValueError:          # 29 Feb in a non-leap year
            return today.replace(year=today.year - 1, day=28).isoformat()
    return None


def headline(conn: sqlite3.Connection, scope: Scope,
             since: str | None = None) -> sqlite3.Row:
    clause, params = scope.where()
    if since:
        clause += " AND trade_date >= ?"
        params = params + [since]
    return conn.execute(
        f"SELECT {_METRICS} FROM v_trade WHERE {clause}", params
    ).fetchone()


TRAILING_WINDOW = 10


def trailing(conn: sqlite3.Connection, scope: Scope,
             window: int = TRAILING_WINDOW) -> sqlite3.Row:
    """Stats over the most recent `window` trades in the scope.

    'Most recent' uses the canonical chronological order (trade_date, then
    entry_time) -- market sequence, not the order things were typed in. For a
    backtesting scope that means the last sessions studied, which is the
    sequence the win rate is actually about.
    """
    clause, params = scope.where()
    return conn.execute(
        f"""
        SELECT
          COUNT(*)                                                          AS n,
          SUM(outcome='win')                                                AS n_wins,
          SUM(outcome='loss')                                               AS n_losses,
          SUM(outcome='breakeven')                                          AS n_be,
          SUM(outcome IN ('win','loss'))                                    AS n_decided,
          1.0*SUM(outcome='win') / COUNT(*)                                 AS win_rate_incl_be,
          1.0*SUM(outcome='win') / NULLIF(SUM(outcome IN ('win','loss')),0) AS win_rate_excl_be,
          AVG(r)                                                            AS expectancy_incl_be
        FROM (
          SELECT * FROM v_trade WHERE {clause}
          ORDER BY trade_date DESC, entry_time DESC, id DESC
          LIMIT ?
        )
        """,
        params + [window],
    ).fetchone()


def months_with_trades(conn: sqlite3.Connection, scope: Scope) -> list[str]:
    """'YYYY-MM' strings, oldest first. Drives the calendar's navigation."""
    clause, params = scope.where()
    return [row[0] for row in conn.execute(
        f"SELECT DISTINCT substr(trade_date,1,7) FROM v_trade WHERE {clause} ORDER BY 1",
        params)]


def daily_r(conn: sqlite3.Connection, scope: Scope, year: int, month: int) -> dict[str, dict]:
    """Net R per calendar day for one month, keyed 'YYYY-MM-DD'."""
    clause, params = scope.where()
    prefix = f"{year:04d}-{month:02d}-"
    rows = conn.execute(
        f"""SELECT trade_date, COUNT(*) AS n, SUM(r) AS net_r,
                   SUM(outcome='win') AS wins, SUM(outcome='loss') AS losses,
                   SUM(outcome='breakeven') AS bes
            FROM v_trade WHERE {clause} AND trade_date LIKE ?
            GROUP BY trade_date""",
        params + [prefix + "%"],
    ).fetchall()
    return {row["trade_date"]: dict(row) for row in rows}


def day_types(conn: sqlite3.Connection, scope: Scope,
              year: int, month: int) -> dict[str, list[str]]:
    """Which trade types each day of the month holds, keyed 'YYYY-MM-DD'.

    Only for labelling: `daily_r` aggregates a day into one net R with no trade
    type attached, which is correct for the number but loses what the day was.
    """
    clause, params = scope.where()
    rows = conn.execute(
        f"""SELECT trade_date, trade_type FROM v_trade
            WHERE {clause} AND trade_date LIKE ?
            GROUP BY trade_date, trade_type ORDER BY trade_date, trade_type""",
        params + [f"{year:04d}-{month:02d}-%"],
    ).fetchall()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["trade_date"], []).append(row["trade_type"])
    return out


def recent_trades(conn: sqlite3.Connection, scope: Scope,
                  limit: int = TRAILING_WINDOW) -> list[sqlite3.Row]:
    clause, params = scope.where()
    return conn.execute(
        f"""SELECT * FROM v_trade WHERE {clause}
            ORDER BY trade_date DESC, entry_time DESC, id DESC LIMIT ?""",
        params + [limit],
    ).fetchall()


def breakdown(conn: sqlite3.Connection, scope: Scope, dimension: str) -> list[sqlite3.Row]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}")
    _, expression = DIMENSIONS[dimension]
    clause, params = scope.where()
    return conn.execute(
        f"SELECT {expression} AS bucket, {_METRICS} FROM v_trade "
        f"WHERE {clause} GROUP BY bucket ORDER BY bucket",
        params,
    ).fetchall()


def tag_breakdown(
    conn: sqlite3.Connection, scope: Scope, kind: str, *, rollup: bool = False
) -> list[sqlite3.Row]:
    """Per-tag stats. Rows overlap: a trade with three tags appears three times.

    The DISTINCT matters for the rolled-up view: a trade tagged both '5m FVG'
    and '15m FVG' is one FVG trade, not two, and without it every aggregate in
    that bucket -- including n -- is inflated.
    """
    clause, params = scope.where("v")
    label = "COALESCE(g.family, g.name)" if rollup else "g.name"
    return conn.execute(
        f"""
        SELECT m.bucket, {_METRICS}
        FROM (
          SELECT DISTINCT {label} AS bucket, tt.trade_id
          FROM tag g JOIN trade_tag tt ON tt.tag_id = g.id
          WHERE g.kind = ?
        ) m
        JOIN v_trade v ON v.id = m.trade_id
        WHERE {clause}
        GROUP BY m.bucket
        ORDER BY n_all DESC
        """,
        [kind] + params,
    ).fetchall()


def tag_lift(
    conn: sqlite3.Connection, scope: Scope, kind: str, *, rollup: bool = False
) -> list[sqlite3.Row]:
    """Expectancy with the tag minus expectancy without it.

    Coverage is returned alongside: a tag on ~100% of trades has an almost
    empty 'without' group, so its lift is noise and the caller suppresses it.
    """
    clause, params = scope.where("v")
    label = "COALESCE(g.family, g.name)" if rollup else "g.name"
    return conn.execute(
        f"""
        WITH scoped AS (SELECT * FROM v_trade v WHERE {clause}),
        buckets AS (SELECT DISTINCT {label} AS bucket FROM tag g WHERE g.kind = ?),
        tagged AS (
          SELECT DISTINCT {label} AS bucket, tt.trade_id
          FROM tag g JOIN trade_tag tt ON tt.tag_id = g.id
          WHERE g.kind = ?
        )
        SELECT
          b.bucket,
          SUM(t.trade_id IS NOT NULL)                          AS n_with,
          SUM(t.trade_id IS NULL)                              AS n_without,
          1.0*SUM(t.trade_id IS NOT NULL) / COUNT(*)           AS coverage,
          AVG(CASE WHEN t.trade_id IS NOT NULL THEN s.r END)   AS exp_with,
          AVG(CASE WHEN t.trade_id IS NULL     THEN s.r END)   AS exp_without,
          AVG(CASE WHEN t.trade_id IS NOT NULL THEN s.r END)
            - AVG(CASE WHEN t.trade_id IS NULL THEN s.r END)   AS lift_r
        FROM buckets b
        CROSS JOIN scoped s
        LEFT JOIN tagged t ON t.bucket = b.bucket AND t.trade_id = s.id
        GROUP BY b.bucket
        HAVING n_with > 0
        ORDER BY n_with DESC
        """,
        params + [kind, kind],
    ).fetchall()


def lift_is_meaningful(row: sqlite3.Row) -> bool:
    """A lift needs both sides populated to say anything at all."""
    return min(row["n_with"], row["n_without"]) >= FLAG_THRESHOLD


def bucket_label(dimension: str, value) -> str:
    if value is None:
        return "—"
    if dimension == "dow":
        return DOW_NAMES[int(value)]
    minutes = int(value)
    width = 15 if dimension == "bucket_15m" else 5
    start = 570 + minutes
    end = start + width - 1
    return f"{start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}"


def list_trades(
    conn: sqlite3.Connection,
    scope: Scope,
    *,
    search: str = "",
    tag_ids: list[int] | None = None,
    order_by: str = "created_at DESC",
) -> list[sqlite3.Row]:
    clause, params = scope.where("v")
    sql = [f"SELECT v.* FROM v_trade v WHERE {clause}"]

    if search.strip():
        sql.append("AND v.id IN (SELECT rowid FROM trade_fts WHERE trade_fts MATCH ?)")
        params.append(search.strip())

    for tag_id in tag_ids or []:
        sql.append("AND EXISTS (SELECT 1 FROM trade_tag WHERE trade_id = v.id AND tag_id = ?)")
        params.append(tag_id)

    sql.append(f"ORDER BY {order_by}")
    return conn.execute(" ".join(sql), params).fetchall()


def tags_for_trades(conn: sqlite3.Connection, trade_ids: list[int]) -> dict[int, dict[str, list[str]]]:
    if not trade_ids:
        return {}
    placeholders = ",".join("?" * len(trade_ids))
    out: dict[int, dict[str, list[str]]] = {i: {"confluence": [], "dol": [], "entry": []}
                                            for i in trade_ids}
    for row in conn.execute(
        f"""SELECT tt.trade_id, g.kind, g.name FROM trade_tag tt
            JOIN tag g ON g.id = tt.tag_id
            WHERE tt.trade_id IN ({placeholders})
            ORDER BY g.sort_order, g.name""",
        trade_ids,
    ):
        out[row["trade_id"]][row["kind"]].append(row["name"])
    return out


def tag_palette(conn: sqlite3.Connection, kind: str) -> dict[str, str]:
    """Ordered {tag name: colour} for one kind. Order matters: the chip widget
    maps its colour list onto its option list by position."""
    return {row["name"]: row["color"] for row in conn.execute(
        "SELECT name, color FROM tag WHERE kind = ? AND is_active = 1 "
        "ORDER BY sort_order, name", (kind,))}


def chip_palette(conn: sqlite3.Connection, dimension: str) -> dict[str, str]:
    """Ordered {value: colour} for a fixed vocabulary (day/trade_type/outcome)."""
    return {row["value"]: row["color"] for row in conn.execute(
        "SELECT value, color FROM chip_color WHERE dimension = ?", (dimension,))}


def all_tags(conn: sqlite3.Connection, kind: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, name, family FROM tag WHERE kind = ? AND is_active = 1 "
        "ORDER BY sort_order, name",
        (kind,),
    ).fetchall()
