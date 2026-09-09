"""Visual layer: the card look, the appearance toggle, and the R calendar.

The palette is deliberately narrow -- one green, one red, one neutral. Green
and red mean exactly one thing in this app (a day finished up or down in R) and
are never used decoratively, so the calendar reads at a glance. They are the
one thing that does *not* change between light and dark: a win is the same
green either way.

Two palettes are defined here, and a matching pair lives in
.streamlit/config.toml. Both halves are needed. This file paints everything the
app draws itself; the config paints Streamlit's own chrome and, crucially, the
dataframe grids -- those render to <canvas>, so no stylesheet can reach them
and only a real Streamlit theme switch changes them.

Dark follows Google's Material dark (neutral greys on #1f1f1f); light follows
Claude's (warm cream). They are matched to different references on purpose --
each was chosen on its own, so do not "harmonise" one to the other.
"""

from __future__ import annotations

import calendar
import html
from contextlib import contextmanager
from datetime import date

import streamlit as st
import streamlit.components.v1 as components

GREEN = "#22c55e"
RED = "#ef4444"

DEFAULT_MODE = "dark"
MODES = ("dark", "light")

# Every page's pathname, because Streamlit stores the chosen appearance per
# path -- setting it on one page alone would leave the others on "System".
PAGE_PATHS = ("/", "/dashboard", "/journal", "/analytics", "/new-trade")

# card   -- panel ground, sits just above the page background so panels read as
#           raised; below it they look like holes punched in the page.
# card-2 -- the ground inside a panel (calendar cells, the active toggle pill).
# edge   -- hairline borders.
PALETTES: dict[str, dict[str, str]] = {
    # Google's Material dark, as on the Search history / My Activity pages:
    # a #1f1f1f ground with a neutral grey ramp above it. Every grey here is
    # neutral by design -- a warm or blue-leaning one shows up immediately
    # against this ground as a wrong colour rather than a different shade.
    "dark": {
        "card": "#2d2f31",
        "card_2": "#37393b",
        "edge": "#444746",
        "muted": "#9aa0a6",
        "hover": "rgba(255,255,255,.06)",
        "hover_text": "#e8eaed",
        "active_text": "#e8eaed",
        "pill_shadow": "0 1px 2px rgba(0,0,0,.35)",
        # Denser than the original .13: the calendar cells sit on card_2,
        # which is lighter here than the old #242424, so the same alpha
        # carried less contrast.
        "tint": ".15",
        "tint_edge": ".45",
        "flat_tint": "rgba(154,160,166,.12)",
        "flat_edge": "rgba(154,160,166,.38)",
        "swatch_flat": "rgba(154,160,166,.5)",
        # Must equal theme.dark.sidebar.backgroundColor in config.toml -- note
        # the sidebar-specific key, not secondaryBackgroundColor. It backs the
        # pinned toggle, so a mismatch shows up as a band of the wrong grey
        # behind it when the sidebar scrolls.
        "sidebar_bg": "#171717",
    },
    # Claude's light mode: warm cream ground, white panels, near-black text.
    "light": {
        "card": "#ffffff",
        "card_2": "#f5f3ec",
        "edge": "#e3e0d6",
        "muted": "#6b6862",
        "hover": "rgba(0,0,0,.05)",
        "hover_text": "#1f1e1d",
        "active_text": "#1f1e1d",
        "pill_shadow": "0 1px 2px rgba(0,0,0,.10)",
        # Denser tints: the same alpha that reads clearly on near-black washes
        # out to almost nothing on cream.
        "tint": ".20",
        "tint_edge": ".55",
        "flat_tint": "rgba(107,104,98,.10)",
        "flat_edge": "rgba(107,104,98,.30)",
        "swatch_flat": "rgba(107,104,98,.45)",
        # Light has no [theme.light.sidebar] override: its sidebar is already
        # deeper than its page via secondaryBackgroundColor, so this tracks
        # that key instead. Dark is the one that needed a dedicated token.
        "sidebar_bg": "#f0eee6",
    },
}


def mode() -> str:
    """The palette currently being rendered.

    The browser is the source of truth, not session state: Streamlit reads the
    chosen appearance from localStorage at load, and a reload would reset any
    server-side flag while the real theme stayed put. `st.context.theme.type`
    is how the server sees what the browser actually applied.
    """
    active = getattr(st.context.theme, "type", None)
    return active if active in MODES else DEFAULT_MODE


def _css(mode_name: str) -> str:
    p = PALETTES[mode_name]
    return f"""
<style>
  :root {{
    --card: {p["card"]};
    --card-2: {p["card_2"]};
    --edge: {p["edge"]};
    --muted: {p["muted"]};
    --hover: {p["hover"]};
    --hover-text: {p["hover_text"]};
    --active-text: {p["active_text"]};
    --pill-shadow: {p["pill_shadow"]};
    --flat-tint: {p["flat_tint"]};
    --flat-edge: {p["flat_edge"]};
    --swatch-flat: {p["swatch_flat"]};
    --sidebar-bg: {p["sidebar_bg"]};
    --green: {GREEN};
    --red: {RED};
  }}

  /* No max-width: fill whatever the window gives us. The side gutters are a
     flat 30px on every page -- Streamlit's own are responsive (80px on a wide
     window, 16px on a narrow one), which left far more empty page than this
     app wants at desk width. !important because Streamlit sets them from a
     generated class that outranks a bare selector. */
  .block-container {{
    /* Started at 9px, which put the title 30px down to match the side gutter,
       then pulled up twice at the user's request to land it at 18. The last
       leg needs a negative margin: padding bottoms out at 0, and most of the
       remaining gap is the heading's own line box, not container padding. */
    padding-top: 0;
    margin-top: -3px;
    max-width: 100%;
    padding-left: 30px !important;
    padding-right: 30px !important;
  }}
  /* Streamlit's header is a 60px opaque band across the top with z-index
     999990, so pulling the content up put every page title behind it. The
     band has nothing in it but the Deploy button and the ⋮ menu, both at the
     far right, so it is made see-through and click-through -- otherwise it
     would swallow clicks across the full width of the first 60px of the page,
     title included. Its two controls get their own pointer-events back. */
  [data-testid="stHeader"],
  [data-testid="stHeader"] [data-testid="stToolbar"] {{
    background: transparent !important;
    pointer-events: none;
  }}
  [data-testid="stHeader"] [data-testid="stAppDeployButton"],
  [data-testid="stHeader"] [data-testid="stMainMenu"],
  [data-testid="stHeader"] button {{
    pointer-events: auto;
  }}

  /* Every st.markdown("<style>...") lands in its own element container. The
     container is zero-height, but the page's vertical block has row-gap:16px,
     so each invisible one still costs 16px of page height. Two are injected
     (the palette above and the tag-chip colours), and those 32px were pushing
     the journal's header down and making the page itself scroll on top of the
     grid's own scrolling. display:none removes the box and its gap; a <style>
     element still applies from inside a hidden container.

     Matched loosely on purpose: Streamlit puts an unnamed wrapper between the
     element container and the markdown container, so a direct-child chain
     silently fails to match. Nothing but these injections puts a <style> tag
     inside an element container. */
  [data-testid="stElementContainer"]:has(style) {{
    display: none !important;
  }}

  /* Page headings: one size and one baseline everywhere.

     Two things pulled them apart. st.title() renders an h1 at 44px with 20px
     of its own top padding, while the dashboard's hero is a plain div at 40px
     with none -- so the titled pages sat lower *and* larger. This trims the
     padding so the text starts at the same y as the hero, and matches the
     sizes; .hero-name below carries the same 2.25rem.

     Deliberately not scoped to a page: scoping the padding to the journal is
     exactly what left Analytics and New Trade out of line before. */
  [data-testid="stMain"] h1 {{
    font-size: 2.25rem !important;
    padding-top: 7px !important;
  }}

  /* Viewport-relative heights for the two tall panels. Streamlit's height=
     argument only takes pixels or "stretch" (which sizes to the parent, not
     the window), so these are driven by CSS against the st-key- class that
     a keyed container emits.

     These fill the space left over rather than taking a fixed percentage of
     it: the chrome above the grid is a constant whatever the screen, so a
     percentage wastes room on a tall monitor and starves the panel on a short
     one.

     The constant is that chrome plus the gap wanted underneath: the grid's top
     edge sits 79px down (title block and its spacing), and 30px is the gap
     below, matching the page's side gutters. It was 145 when the page started
     35px lower; left alone after the content moved up, the table simply
     stopped 66px short of the bottom. Desktop only; the min-height floors stop
     it collapsing on an unusually short window. */
  .st-key-journal_grid div[data-testid="stDataFrame"],
  .st-key-journal_grid div[data-testid="stDataFrameResizable"] {{
    height: calc(100vh - 109px) !important;
    max-height: calc(100vh - 109px) !important;
    /* Only a floor against a degenerate window. It used to be 260px, which
       outgrew the calc below ~405px of viewport height and put the page back
       into scrolling -- the thing the viewport-relative height exists to
       avoid. At 120px it only bites below ~265px tall, where nothing would be
       usable anyway. */
    min-height: 120px !important;
  }}
  /* The grid's own Fullscreen button drops it into a fixed, full-viewport
     overlay. The windowed height above is !important, so without this it kept
     its in-page height there: the table got wider but not taller.

     Gated on the toolbar button's label, which flips to "Close fullscreen"
     while expanded. Streamlit wraps *every* dataframe in stFullScreenFrame
     whether or not it is expanded, so matching the frame alone would apply
     this in the page too; and the only other difference is a generated
     emotion class that changes between Streamlit builds.

     height:100% rather than a viewport calc: it resolves against the frame's
     content box, so the overlay's own padding is accounted for without this
     having to know what that padding is. */
  .st-key-journal_grid [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"])
    div[data-testid="stDataFrame"],
  .st-key-journal_grid [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"])
    div[data-testid="stDataFrameResizable"] {{
    height: 100% !important;
    max-height: 100% !important;
  }}

  /* Streamlit reserves 160px under every page for a chat input this app does
     not have, which is what was stopping the grid reaching the bottom of the
     window. Scoped with :has() so only the journal page loses it -- the other
     pages are short enough that the slack is harmless there. */
  .block-container:has(.st-key-journal_grid) {{ padding-bottom: 8px !important; }}
  /* The drawer is a flex item in a column container, so `height` alone loses
     to flex sizing -- max-height plus a non-growing flex is what actually
     clamps it. Its own header row (date + Close) is rendered above the
     container and costs a fixed 82px, so its constant is the grid's plus
     that: the two then finish flush at the bottom of the window. Move one and
     the other has to follow. */
  .st-key-trade_drawer {{
    max-height: calc(100vh - 191px) !important;
    min-height: 120px !important;
    flex: 0 0 auto !important;
    overflow-y: auto !important;
  }}
  /* Keep the drawer's contents at their natural height.

     The drawer is a clamped flex column, so its children are flex items free
     to shrink -- and because Streamlit gives each element container
     overflow:auto, they are scroll containers, whose automatic minimum size is
     0 rather than their content. Nothing stopped them collapsing: the three
     text areas (the tallest items, so they absorbed most of the shrinkage)
     were squashed to zero height and the Notes field simply was not there.
     The drawer scrolls instead, which is what overflow-y above is for. */
  .st-key-trade_drawer > [data-testid="stElementContainer"],
  .st-key-trade_drawer > [data-testid="stVerticalBlock"],
  .st-key-trade_drawer > [data-testid="stHorizontalBlock"] {{
    flex-shrink: 0 !important;
  }}
  /* Remove-screenshot button: sits on the picture's top-right corner instead
     of below it. Matched on the key prefix -- each container's key carries the
     timeframe, ordinal and trade id, so there is no single class to hang it
     on. The dark disc is its own, not the theme's card colour: it has to stay
     legible over whatever the screenshot happens to show underneath. */
  [class*="st-key-shot_"] {{
    position: relative;
  }}
  /* Matched on the button's own key, NOT on ":has(button)": the image's
     container holds buttons too -- Streamlit's fullscreen/download toolbar --
     and the looser selector took the picture out of the flow along with the
     control meant to sit on top of it. */
  [class*="st-key-shot_"] [class*="st-key-rm_"] {{
    position: absolute;
    /* Tucked into the corner, but never flush with it: a hairline of chart
       still shows on both sides, so the disc reads as sitting on the image
       rather than being clipped by its edge. */
    top: 4px;
    right: 4px;
    width: auto !important;
    z-index: 3;
  }}
  [class*="st-key-rm_"] button {{
    background: rgba(0,0,0,.55) !important;
    border: 1px solid rgba(255,255,255,.25) !important;
    color: #fff !important;
    border-radius: 5px !important;
    padding: 0 !important;
    /* Sized to the glyph rather than to a comfortable tap target: this sits on
       top of the picture, so the disc is kept just wide enough to read as a
       button and no wider. */
    width: 20px !important;
    height: 20px !important;
    min-height: 0 !important;
    font-size: .8rem !important;
    line-height: 1 !important;
  }}
  [class*="st-key-rm_"] button:hover {{
    background: rgba(239,68,68,.85) !important;
    border-color: rgba(239,68,68,.95) !important;
  }}
  /* The image is the block the button is pinned to, so it must not carry the
     bottom margin Streamlit gives it, or the corner drifts off the picture. */
  [class*="st-key-shot_"] [data-testid="stImage"] {{
    margin-bottom: 0 !important;
  }}

  /* File uploaders, on the entry form and in the drawer. Streamlit gives the
     dropzone a 68px floor and its button a 40px one, which is a lot of dark
     panel for one short row -- and there are two of them side by side on the
     form. Trimmed to the height of the button plus its padding. */
  [data-testid="stFileUploaderDropzone"] {{
    padding: 6px 12px !important;
    min-height: 0 !important;
  }}
  [data-testid="stFileUploaderDropzone"] button {{
    min-height: 0 !important;
    height: 30px !important;
    padding: 2px 12px !important;
  }}
  /* The calendar's month arrows and the drawer's Close button, sized to that
     same 30px. All three are chrome around content rather than content, so
     they read better at one height; Streamlit's default 2rem left them taller
     than everything they sit beside. height, not min-height -- Streamlit pins
     these with the former. */
  .st-key-cal_nav button,
  .st-key-drawer_close button {{
    min-height: 0 !important;
    height: 30px !important;
    padding: 2px 12px !important;
  }}
  /* Close sits on the same line as the drawer's date + time heading, and the
     row stretches its columns, so the short button landed at the top of a tall
     one -- 14px above the title's centre. Centring the row gets most of it;
     the heading's padding is lopsided (12 top, 16 bottom) so its text centre
     is not its box centre, and the margin covers the rest. NB flex centring
     splits a margin between both sides, so 12px here buys a 6px shift. */
  [data-testid="stHorizontalBlock"]:has(.st-key-drawer_close) {{
    align-items: center !important;
  }}
  .st-key-drawer_close {{
    margin-top: 12px !important;
  }}

  /* The rule above Delete trade. Streamlit hangs 32px off both sides of an
     hr, which left it floating mid-way between the HTF uploader and the
     button. Pulled up against the uploader; the space below is left alone, so
     the line reads as closing the screenshots section rather than as a lid on
     the button. Scoped to the drawer -- the dividers on Analytics keep theirs. */
  .st-key-trade_drawer hr {{
    margin-top: 8px !important;
  }}

  /* Delete trade: tinted the same red the calendar uses for a losing day, at
     the same strength, so the one destructive control on the page reads as
     dangerous without shouting. The confirmation dialog is what actually
     guards it -- this only has to make the button not look like Close. */
  .st-key-delete_trade button {{
    background: rgba(239,68,68,{p["tint"]}) !important;
    border-color: rgba(239,68,68,{p["tint_edge"]}) !important;
  }}
  .st-key-delete_trade button:hover {{
    background: rgba(239,68,68,{min(float(p["tint"]) * 2, 0.45):.2f}) !important;
    border-color: rgba(239,68,68,.75) !important;
  }}

  /* Psyche on the entry form: opens at the height of the multiselects above
     it and grows a line at a time as it is typed into.

     Streamlit's floor for a text area is 68px, so the widget is created at 68
     and the real height set here instead. field-sizing:content is what does
     the growing -- it is Chromium-only, and where it is missing the field
     simply stays at its one-line height with a scrollbar and the drag handle
     still works. The containers have to be released from the fixed height the
     widget gave them, or they would clip the field as it grew. */
  :is(.st-key-psyche_field, .st-key-drawer_psyche_field,
      .st-key-drawer_improve_field, .st-key-drawer_notes_field) textarea {{
    min-height: 34px !important;
    height: auto !important;
    field-sizing: content;
    max-height: 40vh;   /* past this it scrolls, rather than pushing Save Entry
                           off the bottom of the page */
  }}
  /* Notes in the drawer is the exception on both counts: it opens at twice the
     psyche box, and it is never capped, so a note is read in full rather than
     through a scrolling window. The drawer itself scrolls if it has to. */
  .st-key-drawer_notes_field textarea {{
    /* 88px, i.e. twice the 44px the others settle at when empty. Unlike their
       34px floor this is the finished height, not a floor plus padding: once
       min-height clears the content it is the box, border-box and all. */
    min-height: 88px !important;
    max-height: none !important;
  }}
  /* Every one of them needs its containers released from the fixed height the
     widget was created with, or they clip the field as it grows. */
  :is(.st-key-psyche_field, .st-key-drawer_psyche_field,
      .st-key-drawer_improve_field, .st-key-drawer_notes_field)
    :is([data-testid="stTextAreaRootElement"], [data-testid="stTextArea"],
        [data-testid="stElementContainer"]) {{
    height: auto !important;
  }}

  /* RR on the entry form: typed, not stepped. The steppers are the only part
     of a number_input CSS can remove -- keeping the widget keeps the numeric
     keyboard, the min/max and the "not a number" rejection. Scoped to the one
     field so any other number_input keeps its own. */
  .st-key-rr_field [data-testid="stNumberInputStepUp"],
  .st-key-rr_field [data-testid="stNumberInputStepDown"],
  .st-key-drawer_rr_field [data-testid="stNumberInputStepUp"],
  .st-key-drawer_rr_field [data-testid="stNumberInputStepDown"] {{
    display: none !important;
  }}
  /* Without the buttons the input has nothing to pad against on the right. */
  .st-key-rr_field [data-testid="stNumberInputContainer"] input,
  .st-key-drawer_rr_field [data-testid="stNumberInputContainer"] input {{
    padding-right: 12px !important;
  }}

  /* Metric tiles as cards */
  div[data-testid="stMetric"] {{
    background: var(--card);
    border: 1px solid var(--edge);
    border-radius: 14px;
    /* Top-weighted on purpose, and it still totals the 18px the tile was
       sized on, so the row's height does not move. The value's line box
       carries descender space that "65.0%" never uses, which left the text
       sitting optically high inside an evenly padded tile; 13/5 puts it back
       on the tile's visual centre. */
    padding: 13px 18px 5px;
    /* Fill the column rather than reserving space for a label that might wrap
       -- see the height chain below, which is what keeps the row even. */
    height: 100%;
  }}
  /* Equal-height tiles, the honest way round: the columns already stretch to
     the tallest of them, so passing that height down to the tile itself means
     a wrapped label lifts the whole row together. The alternative -- holding
     two lines' worth of empty space in every label on the chance that one of
     them wraps -- cost 17px of dead height on every tile.
     Scoped with :has() to columns that actually hold a metric: a blanket
     height:100% on every column would stretch the journal drawer and the
     entry form's fields too. */
  [data-testid="stColumn"]:has([data-testid="stMetric"]) > div,
  [data-testid="stColumn"]:has([data-testid="stMetric"]) [data-testid="stVerticalBlock"],
  [data-testid="stColumn"]:has([data-testid="stMetric"]) [data-testid="stElementContainer"] {{
    height: 100%;
  }}
  div[data-testid="stMetric"] label p {{
    color: var(--muted) !important;
    font-size: .78rem !important;
    letter-spacing: .02em;
  }}
  /* Let a tile label wrap. Streamlit pins it to one line and ellipsises the
     overflow, which at five tiles across turned "Backtested Win Rate (excl.
     BE)" into "Backtested Win R…" -- and a metric whose name is cut off is
     not a metric. Both the container and the <p> carry the nowrap.

     NB no `div` on these selectors: stMetricLabel is a <label>, and prefixing
     it with div -- as the stMetric rules above legitimately do for their own
     wrapper -- silently matches nothing. */
  [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"],
  [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p {{
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
  }}
  [data-testid="stMetricLabel"] {{
    align-items: flex-start !important;
  }}
  div[data-testid="stMetricValue"] {{
    font-size: 2.0rem !important;
    font-weight: 650;
    letter-spacing: -.02em;
  }}

  /* Panels: real bordered containers, so content sits inside the card */
  div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--card);
    border: 1px solid var(--edge) !important;
    border-radius: 14px;
    padding: 6px 6px 2px 6px;
  }}
  /* Date-range segmented control: one grey bar matching the metric tiles,
     with the active option raised out of it. */
  .st-key-range_filter,
  .st-key-appearance_toggle,
  .st-key-scope_picker {{
    background: var(--card);
    border: 1px solid var(--edge);
    border-radius: 12px;
    padding: 5px 6px;
    margin-bottom: 14px;
    /* A flex child stretches across the cross axis by default, which would
       make this bar span the whole column; these two make it hug its buttons. */
    align-self: flex-start !important;
    width: fit-content !important;
    flex: 0 0 auto !important;
  }}
  /* The flex row holding the buttons. NB the selector: [data-baseweb=
     "button-group"] matches nothing in this Streamlit -- it was dead here for
     a long time, so this 2px gap never actually applied. stButtonGroup is the
     real testid, and the flex container is its child. */
  .st-key-range_filter [data-testid="stButtonGroup"] > div,
  .st-key-appearance_toggle [data-testid="stButtonGroup"] > div,
  .st-key-scope_picker [data-testid="stButtonGroup"] > div {{
    gap: 2px;
  }}
  .st-key-range_filter button,
  .st-key-appearance_toggle button,
  .st-key-scope_picker button {{
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    color: var(--muted) !important;
    font-size: .84rem !important;
    font-weight: 500 !important;
    padding: 5px 14px !important;
    min-height: 0 !important;
  }}
  .st-key-range_filter button:hover,
  .st-key-appearance_toggle button:hover,
  .st-key-scope_picker button:hover {{
    background: var(--hover) !important;
    color: var(--hover-text) !important;
  }}
  .st-key-range_filter button[aria-checked="true"],
  .st-key-range_filter button[kind="segmented_controlActive"],
  .st-key-appearance_toggle button[aria-checked="true"],
  .st-key-appearance_toggle button[kind="segmented_controlActive"],
  .st-key-scope_picker button[aria-checked="true"],
  .st-key-scope_picker button[kind="segmented_controlActive"] {{
    background: var(--card-2) !important;
    color: var(--active-text) !important;
    font-weight: 600 !important;
    box-shadow: var(--pill-shadow);
  }}

  /* The date-range bar, sized to the appearance toggle: same 33px overall,
     same 25px buttons. It keeps its own .84rem text -- only the height is
     being matched -- so the line-height comes down to 1.2, without which the
     larger type overflows the shorter button. The explicit height is the part
     that bites: Streamlit pins these buttons to 2rem and the shared rule above
     clears min-height but not height. */
  .st-key-range_filter {{
    padding: 3px 6px !important;
  }}
  .st-key-range_filter button {{
    padding: 2px 14px !important;
    height: 25px !important;
    line-height: 1.2 !important;
  }}

  /* Sidebar spacing. Streamlit gives a section heading 12px above and 16px
     below, on top of the 16px gap its vertical block already puts between
     every element -- three lots of space doing one job. Trimming the heading's
     own padding pulls both "Trade type" and "Filters" up towards what they
     label; the caption rule closes the gap under the ownership line and under
     the pooled-scope note. */
  [data-testid="stSidebar"] h3 {{
    padding-top: 2px !important;
    padding-bottom: 8px !important;
  }}
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
    margin-bottom: 4px !important;
  }}
  /* The pooled-scope note describes the picker above it, but Streamlit's
     uniform 16px block gap left it 22px below the picker and 2px above the
     "Filters" heading -- reading as a label for the wrong control. Pulled up
     to sit 4px under the picker instead.

     This tracks the picker's margin-bottom: the note starts below it, so the
     two move together. 30 (that margin) + 16 (the block gap) - 4 (where the
     note should land) = 42. */
  .st-key-scope_note {{
    margin-top: -42px;
  }}
  /* And taken out of the flow entirely, so everything below it stays put:
     Filters sits in the same place whether a note is showing or not, which it
     did not when the note was a normal block pushing it down 26px.

     The zeroing goes on the unkeyed layout wrapper Streamlit puts around the
     container -- that, not the container, is the flex child the 16px gap acts
     on. The -16px cancels the gap this extra child would otherwise introduce.
     NB the note therefore overprints the space below it: it fits because it is
     one short line. A membership string long enough to wrap would collide with
     the Filters heading. */
  [data-testid="stLayoutWrapper"]:has(> .st-key-scope_note) {{
    height: 0;
    overflow: visible;
    margin-bottom: -16px;
  }}

  /* "Trade type" alone needs the space put back -- the rule above leaves it
     flush against the caption. 24px is the gap the nav divider already keeps
     above that caption, so the three stack on one rhythm; the picker's
     margin-bottom below is tuned to land "Filters" on the same 24. */
  .st-key-scope_heading h3 {{
    padding-top: 24px !important;
  }}

  /* The scope picker is the same control stacked vertically: seven options
     will not fit across a 300px sidebar. It overrides the shared rules above,
     which size the horizontal toggles to hug their buttons -- this one fills
     the sidebar and left-aligns its labels so the list reads as a menu rather
     than a row of centred pills. */
  .st-key-scope_picker {{
    width: 100% !important;
    align-self: stretch !important;
    /* 30 + the block's own 16px gap + the heading's 2px padding = 48px of
       clearance below the picker, whatever is selected. Doubled from 24 at the
       user's request; it also lifts the pooled-scope note clear of the
       "Filters" heading it overprints into. */
    margin-bottom: 30px;
  }}
  /* The buttons live in a flex row inside the group; turning it into a column
     is what stacks them. The group's own width comes from width="stretch" on
     the widget (see views/common.py), not from here. The gap overrides the 2px
     the horizontal toggles use: stacked, eight of them, the same gap reads as
     a looser list than it does across a row of three. */
  .st-key-scope_picker [data-testid="stButtonGroup"] > div {{
    flex-direction: column !important;
    gap: 1px;
  }}
  /* The label sits in its own flex child that centres itself, so aligning the
     button alone leaves the text centred. */
  .st-key-scope_picker button > div {{
    justify-content: flex-start !important;
    width: 100%;
  }}
  .st-key-scope_picker button {{
    width: 100% !important;
    justify-content: flex-start !important;
    padding: 6px 12px !important;
    /* Streamlit pins these buttons to height:2rem; without this the vertical
       padding above has no visible effect. */
    height: auto !important;
  }}
  /* Pin the appearance toggle to the foot of the sidebar.

     margin-top:auto only pushes an item down if its flex parent has spare
     height to give, and Streamlit's sidebar wrappers are display:block sized
     to their content -- so the chain from stSidebarUserContent down has to be
     made a filling flex column first. The auto margin then goes on the
     wrapper that actually holds the toggle, not the toggle itself, because
     that wrapper is the flex item in the sidebar's element list.

     This keeps the toggle in normal flow, so on a page with a long filter
     list it sits after the filters instead of overlapping them. */
  /* The seam. The sidebar sits one plane below the page (see sidebar_bg), but
     that step is only 8 levels, so this hairline is what makes the boundary
     read as an edge rather than a smudge. Streamlit's own showSidebarBorder
     draws nothing in this layout, hence doing it here.

     Scoped to the expanded state: collapsing the sidebar takes its width to
     zero, and an unscoped border would survive as a stray 1px line down the
     left edge of the window. */
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    border-right: 1px solid var(--edge) !important;
  }}
  /* Streamlit reserves 96px at the foot of the sidebar for a chat input this
     app does not have, which leaves a long filter list ending in a void. */
  section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    padding-bottom: 12px !important;
  }}
  /* The toggle is lifted into the sidebar's header band, above the page nav.
     Streamlit renders that nav in its own block ahead of all user content, so
     no call order can put anything above it -- positioning is the only way in.
     The header is 60px tall and empty apart from the collapse button on the
     right, so this drops into free space rather than displacing anything.

     stSidebarContent is already position:relative and is not the scrolling
     box (user content is), so the toggle both anchors to the sidebar and
     stays put while a long filter list scrolls under it. */
  section[data-testid="stSidebar"] .st-key-appearance_toggle {{
    position: absolute;
    top: 13px;
    left: 20px;
    z-index: 1;
    margin-bottom: 0 !important;
    /* Shorter than the dashboard's date-range bar it otherwise matches: this
       one is persistent chrome rather than a control you read, so it earns
       less height. Sizes only -- the styling is the shared rule above. */
    padding: 3px 4px !important;
  }}
  /* Taking the toggle out of flow leaves its wrapper as an empty flex item,
     which would still claim the sidebar list's 16px row gap above the
     caption. display:contents removes the wrapper's box without hiding the
     positioned child the way display:none would. */
  section[data-testid="stSidebar"]
    [data-testid="stLayoutWrapper"]:has(> .st-key-appearance_toggle) {{
    display: contents;
  }}
  section[data-testid="stSidebar"] .st-key-appearance_toggle button {{
    padding: 3px 12px !important;
    font-size: .78rem !important;
    line-height: 1.35 !important;
    /* The one that actually matters: Streamlit pins these buttons to a fixed
       height:2rem. The shared rule above clears min-height but not height, so
       without this the padding and line-height below have no visible effect
       at all -- the button stays 32px whatever they say. */
    height: auto !important;
  }}

  /* Read-only dashboard tables: hide the hover toolbar (column visibility,
     CSV download, search, fullscreen). The journal grid keeps its toolbar --
     search and download earn their place there. */
  .st-key-glance_table [data-testid="stElementToolbar"],
  .st-key-recent_table [data-testid="stElementToolbar"] {{
    display: none !important;
  }}

  .panel-title {{
    font-size: .78rem;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: .05em;
    text-transform: uppercase;
    margin: 4px 0 10px 2px;
  }}

  /* Same 2.25rem as the h1 rule above -- keep the two in step. */
  .hero-name {{ font-size: 2.25rem; font-weight: 680; letter-spacing: -.03em; margin: 0; }}
  .hero-sub  {{ color: var(--muted); font-size: .95rem; margin: 4px 0 20px 0; }}

  .pos {{ color: var(--green); }}
  .neg {{ color: var(--red); }}
  .neutral {{ color: var(--muted); }}

  /* Calendar */
  .cal-head {{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom: 12px;
  }}
  .cal-title {{ font-size: 1.05rem; font-weight: 620; }}
  /* Stays 1fr -- i.e. minmax(auto, 1fr). The tracks are content-floored on
     purpose: this grid is what gives the whole right-hand column its width,
     and dropping the floor to minmax(0, 1fr) collapses the column chain above
     it to nothing. Equal cells are achieved by making the *contents* a
     constant width instead, on .cal-date and .cal-tag below. */
  .cal-grid {{
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px;
  }}
  .cal-dow {{
    text-align: center; font-size: .7rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: .06em; padding-bottom: 4px;
  }}
  .cal-day {{
    min-height: 62px; border-radius: 10px; padding: 6px 8px;
    border: 1px solid var(--edge); background: var(--card-2);
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .cal-day.empty {{ background: transparent; border-color: transparent; }}
  .cal-day.blank {{ opacity: .35; }}
  .cal-day.win {{
    background: rgba(34,197,94,{p["tint"]}); border-color: rgba(34,197,94,{p["tint_edge"]});
  }}
  .cal-day.loss {{
    background: rgba(239,68,68,{p["tint"]}); border-color: rgba(239,68,68,{p["tint_edge"]});
  }}
  .cal-day.flat {{
    background: var(--flat-tint); border-color: var(--flat-edge);
  }}
  /* Day number hard left, trade-type pill centred in whatever is left over --
     so the pill sits in the same place whether the date is one digit or two,
     and neither pushes the other around. */
  .cal-num {{
    font-size: .72rem; color: var(--muted);
    display: flex; align-items: center; gap: 2px;
    /* Room for a date plus a pill, held whether or not this day has either.
       The tracks are content-sized, so without this the columns holding a
       traded day came out more than twice the width of the ones that did not
       -- the grid was uneven long before anything was tagged. Raised from
       3.6rem with the wider "Evaluation" pill: below 4.4 the untagged columns
       fall short of the tagged ones again. */
    min-width: 4.4rem;
  }}
  /* Both fixed, and that is the whole trick: with the date and the pill each
     a constant width, every cell's top row measures the same whether the date
     is 1 or 2 digits and whatever the tag says -- so no cell can out-measure
     its neighbours and stretch its column. 1.15em fits "31"; 3.9em fits
     FUNDED, the longest of the three tags. */
  .cal-date {{ flex: 0 0 1.15em; }}
  .cal-mark {{ flex: 1 1 auto; display: flex; justify-content: center; min-width: 0; }}
  /* Names the trade type a cell's R came from. Deliberately typographic
     rather than a new colour: green and red already mean exactly one thing
     here, and a third hue would dilute that. */
  .cal-tag {{
    /* .48rem, down from .55: the width is shared by all three labels, and at
       the larger size "EVALUATION" forced 92px cells that overran the panel.
       At this size it needs 53px against the 42 the short labels used, which
       the existing 88px cells already had room for -- the whole grid grows by
       4px. */
    font-size: .48rem; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--muted);
    border: 1px solid var(--edge); border-radius: 4px;
    padding: 0 3px; white-space: nowrap;
    width: 5.9em; text-align: center; box-sizing: content-box;
  }}
  .cal-r {{ font-size: .92rem; font-weight: 650; line-height: 1.1; }}
  .cal-n {{ font-size: .66rem; color: var(--muted); }}
  /* The legend is the last thing in the panel, and Streamlit hangs a
     margin-bottom:-16px on markdown containers -- which eats the card's own
     bottom padding and leaves the legend sitting on the border. Padding here
     rather than margin: margin would collapse into the container's. 16px to
     match the inset on the other three sides. */
  .cal-legend {{
    display:flex; gap:16px; margin-top:12px; padding-bottom:16px;
    font-size:.72rem; color:var(--muted);
  }}
  /* Only rendered when a trade lands on a weekend, which the grid has no
     column for. Sits under the legend rather than in it -- it is a warning
     about missing data, not a key to what is drawn. */
  .cal-note {{
    font-size: .7rem; color: var(--muted); margin-top: -8px; padding-bottom: 16px;
  }}
  .swatch {{
    display:inline-block; width:10px; height:10px; border-radius:3px;
    margin-right:6px; vertical-align:middle;
  }}
</style>
"""


def inject() -> None:
    st.markdown(_css(mode()), unsafe_allow_html=True)


def _css_attr(value: str) -> str:
    """Escape a tag name for use inside a quoted CSS attribute selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def tag_chip_css(palette: dict[str, str]) -> None:
    """Colour `st.multiselect` chips per tag, to match the grid's.

    The widget paints every selected chip in the theme's primary colour, so
    the drawer showed confluences, DoL and entry model all in the same green
    while the table beside it coloured them per tag. `st.multiselect` takes no
    colour argument -- but each chip carries its own value in `aria-label`,
    which is enough to address them one at a time.

    `palette` is {tag name: colour}, i.e. exactly what queries.tag_palette
    returns, so the colours come from the database rather than a second list
    kept in step by hand.
    """
    rules = [
        # Pill, matching the shape the grid draws. The widget's own 6px radius
        # made the same vocabulary look like two different chip systems on
        # either side of the drawer.
        '[data-testid="stMultiSelectTagsContainer"] span[data-tag] {'
        " border-radius: 999px !important; }"
    ]
    rules += [
        f'[data-testid="stMultiSelectTagsContainer"] '
        f'span[data-tag][aria-label="{_css_attr(name)}"] {{'
        f" background-color: {colour} !important; }}"
        for name, colour in palette.items()
        if colour
    ]
    st.markdown("<style>" + "\n".join(rules) + "</style>", unsafe_allow_html=True)


def _set_browser_theme(want: str | None) -> None:
    """Point Streamlit's own theme at `want` ("dark"/"light") and reload.

    Streamlit has no server-side setter for the theme -- the frontend reads the
    choice from localStorage when the page loads -- so this reaches across from
    a components iframe (same origin, so the parent window is accessible) and
    then reloads to make it take. The write is idempotent: if the stored value
    already matches, nothing happens and there is no reload loop.

    `want=None` means "only seed the default": a browser that has never chosen
    gets dark, but a deliberate choice of light is left alone.
    """
    target = "null" if want is None else f'"{want.capitalize()}"'
    components.html(
        f"""
        <script>
          (function () {{
            try {{
              var ls = window.parent.localStorage;
              var here = window.parent.location.pathname;
              var paths = {list(PAGE_PATHS)!r}.concat([here]);
              var key = function (p) {{ return "stActiveTheme-" + p + "-v2"; }};
              var stored = ls.getItem(key(here));
              var want = {target};
              if (want === null) {{
                if (stored !== null) return;   // respect an existing choice
                want = "Dark";
              }}
              var wanted = JSON.stringify(want);
              if (stored === wanted) return;   // already there; do not reload
              paths.forEach(function (p) {{ ls.setItem(key(p), wanted); }});
              window.parent.location.reload();
            }} catch (e) {{ /* nothing sensible to do in a themeing script */ }}
          }})();
        </script>
        """,
        height=0,
    )


def appearance_toggle() -> None:
    """Light/dark switch. Call it before any other sidebar content: it renders
    in call order, and being first is what keeps it in the same place on every
    page rather than trailing whatever filters that page adds.

    Deliberately the same control and styling as the dashboard's date-range
    picker, at a smaller height. Switching costs a page reload, because that is
    the only moment Streamlit reads the theme -- filters and any open trade
    reset with it.
    """
    active = mode()
    with st.sidebar.container(key="appearance_toggle"):
        picked = st.segmented_control(
            "Appearance", ["Dark", "Light"],
            default=active.capitalize(), key="appearance_mode",
            label_visibility="collapsed",
        )

    # Compare against what the browser is actually rendering rather than a
    # session flag: a reload resets session state but not the stored theme.
    want = (picked or active).lower()
    _set_browser_theme(want if want != active else None)


@contextmanager
def panel(title: str, *, key: str | None = None):
    """A titled card. Uses a real bordered container rather than raw <div>s --
    Streamlit closes stray tags at the element boundary, so an opened <div>
    never actually wraps the widgets that follow it.

    `key` emits an st-key- CSS class so a panel can be styled individually.
    """
    box = st.container(border=True, key=key)
    with box:
        st.markdown(f'<div class="panel-title">{html.escape(title)}</div>',
                    unsafe_allow_html=True)
        yield box


def hero(greeting: str, subtitle: str) -> None:
    """The dashboard's opening line. Takes the whole greeting rather than a
    name, so an unnamed journal reads "Welcome" instead of "Welcome, "."""
    st.markdown(
        f'<div class="hero-name">{html.escape(greeting)}</div>'
        f'<div class="hero-sub">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True,
    )


def calendar_html(year: int, month: int, days: dict[str, dict]) -> str:
    """A month grid coloured by net R.

    `days` maps 'YYYY-MM-DD' to {'net_r', 'n', 'wins', 'losses', 'bes'}, plus
    an optional 'tag' string naming what kind of day it was ('Funded', 'Paper',
    'Eval') -- a day holds one trade type, so the tag identifies the day rather
    than flagging an exception to it.
    Green means the day finished net positive in R, red net negative, grey a
    day that was traded and finished flat. A day with no trades is left blank
    rather than coloured, so absence never reads as a result.

    Monday to Friday only -- no trades are taken at the weekend, and the two
    dead columns were costing a fifth of the grid's width. Should a weekend
    trade ever be logged it would have no cell to land in, so rather than let
    it vanish the grid says so underneath.
    """
    calendar.setfirstweekday(calendar.MONDAY)
    weeks = calendar.monthcalendar(year, month)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    cells = [f'<div class="cal-dow">{n}</div>' for n in names]
    for week in weeks:
        weekdays = week[:len(names)]
        # A month can begin on a Saturday or end on a Sunday, leaving a row
        # with nothing but weekend in it. Dropping it avoids an empty band.
        if not any(weekdays):
            continue
        for day in weekdays:
            if day == 0:
                cells.append('<div class="cal-day empty"></div>')
                continue
            key = f"{year:04d}-{month:02d}-{day:02d}"
            entry = days.get(key)
            if entry is None:
                cells.append(
                    f'<div class="cal-day blank">'
                    f'<span class="cal-num"><span class="cal-date">{day}</span>'
                    f'</span></div>')
                continue
            net = entry["net_r"]
            state = "win" if net > 0 else "loss" if net < 0 else "flat"
            tone = "pos" if net > 0 else "neg" if net < 0 else "neutral"
            label = "trade" if entry["n"] == 1 else "trades"

            marker = entry.get("tag")
            tip = (f'{key}: {entry["wins"]}W {entry["losses"]}L {entry["bes"]}BE'
                   f'{f" ({marker.lower()})" if marker else ""}')
            # The pill goes in its own flex cell rather than trailing the date,
            # which is what keeps it centred in the leftover width instead of
            # being shunted along by a two-digit day.
            tag = (f'<span class="cal-mark"><span class="cal-tag">{marker}</span></span>'
                   if marker else "")
            cells.append(
                f'<div class="cal-day {state}" title="{tip}">'
                f'<span class="cal-num"><span class="cal-date">{day}</span>{tag}</span>'
                f'<span class="cal-r {tone}">{net:+.1f}R</span>'
                f'<span class="cal-n">{entry["n"]} {label}</span></div>'
            )

    legend = (
        '<div class="cal-legend">'
        f'<span><span class="swatch" style="background:rgba(34,197,94,.5)"></span>Up in R</span>'
        f'<span><span class="swatch" style="background:rgba(239,68,68,.5)"></span>Down in R</span>'
        f'<span><span class="swatch" style="background:var(--swatch-flat)"></span>Traded, flat</span>'
        "</div>"
    )

    # Only ever shown if the no-weekend-trading assumption is broken. Silent
    # normally; the alternative is a day's R quietly missing from the month.
    stranded = sorted(
        key for key in days
        if date.fromisoformat(key).weekday() >= len(names)
        and key.startswith(f"{year:04d}-{month:02d}")
    )
    if stranded:
        listed = ", ".join(k[-2:].lstrip("0") for k in stranded)
        legend += (f'<div class="cal-note">Not shown: weekend '
                   f'{"trades" if len(stranded) > 1 else "trade"} on the {listed} — '
                   "this grid runs Monday to Friday.</div>")

    return f'<div class="cal-grid">{"".join(cells)}</div>{legend}'


def month_title(year: int, month: int) -> str:
    return f"{date(year, month, 1):%B %Y}"
