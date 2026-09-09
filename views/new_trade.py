"""Trade entry form. Writes straight into the journal database."""

from __future__ import annotations

import sqlite3
from datetime import date

import streamlit as st

from journal import edits, queries as q
from journal.fields import FieldError, display_date, display_time

from .common import IMAGE_TYPES, KIND_LABELS, OUTCOMES, TRADE_TYPES


def render() -> None:
    conn = st.session_state.conn

    st.title("Add Trade")

    if "just_saved" in st.session_state:
        saved = st.session_state.pop("just_saved")
        shots = saved.get("shots", 0)
        st.success(
            f"Saved trade #{saved['id']} — {saved['date']} {saved['time']}, "
            f"{saved['type']}, {saved['outcome']} ({saved['r']:+.1f}R)"
            + (f", {shots} screenshot{'' if shots == 1 else 's'}." if shots else ".")
        )
        # The trade saved; these did not. Named individually so it is clear
        # which picture to re-add from the drawer.
        for problem in saved.get("shot_errors", []):
            st.warning(f"Screenshot not saved — {problem}")

    # Read before the form is built; bumped after a save, which rebuilds the
    # two uploaders empty. See the comment where they are created.
    shot_nonce = st.session_state.get("new_shot_nonce", 0)

    # enter_to_submit=False: saving a trade should take a deliberate click on
    # Save Entry, not a stray Enter while tabbing through fields. It also drops
    # the "Press Enter to submit form" hint the widgets show to advertise it.
    with st.form("new_trade", clear_on_submit=True, enter_to_submit=False):
        # One row for everything that identifies the trade. The weights are
        # driven by the *labels*, not the values: "Time of entry" is the widest
        # at ~78px and wraps to two lines below that, which drops its input out
        # of line with the rest of the row. Trade type gets the most room -- it
        # carries the longest value ("forwardtesting") -- and RR keeps enough
        # width for its -/+ steppers.
        c1, c2, c3, c4, c5 = st.columns([1.0, 0.95, 1.25, 0.8, 1.0])
        trade_date = c1.date_input("Date", value=date.today(), format="MM/DD/YYYY")
        entry_time = c2.text_input("Time of entry", placeholder="9:34")
        # format_func only changes what is displayed -- the values these return
        # are still the lowercase ones the schema stores.
        trade_type = c3.selectbox("Trade type", TRADE_TYPES,
                                  index=TRADE_TYPES.index("funded"),
                                  format_func=str.capitalize)
        # Keyed container so theme.py can hide the -/+ steppers: this is a
        # number you type, and the steppers only invited 0.1-at-a-time clicking.
        # Still a number_input, so the field keeps its numeric validation.
        with c4.container(key="rr_field"):
            planned_rr = st.number_input("RR", min_value=0.1, max_value=50.0,
                                         value=1.0, step=0.1)
        outcome = c5.selectbox("Outcome", OUTCOMES, format_func=str.capitalize)

        picked: dict[str, list[str]] = {}
        for kind, label in KIND_LABELS.items():
            names = [row["name"] for row in q.all_tags(conn, kind)]
            picked[kind] = st.multiselect(label, names, key=f"new_{kind}")

        # Screenshots. Unlike every other field these cannot be written with
        # the trade: add_screenshot needs a trade_id, and there is no trade yet
        # -- so the uploads are held here and saved once the insert returns one.
        # LTF first, matching the order the drawer lists them in. The counter
        # in the keys is bumped after each save so the next trade starts with
        # empty uploaders -- a file_uploader holds its files until the widget
        # is destroyed, and clear_on_submit does not survive the st.rerun()
        # below, so without this the last trade's pictures would be written to
        # the next one as well.
        ltf_col, htf_col = st.columns(2)
        ltf_files = ltf_col.file_uploader(
            "LTF screenshots", type=IMAGE_TYPES, accept_multiple_files=True,
            key=f"new_ltf_{shot_nonce}", help="Up to 8. Added to the trade once it saves.")
        htf_files = htf_col.file_uploader(
            "HTF screenshots", type=IMAGE_TYPES, accept_multiple_files=True,
            key=f"new_htf_{shot_nonce}", help="Up to 8. Added to the trade once it saves.")

        notes = st.text_area("Notes", height=140,
                             help="Not shown in the trade table — open the trade to read it.")
        # Open, not tucked into an expander: psyche is an input to review, and
        # a field you have to go looking for is a field that stays empty.
        #
        # Starts at 68px -- the height of the multiselects above it, and also
        # Streamlit's floor for a text area -- and grows as it is typed into.
        # The growing is CSS, keyed off this container; see theme.py.
        with st.container(key="psyche_field"):
            psyche = st.text_area(
                "Psyche", height=68,
                help="Not shown in the trade table — open the trade to read it.")

        submitted = st.form_submit_button("Save Entry", type="primary")

    if not submitted:
        return

    try:
        trade_id = edits.create_trade(
            conn,
            trade_date=trade_date,
            entry_time=entry_time,
            trade_type=trade_type,
            planned_rr=planned_rr,
            outcome=outcome,
            notes=notes,
            psyche=psyche,
            # No improvement field on this form any more. The column and its
            # drawer editor both stay: a review of what to do better is written
            # after the trade has been sat with, not while logging it.
            tags=picked,
        )
    except FieldError as exc:
        st.error(str(exc))
        return
    except sqlite3.Error as exc:
        st.error(f"Could not save: {exc}")
        return

    # The trade is committed by this point, so a failed image is reported
    # rather than raised: losing the whole entry over one unreadable file would
    # be the worse outcome, and the drawer can take the picture afterwards.
    saved_shots, shot_errors = 0, []
    for timeframe, uploads in (("ltf", ltf_files), ("htf", htf_files)):
        for upload in uploads or []:
            try:
                edits.add_screenshot(conn, trade_id, timeframe,
                                     upload.getvalue(), upload.name)
                saved_shots += 1
            except (FieldError, sqlite3.Error, OSError) as exc:
                shot_errors.append(f"{timeframe.upper()} {upload.name}: {exc}")

    # Retires both uploaders, so these files cannot follow the next trade in.
    st.session_state["new_shot_nonce"] = shot_nonce + 1

    row = conn.execute("SELECT * FROM v_trade WHERE id = ?", (trade_id,)).fetchone()
    st.session_state["just_saved"] = {
        "id": trade_id, "date": display_date(row["trade_date"]),
        "time": display_time(row["entry_time"]),
        "type": row["trade_type"], "outcome": row["outcome"], "r": row["r"],
        "shots": saved_shots, "shot_errors": shot_errors,
    }
    st.rerun()
