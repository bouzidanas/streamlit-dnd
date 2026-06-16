"""Probe: can iframes access parent DOM, and can a custom component send values back?"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.title("Iframe probe")

with st.container(key="iframe_probe_container", border=True):
    st.button("Target Button A", key="iframe_probe_btn_a")
    st.button("Target Button B", key="iframe_probe_btn_b")

# --- Path 1: components.html (srcdoc iframe) ---------------------------------
components.html(
    """
    <body>
    <div id="result1">PENDING</div>
    <script>
    window.addEventListener('load', function() {
        try {
            const n = window.parent.document.querySelectorAll('[class*="st-key-"]').length;
            document.getElementById('result1').textContent = 'SRCDOC_PARENT_OK n=' + n;
        } catch (e) {
            document.getElementById('result1').textContent = 'SRCDOC_PARENT_BLOCKED ' + e.message;
        }
    });
    </script>
    </body>
    """,
    height=60,
)

# --- Path 2: declared custom component (served from same origin) -------------
_COMPONENT_DIR = Path(__file__).parent / "probe_component"
_probe_component = components.declare_component("dom_probe", path=str(_COMPONENT_DIR))

value = _probe_component(default="no value yet", key="probe_component_1")
st.write("Component returned:", value)
