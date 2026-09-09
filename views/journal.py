"""The trade table and its right-hand detail drawer."""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

from journal import edits, queries as q
from journal.fields import FieldError, display_date, display_time

from .common import (IMAGE_TYPES, KIND_LABELS, OUTCOMES, TRADE_TYPES,
                     clear_filters_button, scope_picker)

# A real button in the row (ButtonColumn), not a checkbox: the cell value is
# the label, and clicking fires a Python callback with the row position.
OPEN = "open"
# Icon only. The grid draws to a canvas, so CSS cannot shrink the button text
# -- the label itself is the only lever short of scaling the whole app's font.
OPEN_LABEL = ":material/right_panel_open:"
NARROW = 70          # shared width so id and RR match exactly
# Plain scalar columns. Trade type and outcome moved to _save_chip_edits when
# they became chips -- they hold lists now, which this loop cannot compare.
EDITABLE_COLUMNS = {"date": "trade_date", "time": "entry_time", "rr": "planned_rr"}


def render() -> None:
    conn = st.session_state.conn
    scope = scope_picker()

    st.sidebar.subheader("Filters")
    tag_filter_ids: list[int] = []
    for kind, label in KIND_LABELS.items():
        by_name = {row["name"]: row["id"] for row in q.all_tags(conn, kind)}
        chosen = st.sidebar.multiselect(label, list(by_name), key=f"filter_{kind}")
        tag_filter_ids += [by_name[name] for name in chosen]
    # Last of the filters, under the three vocabularies: the others pick from a
    # fixed list, this one is free text. Keyed so Clear Filter can reset it;
    # the keys are listed in common.py.
    search = st.sidebar.text_input("Search notes", placeholder="e.g. conditions",
                                   key="filter_search")
    # Last sidebar call on this page, so it lands under the filters it clears.
    clear_filters_button()

    st.title("Trading Journal")

    if "delete_notice" in st.session_state:
        st.success(st.session_state.pop("delete_notice"))

    try:
        rows = q.list_trades(conn, scope, search=search, tag_ids=tag_filter_ids)
    except sqlite3.Error as exc:
        st.error(f"Search could not be parsed: {exc}")
        rows = q.list_trades(conn, scope, tag_ids=tag_filter_ids)

    _trades_tab(conn, rows)


# ------------------------------------------------------------------- trades

def _trades_tab(conn, rows) -> None:
    if not rows:
        st.info("No trades match this trade type and filter.")
        st.session_state.pop("open_trade", None)
        return

    visible = {row["id"] for row in rows}
    if st.session_state.get("open_trade") not in visible:
        st.session_state.pop("open_trade", None)
    is_open = "open_trade" in st.session_state

    # With a trade open the page splits in half: table on the left, drawer on
    # the right, both usable at once.
    if is_open:
        table_col, drawer_col = st.columns([1, 1], gap="medium")
    else:
        table_col, drawer_col = st.container(), None

    with table_col:
        _table(conn, rows, compact=is_open)
    if drawer_col is not None:
        with drawer_col:
            _drawer(conn, st.session_state["open_trade"])


def _open_from_row(rows) -> None:
    """Callback for the Open button. Streamlit reports the clicked row's
    position, which indexes the same list the frame was built from."""
    click = st.session_state.get("open_click")
    if not click:
        return
    position = click["row"]
    if 0 <= position < len(rows):
        st.session_state["open_trade"] = int(rows[position]["id"])


def _chips(label, palette: dict[str, str], **kwargs):
    """A coloured-chip column. The colour list is positional, so it is built
    from the same ordered mapping the options come from."""
    options = list(palette)
    return st.column_config.MultiselectColumn(
        label, options=options, color=[palette[o] for o in options], **kwargs)


TAG_COLUMNS = {"confluences": "confluence", "dol": "dol", "entry": "entry"}
SINGLE_CHIP_COLUMNS = {"type": "trade_type", "outcome": "outcome"}


def _save_chip_edits(conn, edited, frame) -> tuple[bool, list[str]]:
    """Persist chip edits. Multi-value columns map straight onto trade_tag;
    the single-value ones refuse anything that is not exactly one choice
    rather than writing something the schema would reject."""
    changed, problems = False, []
    for position, row in edited.iterrows():
        original = frame.loc[position]
        trade_id = int(original["id"])

        for column, kind in TAG_COLUMNS.items():
            new, old = sorted(map(str, row[column])), sorted(map(str, original[column]))
            if new != old:
                edits.set_tags(conn, trade_id, kind, [str(v) for v in row[column]])
                changed = True

        for column, field in SINGLE_CHIP_COLUMNS.items():
            new, old = [str(v) for v in row[column]], [str(v) for v in original[column]]
            if new == old:
                continue
            if len(new) != 1:
                problems.append(
                    f"Trade {trade_id} — {column}: choose exactly one value "
                    f"(got {len(new)}). Not saved.")
                continue
            try:
                edits.update_field(conn, trade_id, field, new[0])
                changed = True
            except (FieldError, sqlite3.Error) as exc:
                problems.append(f"Trade {trade_id} — {column}: {exc}")
    return changed, problems


def _cell_changed(column: str, new, old) -> bool:
    """Did this cell actually change?

    The date column needs its own comparison: it goes into the editor as a
    Timestamp and can come back as a plain date, and those two never compare
    equal even for an untouched cell -- a bare != there reports all 75 rows as
    edited and rewrites every one of them on the next run.
    """
    if column == "date":
        return pd.Timestamp(new) != pd.Timestamp(old)
    return new != old


def _table(conn, rows, *, compact: bool) -> None:
    tags = q.tags_for_trades(conn, [row["id"] for row in rows])
    # Notes are deliberately absent from the grid -- they live in the drawer.
    frame = pd.DataFrame([
        {
            OPEN: OPEN_LABEL,
            "id": row["id"],
            # A real date, not the stored string: DateColumn is what renders
            # MM/DD/YYYY and gives the cell a picker. Storage stays ISO.
            "date": pd.Timestamp(row["trade_date"]),
            "day": [q.DOW_NAMES[row["dow"]]],
            "time": display_time(row["entry_time"]),
            "type": [row["trade_type"]],
            "rr": row["planned_rr"],
            "outcome": [row["outcome"]],
            "confluences": list(tags[row["id"]]["confluence"]),
            "dol": list(tags[row["id"]]["dol"]),
            "entry": list(tags[row["id"]]["entry"]),
        }
        for row in rows
    ])

    hidden = {"confluences", "dol", "entry", "day"} if compact else set()
    config = {
        OPEN: st.column_config.ButtonColumn(
            "", type="tertiary", width="small", key="open_click",
            on_click=_open_from_row, args=(rows,),
            help="Open this trade in the side panel"),
        "id": st.column_config.NumberColumn("id", disabled=True, width=NARROW),
        "date": st.column_config.DateColumn("Date", format="MM/DD/YYYY",
                                            help="MM/DD/YYYY"),
        # Sized for "Wednesday", the longest weekday -- "small" (75px) clipped it.
        "day": _chips("Day", q.chip_palette(conn, "day"), disabled=True,
                      width=115,
                      help="Derived from the date and never stored — change the "
                           "date and this follows."),
        "time": st.column_config.TextColumn(
            "ToE", help="Type any time: 934, 9:34, 9:34am. Minute precision is kept."),
        "type": _chips("Trade type", q.chip_palette(conn, "trade_type"),
                       format_func=str.capitalize),
        "rr": st.column_config.NumberColumn("RR", min_value=0.01, step=0.1,
                                    width=NARROW),
        "outcome": _chips("Outcome", q.chip_palette(conn, "outcome"),
                          format_func=lambda v: "BE" if v == "breakeven" else v.capitalize(),
                          width="small"),
        "confluences": _chips("Confluences", q.tag_palette(conn, "confluence")),
        "dol": _chips("DoL", q.tag_palette(conn, "dol")),
        "entry": _chips("Entry", q.tag_palette(conn, "entry")),
    }
    for column in hidden:
        config[column] = None

    # Keyed container so theme.py can drive the grid height in vh.
    with st.container(key="journal_grid"):
        edited = st.data_editor(frame, hide_index=True, width="stretch",
                                key="grid", column_config=config)

    problems, changed = [], False
    for position, row in edited.iterrows():
        original = frame.loc[position]
        for column, field_name in EDITABLE_COLUMNS.items():
            if not _cell_changed(column, row[column], original[column]):
                continue
            try:
                edits.update_field(conn, int(row["id"]), field_name, row[column])
                changed = True
            except (FieldError, sqlite3.Error) as exc:
                problems.append(f"Trade {int(row['id'])} — {column}: {exc}")

    chip_changed, chip_problems = _save_chip_edits(conn, edited, frame)
    changed = changed or chip_changed
    problems += chip_problems
    for problem in problems:
        st.error(problem)
    if changed and not problems:
        st.rerun()



@st.dialog("Delete this trade?")
def _confirm_delete(conn, trade) -> None:
    """Names the specific trade before anything is removed. Irreversible."""
    st.markdown(f"**{trade['trade_date']} · {display_time(trade['entry_time'])}**")
    st.write(f"{trade['trade_type']} · RR {trade['planned_rr']} · "
             f"{trade['outcome']} · realised **{trade['r']:+.1f}R**")

    tags = q.tags_for_trades(conn, [trade["id"]])[trade["id"]]
    n_tags = sum(len(v) for v in tags.values())
    n_shots = sum(len(v) for v in edits.screenshots(conn, trade["id"]).values())
    goes_too = [f"{n_tags} tag link{'s' if n_tags != 1 else ''}"]
    if n_shots:
        goes_too.append(f"{n_shots} screenshot{'s' if n_shots != 1 else ''}")
    for field, label in (("notes", "notes"), ("psyche", "psyche"),
                         ("improvement", "review")):
        if trade[field]:
            goes_too.append(label)
    st.caption("Also removed: " + ", ".join(goes_too) + ".")
    st.warning("This cannot be undone.")

    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", width="stretch"):
        st.session_state.pop("pending_delete", None)
        st.rerun()
    if confirm.button("Delete permanently", type="primary", width="stretch"):
        try:
            summary = edits.delete_trade(
                conn, trade["id"],
                expect=tuple(trade[c] for c in edits.IDENTITY),
            )
        except (FieldError, sqlite3.Error, RuntimeError) as exc:
            st.error(str(exc))
            return

        st.session_state.pop("pending_delete", None)
        st.session_state.pop("open_trade", None)
        # The editor keys pending edits by row position; after a delete those
        # positions shift, so the stale state has to go with it.
        st.session_state.pop("grid", None)
        removed = [f"{summary['tags']} tag link{'s' if summary['tags'] != 1 else ''}"]
        if summary["screenshots"]:
            removed.append(f"{summary['screenshots']} "
                           f"screenshot{'s' if summary['screenshots'] != 1 else ''}")
        st.session_state["delete_notice"] = (
            f"Deleted {trade['trade_date']} {display_time(trade['entry_time'])} "
            f"({trade['trade_type']}, {trade['outcome']}) — {', '.join(removed)} removed."
        )
        if summary["files_failed"]:
            st.session_state["delete_notice"] += (
                f" Warning: {len(summary['files_failed'])} image file(s) could not be "
                "deleted from disk; the database rows are gone.")
        st.rerun()


def _when(conn, trade) -> None:
    """Date and time of entry, editable, at the head of the drawer.

    Both rerun after a successful write rather than falling through: the
    heading above and the day-of-week chip in the grid are both derived from
    these, and leaving them showing the old value would be a lie about what is
    now in the database.
    """
    trade_id = trade["id"]
    date_col, time_col = st.columns(2)
    new_date = date_col.date_input(
        "Date", value=date.fromisoformat(trade["trade_date"]),
        format="MM/DD/YYYY", key=f"drawer_date_{trade_id}")
    new_time = time_col.text_input(
        "Time of entry", value=display_time(trade["entry_time"]),
        key=f"drawer_time_{trade_id}")

    if new_date is not None and new_date.isoformat() != trade["trade_date"]:
        edits.update_field(conn, trade_id, "trade_date", new_date)
        st.rerun()

    if new_time.strip() != display_time(trade["entry_time"]):
        try:
            edits.update_field(conn, trade_id, "entry_time", new_time)
        except (FieldError, sqlite3.Error) as exc:
            st.error(f"Time: {exc}")
        else:
            st.rerun()


def _terms(conn, trade) -> None:
    """Trade type, RR and outcome -- the three fields realised R is derived
    from. The R itself is not printed here: it is RR on a win, -1 on a loss and
    0 on a breakeven, so these three controls already say it.

    Each writes and reruns on change, because the grid to the left renders the
    same three values and would otherwise keep showing the old ones.
    """
    trade_id = trade["id"]
    type_col, rr_col, outcome_col = st.columns([1.3, 0.8, 1.0])
    new_type = type_col.selectbox(
        "Trade type", TRADE_TYPES, index=TRADE_TYPES.index(trade["trade_type"]),
        format_func=str.capitalize, key=f"drawer_type_{trade_id}")
    # Keyed for the same stepper-hiding rule the entry form's RR field uses.
    with rr_col.container(key="drawer_rr_field"):
        new_rr = st.number_input(
            "RR", min_value=0.1, max_value=50.0, step=0.1,
            value=float(trade["planned_rr"]), key=f"drawer_rr_{trade_id}")
    new_outcome = outcome_col.selectbox(
        "Outcome", OUTCOMES, index=OUTCOMES.index(trade["outcome"]),
        format_func=str.capitalize, key=f"drawer_outcome_{trade_id}")

    edited = [
        ("trade_type", new_type, new_type != trade["trade_type"]),
        # A float round-trips through the widget, so compare with a tolerance
        # rather than == -- an exact test can fire on an untouched field.
        ("planned_rr", new_rr, abs(new_rr - float(trade["planned_rr"])) > 1e-9),
        ("outcome", new_outcome, new_outcome != trade["outcome"]),
    ]
    for column, value, changed in edited:
        if not changed:
            continue
        try:
            edits.update_field(conn, trade_id, column, value)
        except (FieldError, sqlite3.Error) as exc:
            st.error(f"{column}: {exc}")
        else:
            st.rerun()


def _drawer(conn, trade_id: int) -> None:
    trade = conn.execute("SELECT * FROM v_trade WHERE id = ?", (trade_id,)).fetchone()
    if trade is None:
        st.session_state.pop("open_trade", None)
        st.rerun()

    header, close = st.columns([5, 1])
    header.subheader(f"{display_date(trade['trade_date'])} · "
                     f"{display_time(trade['entry_time'])}")
    # Keyed container so theme.py can match its height to the upload buttons.
    with close.container(key="drawer_close"):
        if st.button("Close", width="stretch"):
            st.session_state.pop("open_trade", None)
            st.rerun()

    with st.container(border=True, key="trade_drawer"):
        _when(conn, trade)
        _terms(conn, trade)

        for kind, label in KIND_LABELS.items():
            names = [row["name"] for row in q.all_tags(conn, kind)]
            current = q.tags_for_trades(conn, [trade_id])[trade_id][kind]
            picked = st.multiselect(label, names, default=current,
                                    key=f"tags_{kind}_{trade_id}")
            if sorted(picked) != sorted(current):
                edits.set_tags(conn, trade_id, kind, picked)
                st.rerun()

        # All three grow with what they hold; the keyed containers are what
        # theme.py sizes them through. 68 is only Streamlit's floor for a text
        # area -- the heights that matter are set there, notes at twice the
        # other two and uncapped.
        for field_name, label, box in (("notes", "Notes", "drawer_notes_field"),
                                       ("psyche", "Psyche", "drawer_psyche_field"),
                                       ("improvement", "What can I improve",
                                        "drawer_improve_field")):
            with st.container(key=box):
                text = st.text_area(label, height=68, value=trade[field_name] or "",
                                    key=f"{field_name}_{trade_id}")
            # No rerun: text areas commit on blur and a rerun would steal focus.
            if text != (trade[field_name] or ""):
                edits.update_field(conn, trade_id, field_name, text)

        st.markdown("**Screenshots**")
        existing = edits.screenshots(conn, trade_id)
        for timeframe in ("ltf", "htf"):
            st.caption(timeframe.upper())
            for shot in existing[timeframe]:
                path = edits.MEDIA_ROOT / shot["rel_path"]
                # Image and its remove button share a keyed container so
                # theme.py can lift the button onto the picture's top-right
                # corner; the key's prefix is what the CSS matches on.
                with st.container(key=f"shot_{timeframe}_{shot['ordinal']}_{trade_id}"):
                    if path.exists():
                        st.image(str(path), width="stretch")
                    else:
                        st.caption("Image file missing from disk.")
                    if st.button("✕", key=f"rm_{timeframe}_{shot['ordinal']}_{trade_id}",
                                 help="Remove this screenshot"):
                        edits.remove_screenshot(conn, trade_id, timeframe,
                                                shot["ordinal"])
                        st.rerun()
            # The key carries a counter that is bumped after every successful
            # save. Without it the same picture was written on every rerun:
            # a file_uploader keeps returning its file until the widget is
            # destroyed, so the save below fired again on the rerun it had just
            # triggered, and again, until the 8-per-timeframe cap stopped it --
            # one upload, eight copies. Changing the key builds a fresh, empty
            # widget instead, which is also what clears the file from the form.
            nonce_key = f"upnonce_{timeframe}_{trade_id}"
            nonce = st.session_state.get(nonce_key, 0)
            upload = st.file_uploader(f"Add {timeframe.upper()}",
                                      type=IMAGE_TYPES,
                                      key=f"up_{timeframe}_{trade_id}_{nonce}")
            if upload is not None:
                try:
                    edits.add_screenshot(conn, trade_id, timeframe,
                                         upload.getvalue(), upload.name)
                except FieldError as exc:
                    # No rerun and no bump: the file stays put with the reason
                    # next to it, rather than vanishing silently.
                    st.error(str(exc))
                else:
                    st.session_state[nonce_key] = nonce + 1
                    st.rerun()

        # Bottom of the panel, below everything it would destroy. The keyed
        # container is a stable hook for theme.py -- the button's own key
        # carries the trade id, so it cannot be selected on directly.
        st.divider()
        with st.container(key="delete_trade"):
            if st.button("Delete trade", key=f"del_{trade_id}", width="stretch"):
                st.session_state["pending_delete"] = trade_id
                st.rerun()

    # Driven by session state rather than by the button's own return value: a
    # button reads True only on the run it was pressed, so calling the dialog
    # from inside that branch would tear it down on the very next rerun --
    # taking the confirm click with it.
    if st.session_state.get("pending_delete") == trade_id:
        _confirm_delete(conn, trade)
