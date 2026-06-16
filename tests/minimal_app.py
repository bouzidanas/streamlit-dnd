"""Minimal app to test the streamlit_dnd module wiring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from streamlit_dnd import apply_move, dnd

st.title("dnd module test")

# --- session state ------------------------------------------------------------
if "list_a" not in st.session_state:
    st.session_state.list_a = ["Alpha", "Bravo", "Charlie"]
if "list_b" not in st.session_state:
    st.session_state.list_b = ["Delta", "Echo"]

# --- render -------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("List A")
    with st.container(key="cont_a", border=True):
        for name in st.session_state.list_a:
            with st.container(key=f"item_{name}", border=True):
                st.write(name)

with col2:
    st.subheader("List B")
    with st.container(key="cont_b", border=True):
        for name in st.session_state.list_b:
            with st.container(key=f"item_{name}", border=True):
                st.write(name)

# --- dnd ----------------------------------------------------------------------
event = dnd("cont_a", "cont_b", cross=True, indicator="line", color="#00c853")

if event:
    st.session_state.last_event = (
        f"{event.item_key}: {event.from_container}[{event.from_index}] -> "
        f"{event.to_container}[{event.to_index}]"
    )
    apply_move(
        event,
        {"cont_a": st.session_state.list_a, "cont_b": st.session_state.list_b},
    )
    st.rerun()

st.write("Order A:", st.session_state.list_a)
st.write("Order B:", st.session_state.list_b)
if "last_event" in st.session_state:
    st.write("Last event:", st.session_state.last_event)
