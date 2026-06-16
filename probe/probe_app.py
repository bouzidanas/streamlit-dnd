"""Probe app: keyed containers with keyed children of many types.

Used to discover the exact DOM structure of Streamlit 1.58 so we know
which elements to target for drag-and-drop.
"""

import pandas as pd
import streamlit as st

st.title("DOM Probe")

# --- Probe 1: bordered container with keyed buttons -------------------------
with st.container(key="probe_container_a", border=True):
    st.button("Button One", key="probe_btn_1")
    st.button("Button Two", key="probe_btn_2")
    st.button("Button Three", key="probe_btn_3")

# --- Probe 2: borderless container with mixed keyed children ----------------
with st.container(key="probe_container_b"):
    st.text_input("Some text", key="probe_text_1")
    st.markdown("Plain markdown (no key possible)")
    st.slider("A slider", 0, 10, key="probe_slider_1")
    st.checkbox("A checkbox", key="probe_check_1")

# --- Probe 3: container holding nested containers (cards) -------------------
with st.container(key="probe_container_c", border=True):
    with st.container(key="probe_card_1", border=True):
        st.write("Card 1 content")
        st.button("Card 1 button", key="probe_card1_btn")
    with st.container(key="probe_card_2", border=True):
        st.write("Card 2 content")
        st.metric("Metric", 42)

# --- Probe 4: horizontal container -------------------------------------------
with st.container(key="probe_container_d", horizontal=True):
    st.button("H One", key="probe_h_1")
    st.button("H Two", key="probe_h_2")

# --- Probe 5: columns inside keyed container ---------------------------------
with st.container(key="probe_container_e"):
    c1, c2 = st.columns(2)
    with c1:
        st.button("Col 1 btn", key="probe_col1_btn")
    with c2:
        st.button("Col 2 btn", key="probe_col2_btn")

# --- Probe 6: dataframe + chart children --------------------------------------
with st.container(key="probe_container_f", border=True):
    st.dataframe(pd.DataFrame({"a": [1, 2], "b": [3, 4]}), key="probe_df_1")
    st.expander("An expander").write("hello")

# --- Probe 7: a custom component iframe to test parent DOM access -------------
import streamlit.components.v1 as components

components.html(
    """
    <script>
    try {
        const parentDoc = window.parent.document;
        const found = parentDoc.querySelectorAll('[class*="st-key-"]').length;
        document.body.innerHTML = '<div id="probe-result">PARENT_ACCESS_OK keyed_elements=' + found + '</div>';
    } catch (e) {
        document.body.innerHTML = '<div id="probe-result">PARENT_ACCESS_BLOCKED: ' + e.message + '</div>';
    }
    </script>
    """,
    height=50,
)
