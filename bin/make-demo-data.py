#!/usr/bin/env python
"""Fill a database with synthetic trades, for screenshots and public demos.

    python bin/make-demo-data.py               # writes demo.db
    python bin/make-demo-data.py --db /tmp/x.db --trades 120
    JOURNAL_DB=$PWD/demo.db streamlit run app.py

Every trade is invented. The point is to show what the journal looks like in
use without publishing anyone's real record, so nothing here is imported,
scraped or derived from real trading -- the numbers come from a seeded
generator and mean nothing.

It refuses to write to a database that already holds trades unless you pass
--force, so it cannot quietly overwrite a real journal.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from journal import db, edits, queries as q  # noqa: E402

# Weighted so the mix looks like someone who mostly backtests, is evaluating,
# and has a small live sample -- the shape the analytics flags are built for.
TRADE_TYPE_WEIGHTS = [
    ("backtesting", 46),
    ("forwardtesting", 10),
    ("paper", 8),
    ("evaluation", 20),
    ("funded", 16),
]

# Deliberately unremarkable: a positive but unimpressive expectancy, which is
# what makes the flags and the "n is too small" warnings visible in a demo.
OUTCOME_WEIGHTS = [("win", 55), ("loss", 38), ("breakeven", 7)]

NOTES = [
    "Clean sweep of the overnight low, waited for the reclaim before entering.",
    "Entered early on the first push and got wicked out. Should have waited.",
    "Textbook setup, no hesitation. Sized normally and let it run to target.",
    "Chased this one after missing the first entry. Not a setup I trade.",
    "Session opened inside the range so I stood down until the sweep.",
    "Held through the retrace instead of managing to breakeven. Worked out.",
    "Small range day, took the scalp and stopped for the session.",
    "News at the open, waited it out and took the second leg.",
]
PSYCHE = [
    "Calm, slept well, no pressure to trade.",
    "Impatient after two days flat. Noticed it and slowed down.",
    "Slightly rushed, checked the plan twice before entering.",
    "Focused. No urge to add or move the stop.",
    "Frustrated from the previous session, kept size small.",
]
IMPROVEMENTS = [
    "Wait for the reclaim rather than the sweep itself.",
    "Stop taking the first entry of the session on principle.",
    "Write the invalidation down before entering, not after.",
    "Nothing to change here; repeat this.",
]


def weighted(rng: random.Random, pairs):
    values = [v for v, _ in pairs]
    weights = [w for _, w in pairs]
    return rng.choices(values, weights=weights, k=1)[0]


def session_time(rng: random.Random) -> str:
    """A plausible entry time. Clustered around the first hour, because that is
    where the analytics' time-of-day buckets are meant to show something."""
    minute = int(rng.gauss(mu=25, sigma=18))
    minute = max(0, min(minute, 150))          # 09:30 to 12:00
    hour, minute = divmod(570 + minute, 60)
    return f"{hour}:{minute:02d}"


def build(conn, count: int, seed: int) -> int:
    rng = random.Random(seed)
    vocab = {kind: [row["name"] for row in q.all_tags(conn, kind)]
             for kind in ("confluence", "dol", "entry")}
    if not any(vocab.values()):
        raise SystemExit("no tag vocabulary in this database - was it seeded?")

    # Walk backwards from today over weekdays only, skipping some so the
    # calendar has gaps in it rather than a solid block.
    day = date.today()
    written = 0
    while written < count:
        day -= timedelta(days=1)
        if day.weekday() >= 5:                 # no weekend trading
            continue
        if rng.random() < 0.45:                # not every weekday is traded
            continue

        outcome = weighted(rng, OUTCOME_WEIGHTS)
        # Planned R:R in quarter steps; losses skew slightly lower, the way a
        # real record does when the good setups are the ones that run.
        rr = round(rng.choice([1.0, 1.0, 1.2, 1.3, 1.5, 1.8, 2.0, 2.1, 2.4, 3.0])
                   * (0.9 if outcome == "loss" else 1.0), 1)

        tags = {
            "confluence": rng.sample(vocab["confluence"],
                                     k=min(rng.randint(1, 3), len(vocab["confluence"]))),
            "dol": rng.sample(vocab["dol"], k=min(rng.randint(1, 3), len(vocab["dol"]))),
            "entry": rng.sample(vocab["entry"], k=min(rng.randint(1, 2), len(vocab["entry"]))),
        }

        edits.create_trade(
            conn,
            trade_date=day,
            entry_time=session_time(rng),
            trade_type=weighted(rng, TRADE_TYPE_WEIGHTS),
            planned_rr=max(rr, 0.5),
            outcome=outcome,
            notes=rng.choice(NOTES) if rng.random() < 0.8 else None,
            psyche=rng.choice(PSYCHE) if rng.random() < 0.5 else None,
            improvement=rng.choice(IMPROVEMENTS) if rng.random() < 0.3 else None,
            tags=tags,
        )
        written += 1
    return written


def mark_as_demo(conn, written: int, seed: int) -> None:
    """Stamp the database so the app knows to say so.

    The mark lives in the database rather than in an environment variable, so a
    demo file cannot be opened quietly: however it is launched, and whoever
    launches it, the banner appears. Real journals never have this table, and
    the app treats its absence as "not a demo".
    """
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS demo_marker (
                created_at TEXT NOT NULL,
                trades     INTEGER NOT NULL,
                seed       INTEGER NOT NULL,
                note       TEXT NOT NULL
            )""")
        conn.execute("DELETE FROM demo_marker")
        conn.execute(
            "INSERT INTO demo_marker (created_at, trades, seed, note) VALUES "
            "(datetime('now'), ?, ?, ?)",
            (written, seed,
             "Synthetic data generated by bin/make-demo-data.py. "
             "Every trade here is invented; none of it is a real trading record."),
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="demo.db", help="database to write (default: demo.db)")
    ap.add_argument("--trades", type=int, default=90, help="how many to generate")
    ap.add_argument("--seed", type=int, default=7, help="rng seed; same seed, same data")
    ap.add_argument("--force", action="store_true",
                    help="write even if the database already holds trades")
    args = ap.parse_args()

    path = Path(args.db).expanduser()
    conn = db.init(path)

    existing = conn.execute("SELECT count(*) FROM trade").fetchone()[0]
    if existing and not args.force:
        print(f"{path} already holds {existing} trades. Refusing to add demo data "
              f"on top of it.\nPass --force if that is really what you want, or "
              f"point --db somewhere else.", file=sys.stderr)
        return 1

    written = build(conn, args.trades, args.seed)
    db.rebuild_fts(conn)                       # bulk inserts bypass the FTS triggers
    mark_as_demo(conn, written, args.seed)

    print(f"wrote {written} synthetic trades to {path}")
    print(f"\nRun the demo with:\n    JOURNAL_DB={path.resolve()} streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
