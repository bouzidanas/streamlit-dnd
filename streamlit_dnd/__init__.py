"""streamlit-dnd: drag-and-drop reordering for Streamlit containers.

Turn the direct children of keyed ``st.container`` blocks into draggable
items that can be reordered within a container or moved across containers.

Quick start::

    import streamlit as st
    from streamlit_dnd import dnd

    with st.container(key="list_a", border=True):
        for item in st.session_state.items_a:
            render(item)

    with st.container(key="list_b", border=True):
        for item in st.session_state.items_b:
            render(item)

    event = dnd("list_a", "list_b")
    if event:
        # apply the move to your session state, then rerun
        ...

How it works
------------
Streamlit gives keyed containers a CSS class ``st-key-<key>``. An invisible
custom component (a same-origin iframe) reaches into the parent document,
finds those containers, and attaches native HTML5 drag-and-drop handlers to
their direct children (``stElementContainer`` / ``stLayoutWrapper`` nodes).
When the user drops an item, the component reports the move back to Python
so the app can persist the new order in ``st.session_state``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

import streamlit as st
import streamlit.components.v1 as components

__version__ = "0.1.0"

__all__ = ["dnd", "DropEvent", "apply_move", "__version__"]

_FRONTEND_DIR = Path(__file__).parent / "frontend"

# Declared lazily so importing this module doesn't require a ScriptRunContext.
_component_func = None


def _get_component():
    global _component_func  # noqa: PLW0603
    if _component_func is None:
        _component_func = components.declare_component(
            "streamlit_dnd", path=str(_FRONTEND_DIR)
        )
    return _component_func


@dataclass(frozen=True)
class DropEvent:
    """A completed drag-and-drop action.

    Attributes
    ----------
    from_container:
        Key of the container the item was dragged out of.
    to_container:
        Key of the container the item was dropped into. Equal to
        ``from_container`` for same-container reordering.
    item_key:
        The ``key=`` of the dragged element (or of the keyed container
        nested inside the dragged wrapper), or ``None`` if the dragged
        element has no key.
    from_index:
        Position of the item among the source container's children before
        the move.
    to_index:
        Insertion position among the destination container's children. For
        same-container moves this index is relative to the list *before*
        the item is removed from its old position.
    """

    from_container: str
    to_container: str
    item_key: str | None
    from_index: int
    to_index: int


def dnd(
    *container_keys: str | Sequence[str],
    cross: bool = True,
    sources: Sequence[str] | None = None,
    destinations: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    placeholder: str | Mapping[str, str] | None = None,
    handle: bool | Literal["border"] = "border",
    handle_corner: Literal[
        "top-left", "top-right", "bottom-left", "bottom-right"
    ] = "top-right",
    handle_icon: str = "⠿",
    indicator: Literal["line", "highlight", "ghost"] = "ghost",
    color: str = "#ff4b4b",
    key: str = "stdnd",
) -> DropEvent | None:
    """Enable drag-and-drop on the direct children of keyed containers.

    Call this *after* the containers have been created in your script. The
    returned :class:`DropEvent` describes the latest drop the user performed
    (or ``None`` if nothing new happened); apply it to your own session
    state and the next rerun will render the updated order.

    Parameters
    ----------
    *container_keys:
        Keys of the ``st.container(key=...)`` blocks to make draggable.
        Strings and/or iterables of strings.
    cross:
        Whether items may be dragged between containers (default ``True``).
        Ignored when ``sources``/``destinations`` are given.
    sources:
        If set, only these containers' items can be dragged. Containers not
        listed become drop-only (or inert if also absent from
        ``destinations``).
    destinations:
        If set, items can only be dropped into these containers.
    exclude:
        Keys of child elements that must never be draggable. An item is
        excluded when its ``key=`` (the same key the move event reports as
        ``item_key``) appears in this list, so placeholder hints, headers, or
        any other fixed content inside a draggable container can be pinned in
        place. Excluded items are also ignored by the drop-position math, so
        the container behaves as if they weren't there.
    placeholder:
        Dimmed, italic hint text shown inside a container while it has no
        draggable items (e.g. ``"Drop items here"``). The component injects and
        removes it automatically, so empty drop targets don't look broken. Pass
        a single string to use the same text for every container, or a mapping
        of container key -> text to give each container its own message.
        ``None`` (default) shows no placeholder.
    handle:
        How an item is grabbed. ``"border"`` (default): the item's edges
        become the handle, so you can grab it from a band running around its
        border while the interior stays free for any buttons or inputs
        inside it. ``False``: grab the item anywhere (simplest, but a click
        on an inner widget can start a drag). ``True``: items get a small
        corner drag handle and can only be dragged from it.
    handle_corner:
        Which corner the handle sits in when ``handle=True``: ``"top-left"``,
        ``"top-right"`` (default), ``"bottom-left"``, or ``"bottom-right"``.
        Ignored unless ``handle=True``.
    handle_icon:
        What the corner handle shows. Any text or emoji (e.g. ``"☰"`` or
        ``"≡"``), or a Streamlit Material icon written as
        ``":material/<name>:"`` (e.g. ``":material/drag_indicator:"``).
        Defaults to the braille "grip" glyph ``"⠿"``. Ignored unless
        ``handle=True``.
    indicator:
        ``"ghost"`` (default): a translucent copy of the dragged item is
        inserted at the prospective position (the list reflows to preview
        the result); on drop the copy becomes the real item — full opacity
        and interactive — until Streamlit's rerender takes over seamlessly.
        ``"line"``: a bright insertion line shows where the item will land.
        ``"highlight"``: the element whose spot will be taken is tinted.
    color:
        CSS color of the indicator (any valid CSS color string).
    key:
        Streamlit widget key for this dnd component instance. Only needs to
        be set when you call :func:`dnd` more than once per page.

    Returns
    -------
    DropEvent | None
        The new drop event, or ``None``.
    """
    # Flatten: dnd("a", "b"), dnd(["a", "b"]) and dnd("a", ["b", "c"]) all work.
    keys: list[str] = []
    for entry in container_keys:
        if isinstance(entry, str):
            keys.append(entry)
        else:
            keys.extend(entry)
    if not keys:
        raise ValueError("dnd() needs at least one container key")

    if indicator not in ("line", "highlight", "ghost"):
        raise ValueError(
            f"indicator must be 'line', 'highlight', or 'ghost', got {indicator!r}"
        )

    if handle not in (True, False, "border"):
        raise ValueError(
            f"handle must be True, False, or 'border', got {handle!r}"
        )

    valid_corners = ("top-left", "top-right", "bottom-left", "bottom-right")
    if handle_corner not in valid_corners:
        raise ValueError(
            f"handle_corner must be one of {valid_corners}, got {handle_corner!r}"
        )

    raw = _get_component()(
        instance_id=key,
        containers=keys,
        cross=cross,
        sources=list(sources) if sources is not None else None,
        destinations=list(destinations) if destinations is not None else None,
        exclude=list(exclude) if exclude is not None else None,
        placeholder=dict(placeholder)
        if isinstance(placeholder, Mapping)
        else placeholder,
        handle=handle,
        handle_corner=handle_corner,
        handle_icon=handle_icon,
        indicator=indicator,
        color=color,
        key=key,
        default=None,
    )

    if not raw:
        return None

    # The component re-sends the same value on every rerun until the next
    # drop. De-duplicate via the event id so each drop is returned once.
    seen_key = f"_stdnd_seen_{key}"
    event_id = raw.get("event_id")
    if st.session_state.get(seen_key) == event_id:
        return None
    st.session_state[seen_key] = event_id

    return DropEvent(
        from_container=raw["from_container"],
        to_container=raw["to_container"],
        item_key=raw.get("item_key"),
        from_index=raw["from_index"],
        to_index=raw["to_index"],
    )


def apply_move(
    event: DropEvent,
    lists: dict[str, list],
) -> None:
    """Apply a :class:`DropEvent` to plain Python lists, in place.

    A convenience helper for the common pattern where each draggable
    container is rendered from a list in ``st.session_state``::

        lists = {"todo": st.session_state.todo, "done": st.session_state.done}
        event = dnd("todo", "done")
        if event:
            apply_move(event, lists)
            st.rerun()

    Parameters
    ----------
    event:
        The drop event returned by :func:`dnd`.
    lists:
        Mapping of container key -> list of items rendered in that
        container (in render order).
    """
    src = lists[event.from_container]
    dst = lists[event.to_container]

    item = src.pop(event.from_index)

    to_index = event.to_index
    if src is dst and event.from_index < to_index:
        # Removing the item shifted everything after it left by one.
        to_index -= 1
    to_index = max(0, min(to_index, len(dst)))

    dst.insert(to_index, item)
