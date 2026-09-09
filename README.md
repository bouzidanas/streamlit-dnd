# streamlit-dnd

Drag-and-drop reordering for keyed children of Streamlit containers — reorder
items inside a container or move them between containers. Fixed headings and
controls can live alongside the cards without corrupting list indices.

Tested against **Streamlit 1.58 through 1.63**.

![demo](https://img.shields.io/badge/streamlit-1.58%2B-red)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://dnd-demo.streamlit.app)

**[Try the live demo](https://dnd-demo.streamlit.app)** to play with every option in the browser, no install needed.

## Install

```bash
pip install streamlit-dnd
```

That's it — the frontend ships inside the package, so there's no build step and
nothing else to configure. Import and use it like any other Streamlit component:

```python
from streamlit_dnd import dnd, apply_move
```

## Run the demo

Try the **[hosted demo](https://dnd-demo.streamlit.app)**, or run the bundled
demo from a clone of this repo:

```bash
pip install -r requirements.txt
streamlit run demo.py
```

## Upgrading from 0.1

Version 0.2 moves only keyed direct children by default. If a 0.1 app rendered
unkeyed draggable children, either give each child a stable `key=` (recommended)
or pass `item_mode="all"` to preserve the old behavior. `apply_move` remains
compatible with mappings of container keys to lists and now accepts additional
collection shapes described below.

## Usage

```python
import streamlit as st
from streamlit_dnd import dnd, apply_move

if "board" not in st.session_state:
    st.session_state["board"] = {"left": ["A", "B", "C"], "right": ["D"]}

# 1. Render keyed containers whose children come from session state
col1, col2 = st.columns(2)
with col1, st.container(key="left", border=True):
    st.subheader("Available")  # fixed: unkeyed children are ignored by default
    for it in st.session_state["board"]["left"]:
        with st.container(key=f"item_{it}", border=True):
            st.write(it)
with col2, st.container(key="right", border=True):
    st.subheader("Selected")
    for it in st.session_state["board"]["right"]:
        with st.container(key=f"item_{it}", border=True):
            st.write(it)

# 2. Enable drag and drop on those containers (call AFTER rendering them)
event = dnd("left", "right")

# 3. Apply drops to session state and rerun
if event:
    apply_move(event, st.session_state["board"])
    st.rerun()
```

## API

### `dnd(*container_keys, **options) -> DropEvent | None`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `*container_keys` | `str` / iterables of `str` | — | Keys of the `st.container(key=...)` blocks to enable dnd on. |
| `cross` | `bool` | `True` | Allow dragging items between containers. `False` = reorder within each container only. Ignored when `sources`/`destinations` are set. |
| `sources` | `list[str] \| None` | `None` | If set, only these containers' items can be dragged. |
| `destinations` | `list[str] \| None` | `None` | If set, items can only be dropped into these containers. |
| `exclude` | `list[str] \| None` | `None` | Keys of child elements that must never be draggable (matched against each item's `key=`). Excluded items are pinned in place and ignored by the drop-position math — handy for fixed headers or other non-draggable content inside a draggable container. |
| `item_mode` | `"keyed" \| "all"` | `"keyed"` | `"keyed"` safely moves only children with their own `key=` and ignores fixed unkeyed content. `"all"` enables the pre-0.2 behavior where every direct child is movable. |
| `placeholder` | `str \| dict[str, str] \| None` | `None` | Dimmed, italic hint shown inside a container while it has no draggable items (e.g. `"Drop items here"`). The component injects/removes it automatically. Pass one string for all containers, or a `{container_key: text}` mapping for per-container messages. |
| `handle` | `bool \| "border"` | `"border"` | `"border"`: the item's edges become the handle (grab from a band around the border, interior stays free for buttons/inputs). `False`: grab items anywhere. `True`: items get a small corner drag handle and only drag from it. |
| `handle_corner` | `"top-right" \| "top-left" \| "bottom-right" \| "bottom-left"` | `"top-right"` | Which corner the handle icon sits in when `handle=True`. |
| `handle_icon` | `str` | `"⠿"` | What the corner handle shows: any text/emoji, or a Streamlit Material icon as `":material/<name>:"` (e.g. `":material/drag_indicator:"`). Applies when `handle=True`. |
| `indicator` | `"line" \| "highlight" \| "ghost"` | `"ghost"` | `"ghost"`: inserts a translucent copy of the dragged item at the drop position — the list reflows to preview the result, and on drop the copy seamlessly becomes the real item. `"line"`: bright insertion line between items showing where the drop lands. `"highlight"`: tints the element whose spot will be taken. |
| `color` | `str` | `"#ff4b4b"` | Any CSS color for the indicator. |
| `key` | `str` | `"stdnd"` | Component instance key. Set explicitly when calling `dnd()` more than once per page. |

Returns a **`DropEvent`** for each completed drop (then `None` until the next drop):

```python
@dataclass(frozen=True)
class DropEvent:
    from_container: str    # container key the item left
    to_container: str      # container key the item entered (== from_container for reorders)
    item_key: str | None   # st key (None only with item_mode="all")
    from_index: int        # position before the move
    to_index: int          # insertion position (pre-removal indexing for same-container moves)
```

### `apply_move(event, collections, *, container_key=None) -> None`

The helper supports lists and insertion-ordered dictionaries:

```python
# Multiple list containers
apply_move(event, {"left": st.session_state.left, "right": st.session_state.right})

# A single list can be passed directly
apply_move(event, st.session_state.tasks)

# Reorder one dict of named objects, such as DataFrames
apply_move(event, st.session_state.dfs, container_key="dataframes")

# Move entries between two dicts
apply_move(event, {"left": st.session_state.dfs, "right": st.session_state.more_dfs})
```

For a container mapping, its keys must match the keys passed to `dnd()`. A
mismatch now raises an error that shows the expected shape and supplied keys.

## Recipes

**Reorder only (no cross-container moves):**

```python
dnd("my_list", cross=False)
```

**Legacy unkeyed children:**

```python
# Every direct child is movable, as in streamlit-dnd 0.1.x. Your backing list
# must have exactly one entry per rendered child and use the same order.
dnd("my_list", item_mode="all")
```

**Named DataFrames as draggable cards:**

```python
with st.container(key="dataframes", border=True):
    st.subheader("Reports")  # fixed and ignored by the index math
    for name, frame in st.session_state.dfs.items():
        with st.container(key=f"frame_{name}", border=True):
            st.write(name)
            st.dataframe(frame)

event = dnd("dataframes")
if event:
    apply_move(event, st.session_state.dfs, container_key="dataframes")
    st.rerun()
```

This reorders whole DataFrame cards. It does not make individual rows inside
`st.dataframe` draggable.

**Source → destination flow** (e.g. a palette you drag items out of, into a canvas):

```python
dnd("palette", "canvas", sources=["palette", "canvas"], destinations=["canvas"])
```

`sources` lists who can be dragged *from*, `destinations` who can be dropped *into*. A container in both lists supports internal reordering too.

**Items with interactive widgets inside:**

```python
dnd("board", handle=True)   # drag only via the corner handle

# pick the corner and the icon (text, emoji, or a Material icon)
dnd("board", handle=True, handle_corner="bottom-left",
    handle_icon=":material/drag_indicator:")

# or make the item's border the handle, leaving the interior free
dnd("board", handle="border")
```

**Multiple independent dnd groups on one page:**

```python
ev1 = dnd("group1_a", "group1_b", key="dnd_group1")
ev2 = dnd("group2_a", "group2_b", key="dnd_group2")
```

**Trello-style ghost preview:**

```python
dnd("board", indicator="ghost")
```

While dragging, a translucent dashed-outline copy of the item is inserted at
the prospective position so the list reflows to show the would-be result. On
drop, that copy instantly turns into the real item (full opacity,
interactive) and the original collapses; when Streamlit's rerender lands a
moment later, the copy is swapped for the genuine re-rendered element with no
visual gap.

**Persisting arrangements across page refreshes:**

`st.session_state` is per-session: a page refresh, a new tab, or an app
restart starts a fresh session and wipes it. To make arrangements durable,
mirror them to storage (a file, database, etc.) on every drop and seed new
sessions from it:

```python
import json, copy
from pathlib import Path

STORE = Path(__file__).parent / "arrangements.json"
DEFAULTS = {"left": ["A", "B", "C"], "right": ["D"]}

def save():
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st.session_state["board"]))
    tmp.replace(STORE)  # atomic write

# Seed new sessions from disk (or defaults)
if "board" not in st.session_state:
    st.session_state["board"] = (
        json.loads(STORE.read_text()) if STORE.exists() else copy.deepcopy(DEFAULTS)
    )

# ... render containers ...

event = dnd("left", "right")
if event:
    apply_move(event, st.session_state["board"])
    save()          # <- mirror the change to disk
    st.rerun()

# Reset = delete the store + restore defaults
if st.button("Reset"):
    STORE.unlink(missing_ok=True)
    st.session_state["board"] = copy.deepcopy(DEFAULTS)
    st.rerun()
```

`demo.py` implements exactly this pattern (see "Persistence" section at the
top of the file). Note: a plain JSON file is shared by *all* visitors of the
app — for multi-user apps, key the storage by user (e.g. `st.user.email`) or
use a database.

## How it works

Streamlit adds a CSS class `st-key-<key>` to every keyed element and container.
This module mounts an **invisible custom component** (a same-origin iframe) that:

1. Reaches into the parent document (`window.parent.document`) — possible because
   Streamlit serves component iframes from the same origin with
   `allow-same-origin`.
2. Finds your containers via `.st-key-<key>` and identifies eligible **direct
   children**: in Streamlit 1.58–1.63's DOM, every visual child of a container is a
   direct DOM child that is either a `div[data-testid="stElementContainer"]`
   (simple elements/widgets) or a `div[data-testid="stLayoutWrapper"]` (nested
   containers, expanders).
   By default, only children with their own Streamlit key are eligible.
3. Wires native HTML5 drag-and-drop handlers onto those children, draws the
   drop indicators, and enforces the cross/sources/destinations rules.
4. On drop, sends `{from_container, to_container, item_key, from_index, to_index}`
   back to Python via `Streamlit.setComponentValue`, which triggers a rerun —
   your script applies the move to `st.session_state` and re-renders.
5. A `MutationObserver` re-wires everything after each Streamlit rerun
   (Streamlit recreates DOM nodes), so dnd keeps working across reruns.

```
┌────────────────────────── parent document ──────────────────────────┐
│  div.st-key-left (stVerticalBlock)        div.st-key-right          │
│  ├─ div[stLayoutWrapper]  ◄─── draggable  ├─ div[stLayoutWrapper]   │
│  │   └─ div.st-key-item_A                 │   └─ div.st-key-item_D  │
│  ├─ div[stLayoutWrapper]  ◄─── draggable  └─ ...                    │
│  │   └─ div.st-key-item_B                                           │
│  └─ ...                                                             │
│                                                                     │
│  ┌─ invisible iframe (this component) ─┐                            │
│  │  wires dnd onto the elements above, │                            │
│  │  reports drops to Python            │                            │
│  └──────────────────────────────────────┘                           │
└──────────────────────────────────────────────────────────────────────┘
```

### Caveats

- **DOM coupling**: this relies on Streamlit's internal DOM structure
  (`stElementContainer` / `stLayoutWrapper` test ids and `st-key-*` classes).
  It is verified against Streamlit 1.58 through 1.63; future versions may need
  small selector updates in `streamlit_dnd/frontend/main.js`.
- **Item identity**: every draggable child needs its own unique `key=` in the
  default mode. Use `item_mode="all"` only when intentionally moving unkeyed
  children and keeping a one-to-one backing collection for all of them.
- **Render before dnd**: call `dnd()` *after* the containers it targets have
  been rendered in the script.

## Project layout

```
streamlit-dnd/
├── demo.py                      # full-featured demo (kanban, playlist, widget board)
├── streamlit_dnd/               # the reusable module
│   ├── __init__.py              # dnd(), DropEvent, apply_move()
│   └── frontend/
│       ├── index.html           # component scaffold (no build step needed)
│       ├── streamlit-protocol.js# minimal Streamlit component protocol
│       └── main.js              # the dnd engine (parent-DOM wiring)
├── tests/
│   ├── test_apply_move.py       # unit tests for collection/index behavior
│   ├── test_api.py              # validation + version consistency
│   ├── minimal_app.py           # minimal app for e2e testing
│   ├── e2e_app.py               # packaged-wheel E2E fixture app
│   ├── e2e_real.py              # real mouse input against live Streamlit
│   ├── e2e_module.py            # Playwright e2e: wiring + simulated drag
│   ├── e2e_demo.py              # Playwright e2e: full demo verification
│   ├── e2e_ghost.py             # Playwright e2e: ghost indicator lifecycle
│   └── e2e_persistence.py       # Playwright e2e: refresh persistence + reset
└── probe/                       # DOM-discovery scripts used during development
```

## Running the tests

```bash
# Unit tests
python -m pytest

# E2E (needs playwright + chromium)
streamlit run tests/minimal_app.py --server.port 8599 --server.headless true &
python tests/e2e_module.py

streamlit run demo.py --server.port 8599 --server.headless true &
python tests/e2e_demo.py
python tests/e2e_ghost.py
python tests/e2e_persistence.py

# True packaged E2E: build/install the wheel first, then drive a real mouse
# against a live Streamlit app (requires Playwright's Chromium browser).
python -m build
python -m pip install --force-reinstall dist/streamlit_dnd-0.2.0-py3-none-any.whl
python -m playwright install chromium
python tests/e2e_real.py --browser chromium
```
