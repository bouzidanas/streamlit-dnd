"""streamlit-dnd demo.

Run with:
    streamlit run demo.py

Demonstrates:
  * Same-container reordering and cross-container drag-and-drop
  * Source-only / destination-only container rules
  * Grab-anywhere, corner-handle, and border-handle drag modes (with a
    configurable handle corner and icon)
  * Three destination indicators (insertion line / spot highlight / ghost
    preview) with a configurable color, switchable from the sidebar
  * Persistence of user-made arrangements: session state is the working
    copy, and every change is mirrored to a JSON file so arrangements
    survive page refreshes and app restarts
  * Draggable items containing many different Streamlit component types
"""

import copy
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_dnd import apply_move, dnd

st.set_page_config(page_title="streamlit-dnd demo", layout="wide")

# ==============================================================================
# Persistence: arrangements survive page refreshes and app restarts.
#
# st.session_state is wiped whenever the browser starts a new session (page
# refresh, new tab, server restart), so it alone can't persist arrangements.
# The pattern here:
#   * st.session_state holds the working copy (fast, per-session)
#   * every drop is mirrored to a JSON file on disk
#   * a new session seeds its session state from that file (or defaults)
#   * the reset button deletes the file and restores defaults
# ==============================================================================

_STORE_PATH = Path(__file__).parent / ".demo_arrangements.json"

_DEFAULTS = {
    "ordering": {
        "ordering_list": [
            "intro_block",
            "metric_block",
            "chart_block",
            "code_block",
            "slider_block",
            "table_block",
        ],
    },
    "kanban": {
        "todo": ["Write spec", "Design schema", "Set up CI"],
        "doing": ["Build API"],
        "done": ["Project kickoff"],
    },
    "playlist": {
        "library": [
            "Bohemian Rhapsody",
            "Stairway to Heaven",
            "Hotel California",
            "Imagine",
        ],
        "queue": ["Hey Jude"],
    },
    "widgets_board": {
        "board_left": ["metric_card", "chart_card", "text_card"],
        "board_right": ["slider_card", "table_card"],
    },
}


def _load_arrangements() -> dict:
    """Read saved arrangements from disk, falling back to defaults."""
    if _STORE_PATH.exists():
        try:
            saved = json.loads(_STORE_PATH.read_text())
            # Start from defaults so boards added in newer demo versions
            # still appear even if the saved file predates them.
            merged = copy.deepcopy(_DEFAULTS)
            merged.update({k: v for k, v in saved.items() if k in _DEFAULTS})
            return merged
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/unreadable file: fall back to defaults
    return copy.deepcopy(_DEFAULTS)


def save_arrangements() -> None:
    """Mirror the current arrangements to disk (atomic write)."""
    data = {k: st.session_state[k] for k in _DEFAULTS}
    tmp = _STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_STORE_PATH)


def reset_arrangements() -> None:
    """Delete saved state and restore the default arrangements."""
    _STORE_PATH.unlink(missing_ok=True)
    for k, v in copy.deepcopy(_DEFAULTS).items():
        st.session_state[k] = v


# Seed session state at the start of every new session (first run after a
# page refresh / new tab / app restart).
if "_arrangements_loaded" not in st.session_state:
    for _k, _v in _load_arrangements().items():
        st.session_state[_k] = _v
    st.session_state._arrangements_loaded = True

# ==============================================================================
# Sidebar: dnd appearance / behavior controls
# ==============================================================================

st.sidebar.title("Drag & Drop settings")

# --- Indicator color: a compact swatch + a hex field beside it, kept in sync
# so you can either click the picker or type a hex code. ------------------------
if "indicator_color" not in st.session_state:
    st.session_state.indicator_color = "#FF4B4B"
if "indicator_color_text" not in st.session_state:
    st.session_state.indicator_color_text = "#FF4B4B"


def _sync_color_from_text() -> None:
    val = st.session_state.indicator_color_text.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", val):
        st.session_state.indicator_color = val.upper()
    # Reflect the canonical value back (also tidies up bad input on next run).
    st.session_state.indicator_color_text = st.session_state.indicator_color


def _sync_text_from_picker() -> None:
    st.session_state.indicator_color_text = st.session_state.indicator_color

st.sidebar.write("#### Indicator color")

with st.sidebar.container(horizontal=True, vertical_alignment="bottom"):
    color = st.color_picker(
        "Indicator color",
        key="indicator_color",
        on_change=_sync_text_from_picker,
        label_visibility="collapsed",
    )
    st.text_input(
        "Indicator color",
        key="indicator_color_text",
        on_change=_sync_color_from_text,
        width="stretch",
        label_visibility="collapsed",
    )

st.sidebar.write("#### Destination indicator")

indicator = st.sidebar.radio(
    "Destination indicator",
    options=["line", "highlight", "ghost"],
    index=2,  # default to ghost preview
    format_func=lambda v: {
        "line": "Insertion line (bright line between items)",
        "highlight": "Spot highlight (tint the element being displaced)",
        "ghost": "Ghost preview (insert a live copy at the drop position)",
    }[v],
    key="indicator_choice",
    label_visibility="collapsed",
)

st.sidebar.write("#### Drag handle")

handle_style = st.sidebar.radio(
    "Drag handle",
    options=["off", "corner", "border"],
    index=2,  # default to border handle
    format_func=lambda v: {
        "off": "Off — grab items anywhere",
        "corner": "Corner — grab from an icon",
        "border": "Border — grab from the edges",
    }[v],
    key="handle_style",
    help=(
        "Use a handle when items hold buttons or inputs, so those stay usable. "
        "Corner puts a small grip icon in one corner; Border lets you grab the "
        "item from a band around its edge while the interior stays free."
    ),
    label_visibility="collapsed",
)

# Defaults used when a handle option doesn't apply (kept so the dnd() calls
# below always have a value to pass).
handle_corner = "top-right"
handle_icon = "⠿"

if handle_style == "corner":
    handle_corner = st.sidebar.selectbox(
        "Handle corner",
        options=["top-right", "top-left", "bottom-right", "bottom-left"],
        key="handle_corner_choice",
    )
    icon_preset = st.sidebar.selectbox(
        "Handle icon",
        options=[
            "⠿",
            "≡",
            "✥",
            ":material/drag_indicator:",
            ":material/drag_handle:",
            ":material/open_with:",
            "Custom…",
        ],
        help=(
            "Any text or emoji, or a Streamlit Material icon written as "
            "`:material/<name>:` (the same syntax `st.button(icon=...)` uses)."
        ),
        key="handle_icon_preset",
    )
    if icon_preset == "Custom…":
        handle_icon = st.sidebar.text_input(
            "Custom icon",
            value="🖐️",
            help="Text, an emoji, or `:material/<name>:`.",
            key="handle_icon_custom",
        )
    else:
        handle_icon = icon_preset

# Map the sidebar choice to the dnd() `handle` argument:
#   off → False (grab anywhere), corner → True (icon handle), border → "border".
handle_arg = {"off": False, "corner": True, "border": "border"}[handle_style]
# Whether any handle is active (used for the widget-board hint below).
handle_on = handle_style != "off"

if st.sidebar.button("↺ Reset all arrangements", width="stretch"):
    reset_arrangements()
    st.rerun()

st.title("streamlit-dnd")
st.write(
    "Drag direct children of Streamlit containers to reorder them or move them between containers. Arrangements are saved to disk and survive page refreshes."
)


def render_persisted(label: str, data) -> None:
    """Show one section's persisted state (working copy + on-disk mirror)."""
    with st.expander(f"🔍 Persisted state — {label}"):
        st.caption(
            "Working copy lives in `st.session_state`; mirrored to "
            f"`{_STORE_PATH.name}` "
            f"({'saved on disk' if _STORE_PATH.exists() else 'not saved yet — make a move'})."
        )
        st.json(data)


# ==============================================================================
# Example 0: Re-ordering — one container, reorder only, every item different
# ==============================================================================

# Each block renders a different kind of Streamlit content; the block id is
# what gets persisted/reordered in session state.
def render_ordering_block(block_id: str) -> None:
    if block_id == "intro_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 📄 Markdown")
            st.markdown(
                "A plain **markdown** block. Drag any of these blocks to "
                "rearrange the page — like reordering sections of a report."
            )
    elif block_id == "metric_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 📊 Metrics")
            m1, m2, m3 = st.columns(3)
            m1.metric("Temperature", "21 °C", "1.2 °C")
            m2.metric("Humidity", "47%", "-3%")
            m3.metric("Wind", "12 km/h", "+2 km/h")
    elif block_id == "chart_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 📈 Area chart")
            st.area_chart(
                pd.DataFrame({"sales": [3, 6, 4, 8, 7, 9], "cost": [2, 3, 3, 4, 5, 5]}),
                height=160,
            )
    elif block_id == "code_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 💻 Code")
            st.code(
                'event = dnd("ordering_list", cross=False)\n'
                "if event:\n"
                "    apply_move(event, st.session_state.ordering)\n"
                "    save_arrangements()  # mirror to disk\n"
                "    st.rerun()",
                language="python",
            )
    elif block_id == "slider_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 🎚️ Slider")
            st.slider(
                "Drag the thumb, then drag the whole block",
                0,
                100,
                35,
                key="ordering_slider",
            )
            st.caption(
                "An interactive widget. With the default border handle the "
                "slider still works — grab the block's edge to move it."
            )
    elif block_id == "table_block":
        with st.container(key=f"order_{block_id}", border=True):
            st.markdown("##### 🗂️ Table")
            st.table(
                pd.DataFrame(
                    {"step": ["extract", "transform", "load"], "ms": [120, 340, 80]}
                )
            )


with st.container():
    st.header("Re-ordering (single container)")
    st.markdown(
        "One container, **re-ordering only** (`cross=False`). Each block holds a "
        "different kind of Streamlit content — drag them into whatever order you like."
    )

    with st.container(key="ordering_list", border=True):
        for block_id in st.session_state.ordering["ordering_list"]:
            render_ordering_block(block_id)

    ordering_event = dnd(
        "ordering_list",
        cross=False,
        handle=handle_arg,
        handle_corner=handle_corner,
        handle_icon=handle_icon,
        indicator=indicator,
        color=color,
        key="dnd_ordering",
    )

    if ordering_event:
        apply_move(ordering_event, st.session_state.ordering)
        save_arrangements()
        st.rerun()

    st.caption(
        "Order: "
        + " → ".join(
            b.replace("_block", "") for b in st.session_state.ordering["ordering_list"]
        )
    )
    render_persisted("Re-ordering", st.session_state.ordering)

# ==============================================================================
# Example 1: Kanban — free cross-container dnd, simple cards
# ==============================================================================

with st.container():
    st.header("Kanban (cross-container)")
    st.markdown(
        "Cards can be reordered within a column **and** moved between any columns "
        "(`cross=True`)."
    )
    cols = st.columns(3)
    column_meta = [("todo", "📝 To do"), ("doing", "⚙️ Doing"), ("done", "✅ Done")]

    for col, (col_key, col_title) in zip(cols, column_meta):
        with col:
            st.subheader(col_title)
            with st.container(key=f"kanban_{col_key}", border=True):
                for card in st.session_state.kanban[col_key]:
                    with st.container(key=f"kanban_card_{card}", border=True):
                        st.markdown(f"**{card}**")
                        st.caption(f"in {col_title}")

    kanban_event = dnd(
        "kanban_todo",
        "kanban_doing",
        "kanban_done",
        cross=True,
        handle=handle_arg,
        handle_corner=handle_corner,
        handle_icon=handle_icon,
        indicator=indicator,
        color=color,
        key="dnd_kanban",
    )

    if kanban_event:
        apply_move(
            kanban_event,
            {f"kanban_{k}": v for k, v in st.session_state.kanban.items()},
        )
        save_arrangements()
        st.rerun()

    render_persisted("Kanban", st.session_state.kanban)

# ==============================================================================
# Example 2: Playlist — library is source-only, queue is destination-only
# ==============================================================================

with st.container():
    st.header("Playlist (source → destination)")
    st.markdown(
        "The **library** is a *source*: you can drag songs out of it but not into it. "
        "The **queue** is a *destination*: songs can be dropped into it (and reordered "
        "within it, since it is also listed as a source)."
    )
    lib_col, queue_col = st.columns(2)

    with lib_col:
        st.subheader("📚 Library (drag out only)")
        with st.container(key="playlist_library", border=True):
            for song in st.session_state.playlist["library"]:
                with st.container(key=f"song_{song}", border=True):
                    st.markdown(f"🎶 **{song}**")

    with queue_col:
        st.subheader("Up next (drop here)")
        with st.container(key="playlist_queue", border=True):
            if not st.session_state.playlist["queue"]:
                st.caption("Queue is empty — drag songs here")
            for song in st.session_state.playlist["queue"]:
                with st.container(key=f"song_{song}", border=True):
                    st.markdown(f"🎶 **{song}**")

    playlist_event = dnd(
        "playlist_library",
        "playlist_queue",
        # library: items can leave; queue: items can be dropped + reordered.
        sources=["playlist_library", "playlist_queue"],
        destinations=["playlist_queue"],
        handle=handle_arg,
        handle_corner=handle_corner,
        handle_icon=handle_icon,
        indicator=indicator,
        color=color,
        key="dnd_playlist",
    )

    if playlist_event:
        apply_move(
            playlist_event,
            {
                "playlist_library": st.session_state.playlist["library"],
                "playlist_queue": st.session_state.playlist["queue"],
            },
        )
        save_arrangements()
        st.rerun()

    st.caption(
        f"Queue order: {' → '.join(st.session_state.playlist['queue']) or '(empty)'}"
    )
    render_persisted("Playlist", st.session_state.playlist)

# ==============================================================================
# Example 3: Widget board — draggable cards containing diverse components
# ==============================================================================

# Each card renders different Streamlit components; the card key doubles as
# the item identity used for persistence.
def render_card(card_id: str) -> None:
    if card_id == "metric_card":
        with st.container(key=f"card_{card_id}", border=True):
            st.markdown("##### 📊 Metrics")
            m1, m2 = st.columns(2)
            m1.metric("Revenue", "$12.4k", "+8%")
            m2.metric("Users", "1,205", "-2%")
    elif card_id == "chart_card":
        with st.container(key=f"card_{card_id}", border=True):
            st.markdown("##### 📈 Chart")
            st.line_chart(
                pd.DataFrame({"a": [1, 5, 2, 6, 3], "b": [3, 2, 4, 1, 5]}),
                height=160,
            )
    elif card_id == "text_card":
        with st.container(key=f"card_{card_id}", border=True):
            st.markdown("##### ✏️ Notes")
            st.text_area("Your notes", "Try dragging this whole card!", key="notes_input")
    elif card_id == "slider_card":
        with st.container(key=f"card_{card_id}", border=True):
            st.markdown("##### 🎚️ Controls")
            st.slider("Threshold", 0, 100, 40, key="threshold_slider")
            st.selectbox("Mode", ["Fast", "Accurate", "Balanced"], key="mode_select")
    elif card_id == "table_card":
        with st.container(key=f"card_{card_id}", border=True):
            st.markdown("##### 🗂️ Data")
            st.dataframe(
                pd.DataFrame(
                    {"task": ["a", "b", "c"], "status": ["done", "wip", "todo"]}
                ),
                hide_index=True,
                height=150,
            )


with st.container():
    st.header("Widget board (mixed components)")
    st.markdown(
        "Cards hold **interactive widgets** (sliders, text areas, charts, tables). "
        "Turn on a **drag handle** in the sidebar so the widgets stay usable while "
        "the cards remain draggable."
    )
    if not handle_on:
        st.info(
            "💡 Tip: pick a **drag handle** (Corner or Border) in the sidebar — "
            "otherwise dragging a slider also drags the card.",
            icon="💡",
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Left panel")
        with st.container(key="board_left", border=True):
            for card_id in st.session_state.widgets_board["board_left"]:
                render_card(card_id)
    with right:
        st.subheader("Right panel")
        with st.container(key="board_right", border=True):
            for card_id in st.session_state.widgets_board["board_right"]:
                render_card(card_id)

    widgets_event = dnd(
        "board_left",
        "board_right",
        cross=True,
        handle=handle_arg,
        handle_corner=handle_corner,
        handle_icon=handle_icon,
        indicator=indicator,
        color=color,
        key="dnd_widgets",
    )

    if widgets_event:
        apply_move(widgets_event, st.session_state.widgets_board)
        save_arrangements()
        st.rerun()

    render_persisted("Widget board", st.session_state.widgets_board)
