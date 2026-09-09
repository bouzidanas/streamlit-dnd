"""Public API validation and packaging invariants."""

import os
from importlib.metadata import version

import pytest

import streamlit_dnd
from streamlit_dnd import dnd


def test_version_matches_project_metadata():
    assert streamlit_dnd.__version__ == version("streamlit-dnd")


def test_release_tag_matches_version_when_present():
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("v"):
        assert tag == f"v{streamlit_dnd.__version__}"


def test_single_string_options_are_not_split_into_characters(monkeypatch):
    captured = {}

    def component(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(streamlit_dnd, "_get_component", lambda: component)
    assert dnd("left", "right", sources="left", destinations="right") is None
    assert captured["sources"] == ["left"]
    assert captured["destinations"] == ["right"]
    assert captured["item_mode"] == "keyed"


@pytest.mark.parametrize(
    ("args", "kwargs", "error_type", "message"),
    [
        (("left", "left"), {}, ValueError, "must be unique"),
        (("left",), {"sources": ["unknown"]}, ValueError, "not passed to dnd"),
        (("left",), {"item_mode": "sometimes"}, ValueError, "item_mode"),
        (("left",), {"handle": 1}, TypeError, "handle"),
        (("left",), {"cross": 1}, TypeError, "cross"),
        (("",), {}, ValueError, "non-empty string"),
    ],
)
def test_invalid_configuration_fails_before_mounting(args, kwargs, error_type, message):
    with pytest.raises(error_type, match=message):
        dnd(*args, **kwargs)
