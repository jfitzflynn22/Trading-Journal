"""Trading journal.

    .venv/bin/streamlit run app.py

Three pages: the dashboard, the journal table, and the entry form. Every page
that shows a statistic is scoped to one trade type or to the one named pooled
scope -- there is no "all trades" view anywhere, by design.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from journal import queries as q
from views import analytics, dashboard, journal, new_trade, theme
from views.common import SIDEBAR_TITLE, demo_banner, get_conn

# The favicon is the app icon, not an emoji, because Safari's "Add to Dock"
# takes the web app's icon straight from it -- that is what puts the right
# picture in the Dock and in the Cmd-Tab switcher. Absolute path: the server
# is started by launchd as well as by hand, and their working directories
# differ.
st.set_page_config(
    page_title="Trading Journal",
    page_icon=str(Path(__file__).parent / "assets" / "app-icon.png"),
    layout="wide",
)

theme.inject()
st.session_state.conn = get_conn()

# Chip colours come from the tag table, so they are injected once here rather
# than per page: the same vocabulary is picked in three places (the drawer,
# the sidebar filters and the New Trade form) and should look the same in all
# of them.
#
# The kinds are merged into one name->colour map because a chip exposes only
# its value, not its kind. The tag table's UNIQUE is (kind, name), so the same
# name *could* be added under two kinds with different colours -- if that ever
# happens the last kind listed here wins for both. No name is currently shared.
theme.tag_chip_css({
    name: colour
    for kind in ("confluence", "dol", "entry")
    for name, colour in q.tag_palette(st.session_state.conn, kind).items()
})

# url_path is explicit because all three page functions are called render(),
# and Streamlit would otherwise infer the same pathname for each.
pages = st.navigation([
    st.Page(dashboard.render, title="Dashboard", icon=":material/home:",
            url_path="dashboard", default=True),
    st.Page(journal.render, title="Trading Journal", icon=":material/table_rows:",
            url_path="journal"),
    st.Page(analytics.render, title="Analytics", icon=":material/insights:",
            url_path="analytics"),
    # url_path stays "new-trade": it is the page's address, not its label, and
    # theme.PAGE_PATHS keys the stored light/dark choice off it.
    st.Page(new_trade.render, title="Add Trade", icon=":material/add_circle:",
            url_path="new-trade"),
])

# First, so it is the top item of the sidebar's content area and sits in the
# same place whatever the page adds below it. Sidebar order is call order.
theme.appearance_toggle()
st.sidebar.caption(f"{SIDEBAR_TITLE} · all figures in R")

# Before the page, not inside it: it has to be the first thing read on every
# page, and it must not be something an individual page can forget to call.
demo_banner(st.session_state.conn)
pages.run()
