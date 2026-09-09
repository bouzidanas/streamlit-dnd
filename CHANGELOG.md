# Changelog

## 0.2.0

- Make keyed direct children the safe default so headings, dividers, and
  controls inside draggable containers no longer corrupt move indices.
- Add `item_mode="all"` for compatibility with the 0.1 unkeyed-child behavior.
- Support a single list directly in `apply_move`.
- Support reordering and cross-container movement of insertion-ordered
  dictionaries, including dictionaries of named DataFrames.
- Replace raw mapping and index failures with actionable, atomic validation.
- Accept a single string for `sources`, `destinations`, and `exclude`.
- Fix empty placeholders in containers that also contain fixed content.
- Correct `streamlit_dnd.__version__` and Python compatibility metadata.
- Add packaged-wheel, real-browser-input E2E coverage and release test gates.

## 0.1.1

- Add touch dragging, exclusions, placeholders, and configurable drag handles.

## 0.1.0

- Initial release.
