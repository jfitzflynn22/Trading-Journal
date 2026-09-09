"""Analytics: breakdowns, tag performance and lift.

Split out of the journal page so the trade table gets the full window. The
trade-type picker is shared with the journal page via its widget key, so the
scope you were looking at carries across.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from journal import queries as q

from .common import (KIND_LABELS, clear_filters_button, flag, pct, r_value,
                     scope_picker)


def render() -> None:
    conn = st.session_state.conn
    scope = scope_picker()
    # Trade type is the only sidebar filter this page has; the button clears
    # the journal's filters too, so the two pages agree on what "cleared" means.
    clear_filters_button()

    st.title("Analytics")
    head = q.headline(conn, scope)
    if head["n_all"] == 0:
        st.info("No trades in this scope.")
        return

    st.subheader(scope.label)
    if head["n_all"] < q.FLAG_THRESHOLD:
        st.warning(f"n = {head['n_all']}. Below {q.FLAG_THRESHOLD} trades these figures "
                   "are a log, not a statistic — read them as description, not edge.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expectancy (incl. BE)", r_value(head["expectancy_incl_be"]),
              help="Mean R per trade over every trade, breakevens included")
    c2.metric(f"Win rate (excl. BE){flag(head['n_decided'])}",
              pct(head["win_rate_excl_be"]), help=f"n = {head['n_decided']} decided trades")
    c3.metric(f"Win rate (incl. BE){flag(head['n_all'])}",
              pct(head["win_rate_incl_be"]), help=f"n = {head['n_all']} trades")
    c4.metric("Trades", head["n_all"],
              help=f"{head['n_wins']}W / {head['n_losses']}L / {head['n_be']}BE")

    with st.expander("Secondary figures"):
        d1, d2, d3 = st.columns(3)
        d1.metric("Expectancy (excl. BE)", r_value(head["expectancy_excl_be"]))
        d2.metric("Avg winner", r_value(head["avg_winner_r"]))
        d3.metric("Average RR", r_value(head["avg_planned_rr"]))
        st.caption(f"Breakeven rate {pct(head['be_rate'])}")

    st.divider()
    st.subheader("Breakdowns")
    dimension = st.radio("Slice by", list(q.DIMENSIONS),
                         format_func=lambda k: q.DIMENSIONS[k][0], horizontal=True)
    st.dataframe(
        pd.DataFrame([
            {
                "Bucket": q.bucket_label(dimension, row["bucket"]),
                "n": row["n_all"],
                "⚠": "⚠" if row["n_all"] < q.FLAG_THRESHOLD else "",
                "Win rate (excl. BE)": pct(row["win_rate_excl_be"]),
                "n decided": row["n_decided"],
                "Win rate (incl. BE)": pct(row["win_rate_incl_be"]),
                "Expectancy (incl. BE)": r_value(row["expectancy_incl_be"]),
            }
            for row in q.breakdown(conn, scope, dimension)
        ]),
        hide_index=True, width="stretch",
    )
    st.caption(f"⚠ marks fewer than {q.FLAG_THRESHOLD} trades in that metric's own "
               "denominator. Win rate (excl. BE) uses the decided-trade count.")

    st.divider()
    st.subheader("Tags")
    kind = st.radio("Dimension", list(KIND_LABELS), format_func=KIND_LABELS.get,
                    horizontal=True)
    rollup = st.toggle("Roll up timeframe variants (FVG, IFVG, SMT, Continuation)",
                       value=True)

    st.dataframe(
        pd.DataFrame([
            {
                "Tag": row["bucket"],
                "n": row["n_all"],
                "⚠": "⚠" if row["n_all"] < q.FLAG_THRESHOLD else "",
                "Win rate (excl. BE)": pct(row["win_rate_excl_be"]),
                "Win rate (incl. BE)": pct(row["win_rate_incl_be"]),
                "Expectancy (incl. BE)": r_value(row["expectancy_incl_be"]),
            }
            for row in q.tag_breakdown(conn, scope, kind, rollup=rollup)
        ]),
        hide_index=True, width="stretch",
    )
    st.caption("Rows overlap — a trade with three tags appears in three rows, so the n "
               "column sums to more than the trade count.")

    st.markdown("**Lift** — expectancy with the tag minus expectancy without it")
    st.dataframe(
        pd.DataFrame([
            {
                "Tag": row["bucket"],
                "Coverage": pct(row["coverage"]),
                "n with": row["n_with"],
                "n without": row["n_without"],
                "Expectancy with": r_value(row["exp_with"]),
                "Expectancy without": r_value(row["exp_without"]),
                "Lift": r_value(row["lift_r"]) if q.lift_is_meaningful(row)
                        else "— too few on one side",
            }
            for row in q.tag_lift(conn, scope, kind, rollup=rollup)
        ]),
        hide_index=True, width="stretch",
    )
    st.caption("A tag on nearly every trade has an almost empty 'without' group, so its "
               "lift says nothing and is suppressed rather than shown.")
