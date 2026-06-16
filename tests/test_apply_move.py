"""Unit tests for streamlit_dnd.apply_move index math."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_dnd import DropEvent, apply_move


def ev(from_c, to_c, from_i, to_i, item_key=None):
    return DropEvent(
        from_container=from_c,
        to_container=to_c,
        item_key=item_key,
        from_index=from_i,
        to_index=to_i,
    )


def test_same_list_move_down():
    """Moving an item down: insertion index is pre-removal, so it shifts."""
    a = ["x", "y", "z"]
    # Drag "x" (index 0) to the gap after "z" (insertion index 3).
    apply_move(ev("a", "a", 0, 3), {"a": a})
    assert a == ["y", "z", "x"]


def test_same_list_move_up():
    a = ["x", "y", "z"]
    # Drag "z" (index 2) to the top (insertion index 0).
    apply_move(ev("a", "a", 2, 0), {"a": a})
    assert a == ["z", "x", "y"]


def test_same_list_middle():
    a = ["a", "b", "c", "d"]
    # Drag "a" (index 0) to between "c" and "d" (insertion index 3).
    apply_move(ev("l", "l", 0, 3), {"l": a})
    assert a == ["b", "c", "a", "d"]


def test_cross_list_move():
    a = ["x", "y"]
    b = ["p", "q"]
    # Drag "x" into b at index 1.
    apply_move(ev("a", "b", 0, 1), {"a": a, "b": b})
    assert a == ["y"]
    assert b == ["p", "x", "q"]


def test_cross_list_to_end():
    a = ["x"]
    b = ["p", "q"]
    apply_move(ev("a", "b", 0, 2), {"a": a, "b": b})
    assert a == []
    assert b == ["p", "q", "x"]


def test_cross_list_to_empty():
    a = ["x"]
    b = []
    apply_move(ev("a", "b", 0, 0), {"a": a, "b": b})
    assert a == []
    assert b == ["x"]


def test_to_index_clamped():
    """Out-of-range to_index (e.g. stale DOM count) is clamped, not an error."""
    a = ["x", "y"]
    b = ["p"]
    apply_move(ev("a", "b", 0, 99), {"a": a, "b": b})
    assert b == ["p", "x"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:  # noqa: PERF203
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
