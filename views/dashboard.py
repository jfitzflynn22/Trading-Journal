"""Home page."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from journal import queries as q
from journal.fields import display_date, display_time

from . import theme
from .common import GREETING, pct, profit_factor_display, r_value, table_height


# The dashboard is fixed to trades taken against a live market -- funded and
# paper -- at the user's request (2026-08-28). It is the "how am I actually
# trading" page, so it never mixes in backtests or forwardtests. The trade type
# picker lives on the journal page, where switching between types is the point.
#
# Note what this pools: paper is grouped as 'simulated' in v_trade, because the
# money is not real, so these figures put paper fills and funded fills in one
# number. That is the deliberate reading -- both are decisions made on live
# price, in real time -- but a paper win is not a funded win, and the win rate
# here no longer answers "how am I doing on the funded account" on its own.
# Funded alone is always one click away on the Journal and Analytics pages.
DASHBOARD_SCOPE = "live_market"

# The second scope on this page, and the only figure that reads it: the
# backtested win rate. This is the picker's own Simulated scope -- backtesting
# and forwardtesting -- rather than a second definition of the same pair. It is
# the complement of DASHBOARD_SCOPE: between them the two cover all five trade
# types and share none, so the two win rates on the page can never be counting
# the same trade twice.
BACKTEST_SCOPE = "simulated"

# What a calendar day is marked with, by trade type. Every type in the scope
# is here, so every traded cell names what it was rather than leaving funded as
# an unlabelled default -- the marker exists because a day's aggregate carries
# no trade type of its own.
DAY_MARKERS = {"funded": "Funded", "paper": "Paper", "evaluation": "Evaluation"}


def render() -> None:
    conn = st.session_state.conn
    scope = q.Scope(DASHBOARD_SCOPE)

    today = datetime.now()
    theme.hero(GREETING, f"{today:%A, %B %-d, %Y}")

    # Date range drives every figure on this page: all four tiles and At a
    # glance. The two exceptions are lists, not statistics -- Recent Trades is
    # the last ten whatever is selected, and the calendar has its own month
    # navigation.
    with st.container(key="range_filter"):
        date_range = st.segmented_control(
            "Date range", q.DATE_RANGES, default=q.ALL_TIME, required=True,
            key="date_range", label_visibility="collapsed",
        ) or q.ALL_TIME
    since = q.range_floor(date_range, today.date())

    head = q.headline(conn, scope, since=since)

    # An empty range takes out the figures, not the page. Returning here used
    # to blank the calendar too -- so picking Current month before the first
    # trade of the month left nothing on screen, including the day grid that
    # would have shown the trade once it was logged.
    if head["n_all"] == 0:
        st.info(
            f"No {scope.label.lower()} trades in this range"
            f"{'' if date_range == q.ALL_TIME else f' ({date_range.lower()})'}."
        )
        _calendar(conn, scope)
        return

    pf_value, pf_help = profit_factor_display(head)
    # The one figure on the page that is not about live trading. Same date
    # range as everything else, different scope -- so it is labelled by scope
    # rather than by denominator alone, and the live tiles are too.
    tested = q.headline(conn, q.Scope(BACKTEST_SCOPE), since=since)

    # No sample-size markers on this page: it is a status board, not an
    # analysis surface. The <20 flagging still applies on the Analytics tab,
    # where the breakdowns are actually read as evidence.
    c1, c2, c3, c4, c5 = st.columns(5)
    # Both win rates exclude breakevens, and neither says so in its label --
    # the tile beside them does, by reporting the breakeven share outright.
    # That is a deliberate departure from the usual labelling rule;
    # the denominator is still spelled out in each tooltip.
    c1.metric(
        "Live Win Rate",
        pct(head["win_rate_excl_be"]),
        help=f"Funded, paper and evaluation trades. Wins ÷ decided trades. "
             f"n = {head['n_decided']} ({head['n_be']} breakevens excluded).",
    )
    c2.metric(
        "Live Breakeven Rate",
        pct(head["be_rate"]),
        help=f"Live trades that finished flat, over every live trade: "
             f"{head['n_be']} of {head['n_all']}. This is the share the win "
             "rate to the left leaves out.",
    )
    c3.metric(
        "Backtested Win Rate",
        pct(tested["win_rate_excl_be"]),
        help=f"Backtesting and forwardtesting. Wins ÷ decided trades. "
             f"n = {tested['n_decided']} ({tested['n_be']} breakevens excluded). "
             "Shares no trade with the live figures.",
    )
    c4.metric("Profit factor", pf_value, help=pf_help)
    # Was Consistency -- a win rate over a fixed 10-trade window, which was the
    # one figure on the page that ignored the range filter. Expectancy replaces
    # it because it reads the range like everything else here, and because the
    # obvious ranged alternative, win rate over the range, is already tile two.
    c5.metric(
        "Expectancy",
        r_value(head["expectancy_incl_be"]),
        help=f"Live trades. Mean R per trade across the range, breakevens "
             f"included. n = {head['n_all']}. Excluding breakevens it is "
             f"{r_value(head['expectancy_excl_be'])} over {head['n_decided']} "
             "decided trades.",
    )

    # No range caption and no spacer here: the tiles run straight into the two
    # panels. What the caption used to say still shows -- the range is named in
    # the At a glance title, and the trade counts are its first two rows.
    # "small" is the same 16px gap the tile row above uses -- "medium" put 32px
    # between the panels and the calendar, twice the rhythm of everything else
    # on the page. Both columns take up the slack in proportion, so the two
    # move towards each other rather than one stretching across.
    left, right = st.columns([5, 6], gap="small")

    with left:
        glance = [
            {"Metric": "Trades", "Value": str(head["n_all"])},
            {"Metric": "Wins / losses / breakevens",
             "Value": f"{head['n_wins']} / {head['n_losses']} / {head['n_be']}"},
            {"Metric": "Avg winner", "Value": r_value(head["avg_winner_r"])},
            {"Metric": "Average RR", "Value": r_value(head["avg_planned_rr"])},
            {"Metric": "Gross won / lost",
             "Value": f"{head['gross_profit_r']:.1f}R / {head['gross_loss_r']:.1f}R"},
        ]
        # The range is in the title because these five figures move with it and
        # nothing else on the row does: Recent Trades below is the last ten
        # whatever is selected, and Consistency says so in its own caption.
        with theme.panel(f"At a glance · {date_range}", key="glance_table"):
            st.dataframe(pd.DataFrame(glance), hide_index=True, width="stretch",
                         height=table_height(len(glance)))

        recent = [
            {
                "Date": display_date(row["trade_date"]),
                "ToE": display_time(row["entry_time"]),
                "Outcome": row["outcome"],
                "R": f"{row['r']:+.1f}",
            }
            for row in q.recent_trades(conn, scope)
        ]
        with theme.panel("Recent Trades", key="recent_table"):
            st.dataframe(pd.DataFrame(recent), hide_index=True, width="stretch",
                         height=table_height(len(recent)))

    with right:
        _calendar(conn, scope)


def _calendar(conn, scope) -> None:
    # The current month is always reachable and is where the calendar opens,
    # even before anything has been traded in it. An empty grid is the honest
    # answer to "how has this month gone"; opening on the last month that
    # happened to contain a trade reads as stale.
    this_month = f"{date.today():%Y-%m}"
    months = sorted(set(q.months_with_trades(conn, scope)) | {this_month})

    state_key = f"cal_month_{scope.key}"
    if state_key not in st.session_state or st.session_state[state_key] not in months:
        st.session_state[state_key] = this_month

    current = st.session_state[state_key]
    position = months.index(current)
    year, month = int(current[:4]), int(current[5:7])

    with theme.panel("Calendar"):
        # Keyed so theme.py can size the two arrows; their own keys carry the
        # scope name, so there is no fixed class to select them by.
        nav = st.container(key="cal_nav")
        with nav:
            nav_prev, nav_title, nav_next = st.columns([1, 5, 1])
        if nav_prev.button("‹", disabled=position == 0, width="stretch",
                           key=f"prev_{scope.key}"):
            st.session_state[state_key] = months[position - 1]
            st.rerun()
        nav_title.markdown(
            f'<div class="cal-title" style="text-align:center">'
            f"{theme.month_title(year, month)}</div>",
            unsafe_allow_html=True,
        )
        if nav_next.button("›", disabled=position == len(months) - 1, width="stretch",
                           key=f"next_{scope.key}"):
            st.session_state[state_key] = months[position + 1]
            st.rerun()

        days = _tagged_days(conn, scope, year, month)
        st.markdown(theme.calendar_html(year, month, days), unsafe_allow_html=True)


def _tagged_days(conn, scope, year: int, month: int) -> dict[str, dict]:
    """Net R per day for the whole scope, each day marked with what it was.

    The totals come from one pooled query rather than from merging a query per
    trade type. That was safe only while no two types could share a date -- true
    of funded and paper, but not something to keep relying on now that
    evaluation is in scope: a merge would have silently dropped one type's R
    from any day that held both.
    """
    days = q.daily_r(conn, scope, year, month)
    for day, types in q.day_types(conn, scope, year, month).items():
        marks = [DAY_MARKERS[t] for t in types if t in DAY_MARKERS]
        if marks and day in days:
            # One type per day, per the user -- so this is normally a single
            # mark. Joined rather than picked from if that ever stops holding,
            # so a mixed day says so instead of quietly showing one label over
            # another type's R.
            days[day]["tag"] = "+".join(marks)
    return days
