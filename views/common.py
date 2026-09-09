"""Shared state and formatting for the pages."""

from __future__ import annotations

import os

import streamlit as st

from journal import db, queries as q

OUTCOMES = ["win", "loss", "breakeven"]
# Shared by the entry form and the drawer, so the two cannot drift into
# accepting different things.
IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
TRADE_TYPES = ["backtesting", "forwardtesting", "paper", "evaluation", "funded"]
KIND_LABELS = {"confluence": "Confluences", "dol": "Draw on liquidity", "entry": "Entry model"}

# Who the journal belongs to. Unset by default -- the dashboard then greets you
# with a plain "Welcome" and the sidebar says "Trading journal". Put your name
# in and it becomes "Welcome, <name>" and "<name>'s journal":
#
#     export JOURNAL_OWNER="Sam"
#
# An environment variable rather than an edit, so pulling an update never
# conflicts with your name.
OWNER = os.environ.get("JOURNAL_OWNER", "").strip()
GREETING = f"Welcome, {OWNER}" if OWNER else "Welcome"
SIDEBAR_TITLE = f"{OWNER}'s journal" if OWNER else "Trading journal"


@st.cache_resource
def get_conn():
    return db.init()


def is_demo(conn) -> bool:
    """True when this database was filled by bin/make-demo-data.py.

    Read from the database, not from an environment variable, so a demo file
    announces itself however it was opened -- including a public deployment
    where nobody sees the command that started it.
    """
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_marker'"
    ).fetchone() is not None


def demo_banner(conn) -> None:
    """Say plainly that the numbers are invented. Shown on every page: someone
    linked straight to Analytics should not have to have seen the dashboard to
    know the win rate in front of them is fictional."""
    if not is_demo(conn):
        return
    st.warning(
        "**Demo — every trade here is fake.** This database was filled by "
        "`bin/make-demo-data.py` with randomly generated trades so the app can "
        "be shown without publishing anyone's real record. Nothing on this page "
        "is a real trading result.",
        icon=":material/science:",
    )


def scope_picker(*, key: str = "scope") -> q.Scope:
    """The scope control. Every figure in the app hangs off this.

    Rendered on any page that shows statistics; deliberately absent from the
    entry form, where trade type is a property of the trade being written.
    """
    # Keyed so theme.py can space this heading on its own: it sits directly
    # under the ownership caption, where the shared sidebar heading rule leaves
    # it flush, while "Filters" gets breathing room from the picker's margin.
    with st.sidebar.container(key="scope_heading"):
        st.subheader("Trade type")
    # The same segmented control the appearance and date-range toggles use,
    # stacked vertically -- seven options will not fit across a 300px sidebar.
    # The keyed container is what gives theme.py its st-key- hook.
    #
    # width="stretch" is load-bearing, not decoration: the default is "content",
    # which sizes the whole element container to the widest button and leaves
    # "Forwardtesting" truncated at ~112px. CSS on the inner elements cannot
    # undo it -- the container it sets is above them.
    with st.sidebar.container(key="scope_picker"):
        scope_key = st.segmented_control(
            "Trade type",
            [key_ for key_, _, _ in q.SCOPES],
            format_func=lambda k: q.SCOPE_LABELS[k],
            default=q.SCOPES[0][0],
            required=True,
            key=key,
            label_visibility="collapsed",
            width="stretch",
        )
    # required=True should never yield None; the fallback keeps a stale or
    # empty selection from taking down every figure on the page.
    scope = q.Scope(scope_key or q.SCOPES[0][0])
    note = q.SCOPE_NOTES.get(scope.key)
    if note:
        # Keyed so theme.py can pull it up against the picker it describes;
        # Streamlit's uniform block gap otherwise parks it under the next
        # heading instead.
        with st.sidebar.container(key="scope_note"):
            st.caption(note)
    return scope


# Every sidebar filter widget, by key. The scope picker is included because it
# is a filter like any other -- the journal page's own filters and the trade
# type both narrow what you are looking at, and clearing one without the other
# would leave the page still filtered. Analytics only has the scope, so the
# missing keys are simply absent from session_state there.
SCOPE_DEFAULT = q.SCOPES[0][0]
FILTER_DEFAULTS: dict[str, object] = {
    "scope": SCOPE_DEFAULT,
    "filter_search": "",
    "filter_confluence": [],
    "filter_dol": [],
    "filter_entry": [],
}


def _filters_are_set() -> bool:
    return any(st.session_state.get(key, default) != default
               for key, default in FILTER_DEFAULTS.items())


def _clear_filters() -> None:
    """Put every filter widget back to its default.

    Assigns the defaults rather than deleting the keys. Deleting them does
    clear the Python-side value -- the table really does come back unfiltered
    -- but the widgets go on *displaying* the old selection, because nothing
    told the browser its own copy was stale. Assigning marks the value as set
    by the server, which is what pushes it back down to the frontend.

    Runs as an on_click callback, which fires before the script reruns; setting
    these inline would hit widgets already instantiated this run, which
    Streamlit rejects.
    """
    for key, default in FILTER_DEFAULTS.items():
        # A fresh list each time: handing the same one to every rerun would let
        # a later selection mutate the default itself.
        st.session_state[key] = list(default) if isinstance(default, list) else default


def clear_filters_button() -> None:
    """Reset every sidebar filter. Rendered last, so it sits below them."""
    st.sidebar.button(
        "Clear Filter", key="clear_filters", on_click=_clear_filters,
        width="stretch", disabled=not _filters_are_set(),
        help="Resets the trade type and every filter to its default.",
    )


ROW_PX = 35  # Streamlit's dataframe row height, plus one for the header


def table_height(rows: int) -> int:
    """Exact pixel height for a dataframe of `rows` rows.

    Hard-coding a height leaves blank rows when the content shrinks; this sizes
    to the actual row count so there is neither dead space nor a scrollbar.
    """
    return ROW_PX * (rows + 1) + 3


def pct(value) -> str:
    return "—" if value is None else f"{value:.1%}"


def r_value(value) -> str:
    return "—" if value is None else f"{value:+.2f}R"


def ratio(value) -> str:
    return "—" if value is None else f"{value:.2f}"


def flag(n: int) -> str:
    return " ⚠" if n < q.FLAG_THRESHOLD else ""


def profit_factor_display(row) -> tuple[str, str]:
    """Profit factor, and an honest label for the undefined case.

    With no losing trades the denominator is zero -- that is not an infinite
    edge, it is an absent denominator, and it says so rather than showing ∞.
    """
    if row["gross_loss_r"] in (None, 0):
        return "—", "No losing trades yet, so there is no denominator to divide by."
    return (f"{row['profit_factor']:.2f}",
            f"{row['gross_profit_r']:.1f}R won ÷ {row['gross_loss_r']:.1f}R lost")
