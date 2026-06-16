"""Edge case probe: empty containers, height-fixed containers."""
import streamlit as st

st.title("Edge probe")

# Empty keyed container - does it render a DOM element?
with st.container(key="empty_container", border=True):
    pass

# Container with fixed height - what's the inner structure?
with st.container(key="height_container", border=True, height=200):
    st.button("In height container", key="hc_btn")

# Container whose children include a placeholder convention
with st.container(key="mixed_container", border=True):
    with st.container(key="_dnd_static_placeholder"):
        st.caption("drop here")
    st.button("Real item", key="mixed_btn")

st.write("done")
