"""streamlit-dnd: drag-and-drop reordering for Streamlit containers.

Turn keyed direct children of ``st.container`` blocks into draggable items
that can be reordered within a container or moved across containers. Unkeyed
content such as headings is ignored by default so DOM positions stay aligned
with the Python collections that back the draggable items.

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

from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import streamlit as st
import streamlit.components.v1 as components

from ._version import __version__

__all__ = ["DropEvent", "__version__", "apply_move", "dnd"]

_FRONTEND_DIR = Path(__file__).parent / "frontend"

# Declared lazily so importing this module doesn't require a ScriptRunContext.
_component_func = None


def _get_component():
    global _component_func
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
    item_mode: Literal["keyed", "all"] = "keyed",
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
    item_mode:
        Which direct children are draggable. ``"keyed"`` (default) includes
        only children with their own ``key=``. This safely ignores headings,
        captions, dividers, and other fixed content users commonly place in a
        list container. ``"all"`` restores the legacy behavior where every
        direct Streamlit child is draggable; in that mode the backing Python
        collection must contain one entry for every child, in the same order.
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
            try:
                keys.extend(entry)
            except TypeError as exc:
                raise TypeError(
                    "container keys must be strings or iterables of strings"
                ) from exc
    if not keys:
        raise ValueError("dnd() needs at least one container key")
    if any(
        not isinstance(container_key, str) or not container_key
        for container_key in keys
    ):
        raise ValueError("every dnd() container key must be a non-empty string")
    if len(set(keys)) != len(keys):
        raise ValueError("dnd() container keys must be unique")

    source_keys = _normalize_key_option(sources, "sources")
    destination_keys = _normalize_key_option(destinations, "destinations")
    excluded_keys = _normalize_key_option(exclude, "exclude")

    for option_name, option_keys in (
        ("sources", source_keys),
        ("destinations", destination_keys),
    ):
        if option_keys is None:
            continue
        unknown = set(option_keys) - set(keys)
        if unknown:
            raise ValueError(
                f"{option_name} contains keys not passed to dnd(): {sorted(unknown)!r}"
            )

    if not isinstance(cross, bool):
        raise TypeError(f"cross must be a bool, got {cross!r}")

    if indicator not in ("line", "highlight", "ghost"):
        raise ValueError(
            f"indicator must be 'line', 'highlight', or 'ghost', got {indicator!r}"
        )

    if not isinstance(handle, (bool, str)):
        raise TypeError(f"handle must be a bool or 'border', got {handle!r}")
    if handle not in (True, False, "border"):
        raise ValueError(f"handle must be True, False, or 'border', got {handle!r}")

    if item_mode not in ("keyed", "all"):
        raise ValueError(f"item_mode must be 'keyed' or 'all', got {item_mode!r}")

    valid_corners = ("top-left", "top-right", "bottom-left", "bottom-right")
    if handle_corner not in valid_corners:
        raise ValueError(
            f"handle_corner must be one of {valid_corners}, got {handle_corner!r}"
        )

    if not isinstance(handle_icon, str):
        raise TypeError(f"handle_icon must be a string, got {handle_icon!r}")
    if not isinstance(color, str):
        raise TypeError(f"color must be a CSS color string, got {color!r}")
    if not color:
        raise ValueError(f"color must be a non-empty CSS color string, got {color!r}")
    if not isinstance(key, str):
        raise TypeError(f"key must be a string, got {key!r}")
    if not key:
        raise ValueError(f"key must be a non-empty string, got {key!r}")

    raw = _get_component()(
        instance_id=key,
        containers=keys,
        cross=cross,
        sources=source_keys,
        destinations=destination_keys,
        exclude=excluded_keys,
        item_mode=item_mode,
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
    collections: Mapping[str, MutableSequence | MutableMapping]
    | MutableSequence
    | MutableMapping,
    *,
    container_key: str | None = None,
) -> None:
    """Apply a :class:`DropEvent` to mutable Python collections, in place.

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
    collections:
        Usually a mapping of ``st.container`` key to the mutable list rendered
        in that container. For a single-container reorder, a list can be passed
        directly. Ordered mutable mappings are also supported, which makes a
        dict of named DataFrames (or other named objects) reorderable without
        converting it to a list.
    container_key:
        Treat ``collections`` itself as the backing collection for this one
        container. This is mainly useful when the collection is a dict, since
        a dict would otherwise be interpreted as the container-to-collection
        mapping. Both event container keys must match this value.

    Raises
    ------
    KeyError
        If a container key is missing from the supplied mapping. The message
        includes the expected shape and the keys that were supplied.
    IndexError
        If the browser event no longer lines up with the backing collection.
    TypeError
        If a backing collection is not a mutable sequence or mutable mapping,
        or a move tries to cross between those two different collection kinds.
    """
    if not isinstance(event, DropEvent):
        raise TypeError(f"event must be a DropEvent, got {type(event).__name__}")

    if container_key is not None:
        if not isinstance(container_key, str) or not container_key:
            raise ValueError("container_key must be a non-empty string")
        if event.from_container != container_key or event.to_container != container_key:
            raise ValueError(
                "container_key can only be used for a same-container move; "
                f"event is {event.from_container!r} -> {event.to_container!r}"
            )
        src = dst = collections
    elif isinstance(collections, MutableSequence):
        if event.from_container != event.to_container:
            raise ValueError(
                "a single collection can only handle a same-container move; "
                "pass {container_key: collection, ...} for cross-container moves"
            )
        src = dst = collections
    else:
        if not isinstance(collections, Mapping):
            raise TypeError(
                "collections must be a mutable sequence, a mutable mapping, or "
                "a mapping of container keys to mutable collections"
            )
        missing = [
            key
            for key in (event.from_container, event.to_container)
            if key not in collections
        ]
        if missing:
            supplied = list(collections.keys())
            hint = (
                "Pass a mapping whose keys match dnd(...), for example "
                "{'left': left_items, 'right': right_items}. For one list, "
                "pass that list directly. For one ordered dict, pass it with "
                f"container_key={event.from_container!r}."
            )
            raise KeyError(
                f"no backing collection for container(s) {missing!r}; "
                f"supplied keys are {supplied!r}. {hint}"
            )
        src = collections[event.from_container]
        dst = collections[event.to_container]

    src_kind = _collection_kind(src, event.from_container)
    dst_kind = _collection_kind(dst, event.to_container)
    if src_kind != dst_kind:
        raise TypeError(
            "cross-container moves require matching collection types; got "
            f"{src_kind} for {event.from_container!r} and {dst_kind} for "
            f"{event.to_container!r}"
        )

    if not isinstance(event.from_index, int) or isinstance(event.from_index, bool):
        raise TypeError("DropEvent.from_index must be an integer")
    if not isinstance(event.to_index, int) or isinstance(event.to_index, bool):
        raise TypeError("DropEvent.to_index must be an integer")
    if not 0 <= event.from_index < len(src):
        raise IndexError(
            f"drop source index {event.from_index} is outside backing collection "
            f"{event.from_container!r} (length {len(src)}). The rendered draggable "
            "items and backing collection are out of sync. Give each movable child "
            "a unique key and use the default item_mode='keyed', or ensure "
            "item_mode='all' has one data entry per rendered child."
        )

    to_index = event.to_index
    if src is dst and event.from_index < to_index:
        # Removing the item shifted everything after it left by one.
        to_index -= 1

    if src_kind == "sequence":
        item = src.pop(event.from_index)
        to_index = max(0, min(to_index, len(dst)))
        dst.insert(to_index, item)
        return

    # Dict insertion order is the display order. Rebuild the mapping after
    # moving one (key, value) pair so named DataFrames and similar objects work
    # without a parallel list of names.
    source_key = list(src.keys())[event.from_index]
    item = (source_key, src[source_key])
    if src is not dst and source_key in dst:
        raise ValueError(
            f"cannot move mapping entry {source_key!r} into "
            f"{event.to_container!r}: that key already exists"
        )
    del src[source_key]
    destination_items = list(dst.items())
    to_index = max(0, min(to_index, len(destination_items)))
    destination_items.insert(to_index, item)
    dst.clear()
    dst.update(destination_items)


def _collection_kind(collection: Any, container_key: str) -> str:
    """Return the supported collection family, with a useful error otherwise."""
    if isinstance(collection, MutableSequence):
        return "sequence"
    if isinstance(collection, MutableMapping):
        return "mapping"
    raise TypeError(
        f"backing collection for {container_key!r} must be a mutable sequence "
        f"or mutable mapping, got {type(collection).__name__}"
    )


def _normalize_key_option(
    value: Sequence[str] | None, option_name: str
) -> list[str] | None:
    """Normalize a key option, accepting one string as a convenience."""
    if value is None:
        return None
    values = [value] if isinstance(value, str) else list(value)
    if any(not isinstance(entry, str) or not entry for entry in values):
        raise ValueError(f"{option_name} must contain only non-empty strings")
    return values
