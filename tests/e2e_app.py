"""App exercised by the packaged, real-input Playwright suite."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import streamlit_dnd
from streamlit_dnd import apply_move, dnd

STORE = Path(".streamlit_dnd_e2e_state.json")
DEFAULT_BOARD = {"e2e_left": ["Alpha", "Bravo"], "e2e_right": []}


def load_board():
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {key: list(value) for key, value in DEFAULT_BOARD.items()}


def save_board():
    STORE.write_text(json.dumps(st.session_state["e2e_board"]))


if "e2e_board" not in st.session_state:
    st.session_state["e2e_board"] = load_board()
if "e2e_frames" not in st.session_state:
    st.session_state["e2e_frames"] = {
        "frames_left": {
            "df1": pd.DataFrame({"value": [1, 2]}),
            "df2": pd.DataFrame({"value": [3, 4]}),
        },
        "frames_right": {},
    }
if "e2e_legacy" not in st.session_state:
    st.session_state["e2e_legacy"] = ["One", "Two", "Three"]
if "e2e_clicked" not in st.session_state:
    st.session_state["e2e_clicked"] = "none"

st.title("streamlit-dnd packaged E2E")
st.caption(f"PACKAGE_VERSION={streamlit_dnd.__version__}")
st.caption(f"PACKAGE_FILE={Path(streamlit_dnd.__file__).resolve()}")

left_col, right_col = st.columns(2)
for column, container_key, title in (
    (left_col, "e2e_left", "Available"),
    (right_col, "e2e_right", "Selected"),
):
    with column, st.container(key=container_key, border=True):
        # This is deliberately inside the dnd container. It must stay fixed and
        # must not shift the item indices sent to Python.
        st.subheader(title)
        for item in st.session_state["e2e_board"][container_key]:
            with st.container(key=f"board_card_{item.lower()}", border=True):
                st.write(item)
                if st.button(f"Select {item}", key=f"select_{item.lower()}"):
                    st.session_state["e2e_clicked"] = item

board_event = dnd(
    "e2e_left",
    "e2e_right",
    placeholder="Drop a card here",
    key="e2e_board_dnd",
)
if board_event:
    apply_move(board_event, st.session_state["e2e_board"])
    save_board()
    st.rerun()

st.caption("STATE_BOARD_LEFT=" + "|".join(st.session_state["e2e_board"]["e2e_left"]))
st.caption("STATE_BOARD_RIGHT=" + "|".join(st.session_state["e2e_board"]["e2e_right"]))
st.caption("STATE_CLICKED=" + st.session_state["e2e_clicked"])

st.header("Named DataFrames")
frames_left, frames_right = st.columns(2)
for column, container_key in (
    (frames_left, "frames_left"),
    (frames_right, "frames_right"),
):
    with column, st.container(key=container_key, border=True):
        st.subheader(container_key.replace("_", " ").title())
        for frame_key, frame in st.session_state["e2e_frames"][container_key].items():
            with st.container(key=f"frame_card_{frame_key}", border=True):
                st.write(frame_key)
                st.dataframe(frame)

frames_event = dnd(
    "frames_left",
    "frames_right",
    handle=False,
    placeholder="Drop a DataFrame here",
    key="e2e_frames_dnd",
)
if frames_event:
    apply_move(frames_event, st.session_state["e2e_frames"])
    st.rerun()

st.caption(
    "STATE_FRAMES_LEFT=" + "|".join(st.session_state["e2e_frames"]["frames_left"])
)
st.caption(
    "STATE_FRAMES_RIGHT=" + "|".join(st.session_state["e2e_frames"]["frames_right"])
)

st.header("Legacy unkeyed mode")
with st.container(key="legacy_items", border=True):
    for item in st.session_state["e2e_legacy"]:
        st.write(item)

legacy_event = dnd(
    "legacy_items",
    cross=False,
    item_mode="all",
    handle=False,
    key="e2e_legacy_dnd",
)
if legacy_event:
    apply_move(legacy_event, st.session_state["e2e_legacy"])
    st.rerun()

st.caption("STATE_LEGACY=" + "|".join(st.session_state["e2e_legacy"]))
