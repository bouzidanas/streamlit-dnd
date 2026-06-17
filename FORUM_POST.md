<!--
=============================================================================
  Streamlit forum post draft for streamlit-dnd
  Paste this into the Discourse editor (Show the Community! category).
  The forum supports Markdown, so headings/code/tables render as-is.

  GIF PLACEHOLDERS: search for [GIF: ...] below. Drag your gif onto the
  editor at that spot (or use the upload button) and Discourse will insert
  the image for you. Delete the placeholder line once the gif is in.
=============================================================================
-->

Hey everyone,

I am excited to share a new custom component I have been working on: **streamlit-dnd**, drag-and-drop reordering for the things inside your Streamlit containers. You give it the keys of some keyed containers, and the direct children of those containers become draggable. You can reorder items inside a single container, or drag them between containers. When a drop happens, you get an event back describing the move so you can update your `session_state` however you like.

[GIF: top-level demo showing items being dragged and reordered within a container, and dragged across two containers]

Check out the project here:

GitHub: https://github.com/bouzidanas/streamlit-dnd
PyPI: https://pypi.org/project/streamlit-dnd/
Live demo: https://dnd-demo.streamlit.app (try every option right in your browser, no install needed)

Install is the usual one-liner, the frontend ships inside the package so there is no build step or extra setup:

```bash
pip install streamlit-dnd
```

## Quick start

The whole idea is that you render normal keyed containers, then call `dnd()` with their keys *after* rendering them. Here is a minimal single-list reorder:

```python
import streamlit as st
from streamlit_dnd import dnd, apply_move

if "items" not in st.session_state:
    st.session_state.items = {"list": ["Apples", "Bananas", "Cherries", "Dates"]}

# 1. Render a keyed container whose children come from session state
with st.container(key="list", border=True):
    for it in st.session_state.items["list"]:
        with st.container(key=f"item_{it}", border=True):
            st.write(it)

# 2. Turn on drag and drop (call this AFTER rendering the container)
event = dnd("list")

# 3. Apply the drop to session state and rerun
if event:
    apply_move(event, st.session_state.items)
    st.rerun()
```

That is the entire loop. Render from state, enable dnd, apply the move on a drop. To allow dragging between containers, just pass more keys: `dnd("list_a", "list_b")`.

[GIF: the quick-start example above running, dragging Bananas above Apples]

There are a few options for how it looks and behaves (a border handle by default so buttons and inputs inside your items stay clickable, a "ghost" drop preview, source/destination restrictions for one-way moves, and so on). The README has the full table and a couple of bigger examples.

[GIF: showing the border handle and the ghost drop preview in action]

## Background

Some of you might remember a post I made a while back about a proof of concept for [draggable Streamlit containers](https://discuss.streamlit.io/t/draggable-streamlit-containers/72484). That one got a lot of interest, and I always meant to turn it into something you could actually install and use. But I kept hitting two walls.

The first wall was me. I was trying to build the drag-and-drop behavior completely from scratch, and I did not have much experience coding the inner workings of dnd. The second wall was Streamlit itself. Over time, updates changed the layout structure of containers enough that the way I was targeting elements to attach dnd behavior stopped working, so I would get something going and then a release would quietly break it. Between those two things, the proof of concept stayed a proof of concept.

What finally got me past both walls was using AI to fill in the gaps in my knowledge, specifically the dnd internals I was weak on. I want to be clear that this is not a vibe coded project. I had a direct hand in solving the crucial problems. I provided the targeting approach for finding and hooking into the right container elements, and the logic for making this play nicely with how Streamlit actually works. A good example of the latter: the component does not force a rerun on every drag event. It reports the drop back to you and leaves the rerun decision in your hands, because that is the kind of control Streamlit users want over their own apps. That was a deliberate design call based on what I learned from the proof of concept and from building Streamlit apps, not something a model decided for me.

In other words, I brought the hard-won lessons from the proof of concept and the Streamlit-specific decisions, and I leaned on AI for the dnd plumbing I am not great at. And just to underline the point: I first tried to one-shot the whole thing with AI, no code solutions from me, and every model I tried failed to get it working. The targeting approach and the Streamlit integration logic were the missing pieces that only came from having actually wrestled with this problem before.

If you find this interesting or useful, please give it a try, and let me know what you build with it or what could be better. Issues and PRs welcome on GitHub.
