/**
 * streamlit-dnd frontend engine.
 *
 * Runs inside an invisible custom-component iframe. Because Streamlit
 * component iframes are same-origin, this script can reach into
 * window.parent.document, find the keyed containers configured from Python
 * (`.st-key-<key>` classes), and wire native HTML5 drag-and-drop onto their
 * direct children.
 *
 * DOM facts (verified against Streamlit 1.58):
 *   - A keyed st.container renders as
 *       div[data-testid="stVerticalBlock" | "stHorizontalBlock"].st-key-<key>
 *   - Its visual "direct children" are its direct DOM children:
 *       div[data-testid="stElementContainer"]   <- simple elements/widgets
 *       div[data-testid="stLayoutWrapper"]      <- nested containers/expanders
 *   - A keyed child element carries .st-key-<child key> on the
 *     stElementContainer itself; a keyed nested container carries it on the
 *     block element one level below the stLayoutWrapper.
 *
 * Drop events are reported back to Python via setComponentValue.
 */

"use strict";

(function () {
  const PDOC = window.parent.document;
  const STYLE_ID = "stdnd-styles";

  // ---------------------------------------------------------------------------
  // Engine state
  // ---------------------------------------------------------------------------

  /** Configuration sent from Python (set on every render). */
  let config = null;

  /** Monotonic counter to give every drop event a unique id. */
  let eventCounter = 0;

  /** State of the in-progress drag, or null. */
  let drag = null;

  /** Indicator DOM nodes (created lazily, reused). */
  let lineEl = null;

  /** Element currently wearing the highlight outline (highlight mode). */
  let highlightedEl = null;

  /**
   * Ghost-indicator state. The ghost is a clone of the dragged item inserted
   * into the destination container at the prospective drop position, so the
   * list reflows to preview the result. On drop it "materializes" (full
   * opacity, source hidden) and stays until Streamlit's rerender swaps in
   * the real item; the MutationObserver then removes it before paint.
   */
  let ghost = {
    el: null, // the clone
    sourceEl: null, // the original dragged element (collapsed after drop)
    destContainer: null, // container the ghost was dropped into
    materialized: false, // true between drop and Streamlit's rerender
    cleanupTimer: null, // safety net if the app never reruns
  };

  /** Debounce timer for MutationObserver re-wiring. */
  let rewireTimer = null;

  let observer = null;

  /**
   * Touch-drag state, or null. Native HTML5 drag-and-drop never fires on
   * touch devices, so a pointer-based fallback drives the same `drag` engine
   * from touch events. `active` flips true only once the finger has moved past
   * a small threshold, so taps and scrolls that start on an item still work.
   */
  let touchDrag = null;

  /** Whether the document-level touch listeners have been attached. */
  let touchWired = false;

  /** Movement (px) before a touch on an item is treated as a drag. */
  const TOUCH_THRESHOLD = 8;


  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------

  function findContainer(key) {
    return PDOC.querySelector(".st-key-" + cssEscape(key));
  }

  function cssEscape(s) {
    return s.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  /** True if the container lays its children out horizontally. */
  function isHorizontal(containerEl) {
    if (containerEl.classList.contains("stHorizontalBlock")) return true;
    const dir = window.parent.getComputedStyle(containerEl).flexDirection;
    return dir === "row" || dir === "row-reverse";
  }

  /**
   * The draggable items of a container: its direct DOM children that are
   * Streamlit element containers or layout wrappers. Items hosting this
   * component's own iframe (or any stIFrame) are excluded so injected
   * machinery never becomes draggable.
   */
  function getItems(containerEl) {
    const items = [];
    for (const child of containerEl.children) {
      const tid = child.getAttribute("data-testid");
      if (tid !== "stElementContainer" && tid !== "stLayoutWrapper") continue;
      // Never make this component's own iframe (or other component iframes
      // injected for dnd) draggable.
      if (child.querySelector('iframe[title*="streamlit_dnd"]')) continue;
      if (child.classList.contains("stdnd-ignore")) continue;
      // Caller-pinned exceptions: a child whose key is listed in `exclude`
      // (config.exclude) is never draggable and never counts toward the index
      // math, so placeholder hints / fixed headers can live inside an
      // otherwise-draggable container. The container still reads as empty when
      // its only child is an excluded placeholder.
      if (isExcludedItem(child)) continue;
      items.push(child);
    }
    return items;
  }

  /** True if a child element is pinned out of dnd via the `exclude` list. */
  function isExcludedItem(child) {
    if (!config.exclude.length) return false;
    const childKey = getItemKey(child);
    return !!childKey && config.exclude.includes(childKey);
  }

  // ---------------------------------------------------------------------------
  // Empty-container placeholder (injected by the engine, like a widget's own
  // placeholder text). Kept fully under our control so it carries none of the
  // margins / min-heights a Streamlit markdown element would bring, which is
  // what made an app-rendered hint sit shifted down inside the container.
  // The placeholder is always present (when text is configured); whether it
  // actually shows is a pure-CSS decision: it's visible only when it's the
  // container's only child, so any real item, ghost preview, or drop indicator
  // sibling hides it with no per-drag JS.
  // ---------------------------------------------------------------------------

  /** Ensure a container has its placeholder element (when text is configured). */
  function setPlaceholder(containerEl, key) {
    const p = config.placeholder;
    const text = typeof p === "string" ? p : p ? p[key] : null;
    let ph = containerEl.querySelector(":scope > .stdnd-placeholder");
    if (text) {
      if (!ph) {
        ph = PDOC.createElement("div");
        ph.className = "stdnd-placeholder stdnd-ignore";
        containerEl.appendChild(ph);
      }
      // Only write when it actually changes: setting textContent is itself a
      // DOM mutation the observer would see, re-triggering wireAll in a loop.
      if (ph.textContent !== text) ph.textContent = text;
    } else if (ph) {
      ph.remove();
    }
  }

  /** Extract the st-key of an item, or null if the item is unkeyed. */
  function getItemKey(item) {
    const fromClasses = (el) => {
      for (const cls of el.classList) {
        if (cls.startsWith("st-key-")) return cls.slice("st-key-".length);
      }
      return null;
    };
    // stElementContainer: key lives on the item itself.
    let key = fromClasses(item);
    if (key) return key;
    // stLayoutWrapper: key lives on the block element one level down.
    for (const child of item.children) {
      key = fromClasses(child);
      if (key) return key;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Styles + indicators (injected into the parent document)
  // ---------------------------------------------------------------------------

  function injectStyles() {
    let style = PDOC.getElementById(STYLE_ID);
    if (!style) {
      style = PDOC.createElement("style");
      style.id = STYLE_ID;
      PDOC.head.appendChild(style);
    }
    style.textContent = `
      .stdnd-draggable { cursor: grab; }
      .stdnd-draggable:active { cursor: grabbing; }
      .stdnd-has-handle { position: relative; }
      .stdnd-handle {
        position: absolute;
        z-index: 10;
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: grab;
        color: inherit;
        font-size: 16px;
        line-height: 1;
        /*
         * No button-like background plate: the glyph itself sits semi-
         * transparent at rest and fades to full opacity on hover/press, so the
         * handle reads as a faint mark until the user reaches for it.
         */
        opacity: 0.4;
        transition: opacity 0.1s ease;
        user-select: none;
        -webkit-user-select: none;
        /* Dragging from the handle on touch should grab, not scroll. */
        touch-action: none;
      }
      /* Corner placement, chosen from Python via handle_corner. */
      .stdnd-handle-top-right { top: 2px; right: 2px; }
      .stdnd-handle-top-left { top: 2px; left: 2px; }
      .stdnd-handle-bottom-right { bottom: 2px; right: 2px; }
      .stdnd-handle-bottom-left { bottom: 2px; left: 2px; }
      .stdnd-handle:hover { opacity: 0.85; }
      .stdnd-handle:active { opacity: 1; cursor: grabbing; }
      /* A Material Symbols glyph rendered inside a handle (handle_icon
       * = ":material/<name>:"); the icon name is the ligature text. */
      .stdnd-handle .stdnd-handle-mi {
        font-family: "Material Symbols Rounded";
        font-size: 18px;
        line-height: 1;
        font-weight: normal;
      }
      /*
       * Border-handle mode (handle="border"): the item is grabbed from a band
       * running along its edges, leaving the interior free for buttons and
       * inputs. The band lights up while the pointer hovers it so the grab
       * area is discoverable; the tint follows the indicator color.
       */
      .stdnd-border-handle { position: relative; }
      .stdnd-border-hot {
        cursor: grab;
        outline: 2px solid color-mix(in srgb, var(--stdnd-color, #ff4b4b) 70%, transparent);
        outline-offset: -2px;
        border-radius: 6px;
      }
      .stdnd-border-hot:active { cursor: grabbing; }
      /*
       * The item being dragged is taken OUT OF FLOW while the drag is in
       * progress: the list closes the gap so it reads as "lifted out", and no
       * dimmed copy is left behind in the original spot. The browser's native
       * drag image (a snapshot taken at dragstart, before this class is added)
       * is what follows the cursor.
       *
       * position:absolute (not display:none) is what removes it from flow:
       * display:none cancels the native drag session, but a zero-SIZE element
       * left in flow is still a flex item, so the container's flex gap would
       * reserve space on both sides of it and leave a visible gap where the
       * item used to be. Absolute positioning takes it out of the flex layout
       * entirely (gap collapses) while keeping it rendered so the drag stays
       * alive.
       */
      .stdnd-dragging {
        position: absolute !important;
        height: 0 !important;
        width: 0 !important;
        min-height: 0 !important;
        min-width: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        opacity: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
      }
      /*
       * Indicators use position:fixed so getBoundingClientRect() viewport
       * coordinates can be used directly. (Streamlit scrolls inside an
       * inner div, so document-absolute positioning would be wrong.)
       */
      .stdnd-line-indicator {
        position: fixed;
        z-index: 999999;
        pointer-events: none;
        border-radius: 2px;
        display: none;
      }
      /*
       * Highlight applied directly to the element whose slot would be taken
       * (rather than a floating overlay box). An outline doesn't affect layout,
       * so the highlighted item never shifts; the tinted fill previews the
       * displacement. Color is driven by --stdnd-color (set per drag).
       */
      .stdnd-highlight-target {
        outline: 2px solid var(--stdnd-color, #ff4b4b);
        outline-offset: -2px;
        border-radius: 6px;
        background: color-mix(in srgb, var(--stdnd-color, #ff4b4b) 18%, transparent);
        transition: background 0.08s ease;
      }
      /*
       * Ghost indicator: a clone of the dragged item inserted at the
       * prospective drop position. pointer-events:none so it never
       * intercepts dragover events aimed at the container. It wears the same
       * outline + tint as the highlight indicator (driven by --stdnd-color)
       * so the preview slot stands out clearly against the surrounding items.
       *
       * The fade is applied to the ghost's CONTENT only (its children), not
       * the element itself, so the outline + tint stay at full strength and
       * the preview border reads brightly while the cloned content sits faded.
       */
      .stdnd-ghost {
        pointer-events: none;
        border-radius: 6px;
        outline: 2px solid var(--stdnd-color, #ff4b4b);
        outline-offset: -2px;
        background: color-mix(in srgb, var(--stdnd-color, #ff4b4b) 8%, transparent);
      }
      .stdnd-ghost > * {
        opacity: 0.3;
      }
      .stdnd-ghost-materialized {
        opacity: 1;
        outline: none !important;
        background: transparent !important;
        pointer-events: auto;
      }
      .stdnd-ghost-materialized > * {
        opacity: 1;
      }
      /*
       * The dragged source after a drop (ghost mode and line/highlight mode
       * alike). Unlike the in-flight .stdnd-dragging collapse, this is applied
       * only post-drop, when the drag session is already over, so display:none
       * is safe here. It's also necessary: a zero-size element is still a flex
       * item, so the parent's flex gap would reserve space on both sides of
       * it and leave a visible gap. display:none removes it from flex flow
       * entirely (gaps collapse) until Streamlit's rerender swaps in the real
       * moved item.
       */
      .stdnd-source-collapsed {
        display: none !important;
      }
      /*
       * Touch drag image: a clone that floats under the finger while a touch
       * drag is in progress (native HTML5 drag images don't exist on touch).
       * Positioned with fixed left/top set to the touch point; the translate
       * centers it horizontally and nudges it below the fingertip so it stays
       * visible. pointer-events:none keeps elementFromPoint() hitting the real
       * containers underneath.
       */
      .stdnd-touch-clone {
        position: fixed;
        z-index: 1000000;
        pointer-events: none;
        opacity: 0.9;
        transform: translate(-50%, 10px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
        border-radius: 6px;
        overflow: hidden;
      }
      /*
       * Engine-injected placeholder for an empty container. Deliberately a
       * plain element with no margins or min-height, so it sits at the
       * container's natural top inset instead of being pushed down the way an
       * app-rendered markdown hint was. pointer-events:none keeps it from
       * intercepting drop events. Hidden by default; shown only when it's the
       * container's only child, so any real item, ghost preview (live or
       * materialized after a drop), or drop indicator sibling hides it.
       */
      .stdnd-placeholder {
        display: none;
        pointer-events: none;
        opacity: 0.5;
        font-style: italic;
        font-size: 0.875rem;
        line-height: 1.4;
        width: 100%;
        align-self: stretch;
      }
      .stdnd-placeholder:only-child {
        display: block;
      }
    `;
  }

  function getLineEl() {
    if (!lineEl || !PDOC.body.contains(lineEl)) {
      lineEl = PDOC.createElement("div");
      lineEl.className = "stdnd-line-indicator";
      PDOC.body.appendChild(lineEl);
    }
    return lineEl;
  }

  function hideIndicators() {
    if (lineEl) lineEl.style.display = "none";
    if (highlightedEl) {
      highlightedEl.classList.remove("stdnd-highlight-target");
      highlightedEl.style.removeProperty("--stdnd-color");
      highlightedEl = null;
    }
  }

  /**
   * Show the bright insertion line at gap `index` of the container
   * (i.e. the dragged item would be inserted before items[index]).
   */
  function showLine(containerEl, items, index, horizontal, color) {
    const line = getLineEl();
    const crect = containerEl.getBoundingClientRect();
    const THICK = 4;

    let x, y, w, h;
    if (horizontal) {
      // Vertical line between items.
      let edgeX;
      if (items.length === 0) {
        edgeX = crect.left + 4;
      } else if (index >= items.length) {
        const r = items[items.length - 1].getBoundingClientRect();
        edgeX = r.right + 2;
      } else {
        const r = items[index].getBoundingClientRect();
        edgeX = r.left - 2;
      }
      x = edgeX - THICK / 2;
      y = crect.top;
      w = THICK;
      h = crect.height;
    } else {
      // Horizontal line between items.
      let edgeY;
      if (items.length === 0) {
        edgeY = crect.top + 4;
      } else if (index >= items.length) {
        const r = items[items.length - 1].getBoundingClientRect();
        edgeY = r.bottom + 2;
      } else {
        const r = items[index].getBoundingClientRect();
        edgeY = r.top - 2;
      }
      x = crect.left;
      y = edgeY - THICK / 2;
      w = crect.width;
      h = THICK;
    }

    line.style.left = x + "px";
    line.style.top = y + "px";
    line.style.width = w + "px";
    line.style.height = h + "px";
    line.style.background = color;
    line.style.boxShadow = `0 0 6px ${color}`;
    line.style.display = "block";
  }

  /**
   * Highlight the element whose spot would be taken by outlining + tinting it
   * in place (the displaced element itself, not a floating overlay box, so it
   * reads exactly like the limestone engine). Reuses the class on the same
   * element across dragover events and moves it when the target changes.
   */
  function showHighlight(targetEl, color) {
    if (highlightedEl === targetEl) return;
    if (highlightedEl) {
      highlightedEl.classList.remove("stdnd-highlight-target");
      highlightedEl.style.removeProperty("--stdnd-color");
    }
    targetEl.style.setProperty("--stdnd-color", color);
    targetEl.classList.add("stdnd-highlight-target");
    highlightedEl = targetEl;
  }

  // ---------------------------------------------------------------------------
  // Ghost indicator
  // ---------------------------------------------------------------------------

  /**
   * Deep-clone the dragged item for use as a ghost. cloneNode() doesn't copy
   * canvas bitmaps (charts) or current input values, so both are copied
   * explicitly. The clone is inert: no st-key classes (so it's never picked
   * up as a real item), no dnd wiring, no pointer events while previewing.
   */
  function sanitizeClone(clone, item) {
    // Strip identity & wiring so the clone can't be mistaken for a real item.
    clone.classList.remove(
      "stdnd-draggable",
      "stdnd-dragging",
      "stdnd-has-handle",
      "stdnd-border-handle",
      "stdnd-border-hot"
    );
    [...clone.classList].forEach((c) => {
      if (c.startsWith("st-key-")) clone.classList.remove(c);
    });
    clone.querySelectorAll('[class*="st-key-"]').forEach((el) => {
      [...el.classList].forEach((c) => {
        if (c.startsWith("st-key-")) el.classList.remove(c);
      });
    });
    delete clone.dataset.stdndWired;
    delete clone.dataset.stdndContainerKey;
    delete clone.dataset.stdndIndex;
    clone.removeAttribute("draggable");
    clone.querySelector(":scope > .stdnd-handle")?.remove();

    // Copy canvas contents (st.line_chart / st.area_chart etc. render to
    // canvas; cloneNode leaves the cloned canvases blank).
    const srcCanvases = item.querySelectorAll("canvas");
    const dstCanvases = clone.querySelectorAll("canvas");
    for (let i = 0; i < srcCanvases.length; i++) {
      const src = srcCanvases[i];
      const dst = dstCanvases[i];
      if (!dst) continue;
      dst.width = src.width;
      dst.height = src.height;
      try {
        dst.getContext("2d").drawImage(src, 0, 0);
      } catch (err) {
        /* tainted/webgl canvas: clone shows blank chart area */
      }
    }

    // Copy live input/textarea/select values (cloneNode copies attributes,
    // not current DOM state).
    const srcInputs = item.querySelectorAll("input, textarea, select");
    const dstInputs = clone.querySelectorAll("input, textarea, select");
    for (let i = 0; i < srcInputs.length; i++) {
      if (dstInputs[i]) dstInputs[i].value = srcInputs[i].value;
    }
  }

  function buildGhost(item, color) {
    const clone = item.cloneNode(true);
    sanitizeClone(clone, item);
    clone.classList.add("stdnd-ghost", "stdnd-ignore");
    // Drive the ghost's outline + tint from the active drag color, same as
    // the highlight indicator does.
    clone.style.setProperty("--stdnd-color", color);
    // Match the original's rendered width so the preview doesn't reflow
    // text when dropped into a differently-sized column.
    clone.style.minHeight = item.getBoundingClientRect().height + "px";
    return clone;
  }

  /**
   * A clone used as the finger-following drag image on touch devices (native
   * HTML5 drag has no equivalent of a touch drag image). It floats under the
   * finger at fixed position; the real source is collapsed out of flow.
   */
  function buildTouchClone(item) {
    const rect = item.getBoundingClientRect();
    const clone = item.cloneNode(true);
    sanitizeClone(clone, item);
    clone.classList.add("stdnd-touch-clone", "stdnd-ignore");
    clone.style.width = rect.width + "px";
    clone.style.height = rect.height + "px";
    return clone;
  }

  /**
   * Insert/move the ghost so it sits at insertion gap `index` of the
   * container. Reuses the existing ghost element when only the position
   * changes (avoids flicker and listener churn).
   */
  function placeGhost(containerEl, items, index, color) {
    if (!drag) return;

    if (!ghost.el || ghost.materialized) {
      removeGhost();
      ghost.el = buildGhost(drag.item, color);
      ghost.sourceEl = drag.item;
      ghost.materialized = false;
    }

    // Where should the ghost go? Before items[index], or at the end.
    const anchor = index < items.length ? items[index] : null;

    // Already in position? (placeGhost runs on every dragover event.)
    if (anchor ? ghost.el.nextElementSibling === anchor : containerEl.lastElementChild === ghost.el) {
      if (ghost.el.parentElement === containerEl) return;
    }

    if (anchor) {
      containerEl.insertBefore(ghost.el, anchor);
    } else {
      containerEl.appendChild(ghost.el);
    }
  }

  /**
   * On drop: the ghost stops being a preview and becomes the visual
   * stand-in for the real item until Streamlit rerenders. Full opacity,
   * interactive, no dashed outline; the original (still in its old
   * position) is collapsed.
   */
  function materializeGhost() {
    if (!ghost.el) return;
    ghost.materialized = true;
    ghost.destContainer = ghost.el.parentElement;
    ghost.el.classList.remove("stdnd-ghost");
    ghost.el.classList.add("stdnd-ghost-materialized", "stdnd-ignore");
    ghost.el.style.outline = "none";

    if (ghost.sourceEl) {
      ghost.sourceEl.classList.add("stdnd-source-collapsed", "stdnd-ignore");
    }

    // Safety net: if the app doesn't rerun (e.g. the Python side ignores
    // the event), restore reality after a few seconds.
    if (ghost.cleanupTimer) clearTimeout(ghost.cleanupTimer);
    ghost.cleanupTimer = setTimeout(() => {
      if (ghost.materialized) removeGhost();
    }, 5000);
  }

  /** Remove the ghost and undo any source collapse. */
  function removeGhost() {
    if (ghost.cleanupTimer) {
      clearTimeout(ghost.cleanupTimer);
      ghost.cleanupTimer = null;
    }
    if (ghost.el) {
      ghost.el.remove();
      ghost.el = null;
    }
    if (ghost.sourceEl) {
      ghost.sourceEl.classList.remove("stdnd-source-collapsed", "stdnd-ignore");
      ghost.sourceEl = null;
    }
    ghost.destContainer = null;
    ghost.materialized = false;
  }

  /** Remove the ghost only if it's still a hover preview (not materialized). */
  function removeGhostPreview() {
    if (ghost.el && !ghost.materialized) removeGhost();
  }

  /**
   * Backstop cleanup for post-drop artifacts. The observer-driven removeGhost()
   * tracks the source by node identity, but Streamlit reuses and reorders DOM
   * nodes across reruns, so that tracking can miss and leave a real item stuck
   * at display:none (a persistent gap where the dragged item used to be). Once
   * the app has re-rendered, no real item should still be collapsed, so sweep
   * the parent document and reveal any orphans / drop any leftover ghost.
   */
  function revealOrphanCollapsed() {
    for (const el of PDOC.querySelectorAll(".stdnd-source-collapsed")) {
      el.classList.remove("stdnd-source-collapsed", "stdnd-ignore");
    }
    for (const el of PDOC.querySelectorAll(".stdnd-ghost-materialized")) {
      el.remove();
    }
    if (ghost.cleanupTimer) {
      clearTimeout(ghost.cleanupTimer);
      ghost.cleanupTimer = null;
    }
    ghost.el = null;
    ghost.sourceEl = null;
    ghost.destContainer = null;
    ghost.materialized = false;
  }

  /**
   * Line/highlight modes have no destination clone. After a real drop the
   * dragged source must NOT snap back into its old slot before Streamlit's
   * rerender lands, or it flashes there for a frame (the flicker ghost mode
   * avoids). Keep the lifted-out source collapsed and reuse the ghost-cleanup
   * machinery so the MutationObserver restores it once the moved item
   * rerenders.
   */
  function holdSourceUntilRerender(item, destContainer) {
    ghost.sourceEl = item;
    ghost.destContainer = destContainer;
    ghost.materialized = true;
    // Swap the transient drag class for the persistent collapse class so
    // onDragEnd's removal of stdnd-dragging doesn't un-collapse the source.
    item.classList.remove("stdnd-dragging");
    item.classList.add("stdnd-source-collapsed", "stdnd-ignore");

    if (ghost.cleanupTimer) clearTimeout(ghost.cleanupTimer);
    ghost.cleanupTimer = setTimeout(() => {
      if (ghost.materialized) removeGhost();
    }, 5000);
  }

  // ---------------------------------------------------------------------------
  // Drop-position math
  // ---------------------------------------------------------------------------

  /**
   * Given a dragover position, compute the insertion index in the container.
   * Items before whose midpoint the cursor sits are "after" the insertion
   * point.
   */
  function computeInsertIndex(items, horizontal, clientX, clientY) {
    let index = items.length;
    for (let i = 0; i < items.length; i++) {
      // The dragged item is out of flow (collapsed to zero size); skip it so
      // its empty slot can't capture the cursor. Indices stay relative to the
      // full item list, which keeps to_index semantics (and apply_move) intact.
      if (drag && items[i] === drag.item) continue;
      const r = items[i].getBoundingClientRect();
      const mid = horizontal ? r.left + r.width / 2 : r.top + r.height / 2;
      const pos = horizontal ? clientX : clientY;
      if (pos < mid) {
        index = i;
        break;
      }
    }
    return index;
  }

  /**
   * In highlight mode the drop target is the item under the cursor; the
   * dragged element takes its spot. Returns items.length when the cursor is
   * past the last item (append at end).
   */
  function computeTakeIndex(items, horizontal, clientX, clientY) {
    for (let i = 0; i < items.length; i++) {
      // Skip the dragged item's collapsed slot (see computeInsertIndex).
      if (drag && items[i] === drag.item) continue;
      const r = items[i].getBoundingClientRect();
      const start = horizontal ? r.left : r.top;
      const end = horizontal ? r.right : r.bottom;
      const pos = horizontal ? clientX : clientY;
      if (pos >= start && pos <= end) return i;
      if (pos < start) return i;
    }
    return items.length;
  }

  // ---------------------------------------------------------------------------
  // Permission rules
  // ---------------------------------------------------------------------------

  function canDragFrom(containerKey) {
    if (config.sources) return config.sources.includes(containerKey);
    return true;
  }

  function canDropTo(fromKey, toKey) {
    // Source/destination lists take precedence over the `cross` flag.
    if (config.sources || config.destinations) {
      const srcOk = config.sources ? config.sources.includes(fromKey) : true;
      const dstOk = config.destinations
        ? config.destinations.includes(toKey)
        : true;
      if (!srcOk || !dstOk) return false;
      if (fromKey !== toKey) return true;
      // Same-container reorder under explicit lists: container must be
      // both a valid source and a valid destination (checked above).
      return true;
    }
    if (fromKey === toKey) return true;
    return !!config.cross;
  }

  // ---------------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------------

  function wireAll() {
    if (!config) return;
    injectStyles();
    for (const key of config.containers) {
      const el = findContainer(key);
      if (!el) continue;
      wireContainer(el, key);
      // Streamlit reuses DOM nodes across reruns, so a node that was a real
      // draggable item last render can be reused to render an excluded
      // child (e.g. a placeholder hint) this render. getItems() skips
      // excluded children, so they'd otherwise keep their stale wiring and
      // stay draggable — strip it explicitly.
      for (const child of el.children) {
        if (child.dataset.stdndWired === "1" && isExcludedItem(child)) {
          unwireItem(child);
        }
      }
      const items = getItems(el);
      if (canDragFrom(key)) {
        items.forEach((item, i) => wireItem(item, key, i));
      } else {
        // Container is destination-only: strip any stale drag wiring.
        items.forEach((item) => unwireItem(item));
      }
      // Placeholder is always present (when configured); CSS shows it only
      // while it's the container's only child.
      setPlaceholder(el, key);
    }

    // wireAll only runs after a (re)render, so if a previous drop left a
    // source collapsed and the observer's node-identity cleanup missed it,
    // the real item is back now — reveal it so it doesn't leave a gap.
    if (!drag && ghost.materialized) revealOrphanCollapsed();
  }

  function wireContainer(el, key) {
    // The container key is recorded on every wire pass (even when listeners
    // are already attached) so touch hit-testing can map an element under
    // the finger back to its container key.
    el.dataset.stdndKey = key;
    if (el.dataset.stdndContainer === config.instanceId) return;
    el.dataset.stdndContainer = config.instanceId;
    el.addEventListener("dragover", (e) => onDragOver(e, el, key));
    el.addEventListener("drop", (e) => onDrop(e, el, key));
    el.addEventListener("dragleave", (e) => onDragLeave(e, el));
  }

  function wireItem(item, containerKey, index) {
    // (Re-)wire idempotently. DOM nodes can be recreated by Streamlit
    // reruns, so wiring is marked with a data attribute.
    if (item.dataset.stdndWired !== "1") {
      item.dataset.stdndWired = "1";
      item.addEventListener("dragstart", onDragStart);
      item.addEventListener("dragend", onDragEnd);
    }
    item.dataset.stdndContainerKey = containerKey;
    item.dataset.stdndIndex = String(index);

    if (config.handle === "corner") {
      item.draggable = false;
      item.classList.add("stdnd-has-handle");
      item.classList.remove("stdnd-draggable", "stdnd-border-handle");
      removeBorderHandle(item);
      ensureHandle(item, config.handleCorner, config.handleIcon);
    } else if (config.handle === "border") {
      item.draggable = false;
      item.classList.add("stdnd-border-handle");
      item.classList.remove("stdnd-draggable", "stdnd-has-handle");
      // Tint the hover band with the configured indicator color.
      item.style.setProperty("--stdnd-color", config.color);
      removeHandle(item);
      ensureBorderHandle(item);
    } else {
      item.draggable = true;
      item.classList.add("stdnd-draggable");
      item.classList.remove("stdnd-has-handle", "stdnd-border-handle");
      removeHandle(item);
      removeBorderHandle(item);
    }
  }

  function unwireItem(item) {
    item.draggable = false;
    item.classList.remove(
      "stdnd-draggable",
      "stdnd-has-handle",
      "stdnd-border-handle"
    );
    removeHandle(item);
    removeBorderHandle(item);
    delete item.dataset.stdndWired;
    delete item.dataset.stdndContainerKey;
    delete item.dataset.stdndIndex;
  }

  function ensureHandle(item, corner, icon) {
    let handle = item.querySelector(":scope > .stdnd-handle");
    if (!handle) {
      handle = PDOC.createElement("div");
      handle.className = "stdnd-handle";
      handle.title = "Drag to move";
      // The item only becomes draggable while the handle is pressed, so
      // inputs/buttons inside the item keep working normally.
      handle.addEventListener("mousedown", () => {
        item.draggable = true;
      });
      handle.addEventListener("mouseup", () => {
        item.draggable = false;
      });
      item.appendChild(handle);
    }
    // Corner placement: reset then apply, so a rerun can move it.
    handle.classList.remove(
      "stdnd-handle-top-right",
      "stdnd-handle-top-left",
      "stdnd-handle-bottom-right",
      "stdnd-handle-bottom-left"
    );
    handle.classList.add("stdnd-handle-" + corner);
    // Icon: rebuild only when it actually changed.
    if (handle.dataset.stdndIcon !== icon) {
      handle.dataset.stdndIcon = icon;
      setHandleIcon(handle, icon);
    }
  }

  /**
   * Render the handle's icon. A value of the form ":material/<name>:" (the
   * same syntax Streamlit accepts for icons) is drawn with the Material
   * Symbols font already loaded by the host page; anything else (an emoji or
   * plain text) is shown verbatim.
   */
  function setHandleIcon(handle, icon) {
    handle.textContent = "";
    const m = /^:material\/([a-z0-9_]+):$/i.exec(icon || "");
    if (m) {
      const span = PDOC.createElement("span");
      span.className = "stdnd-handle-mi";
      span.translate = false;
      span.textContent = m[1];
      handle.appendChild(span);
    } else {
      handle.textContent = icon || "⠿";
    }
  }

  function removeHandle(item) {
    const handle = item.querySelector(":scope > .stdnd-handle");
    if (handle) handle.remove();
  }

  // Width of the grab band along each edge in border-handle mode.
  const BORDER_BAND = 12;

  /** True if the pointer event lands within the item's edge band. */
  function inBorderBand(item, e) {
    const r = item.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) return false;
    return (
      x - r.left <= BORDER_BAND ||
      r.right - x <= BORDER_BAND ||
      y - r.top <= BORDER_BAND ||
      r.bottom - y <= BORDER_BAND
    );
  }

  /**
   * Wire border-handle behavior onto an item (idempotent). The item only
   * becomes draggable while the pointer presses within its edge band, so the
   * interior stays free for interactive widgets. The listeners no-op unless
   * border mode is currently active AND the item is still a wired dnd item, so
   * a DOM node reused across reruns in a different mode — or reused to render
   * an excluded child (e.g. a placeholder) — never becomes draggable.
   */
  function ensureBorderHandle(item) {
    if (item.dataset.stdndBorderWired === "1") return;
    item.dataset.stdndBorderWired = "1";
    const borderActive = () =>
      config.handle === "border" && item.dataset.stdndWired === "1";
    item.addEventListener("mousemove", (e) => {
      if (!borderActive()) return;
      item.classList.toggle("stdnd-border-hot", inBorderBand(item, e));
    });
    item.addEventListener("mouseleave", () => {
      item.classList.remove("stdnd-border-hot");
    });
    item.addEventListener("mousedown", (e) => {
      if (!borderActive()) return;
      item.draggable = inBorderBand(item, e);
    });
    item.addEventListener("mouseup", () => {
      if (config.handle === "border") item.draggable = false;
    });
  }

  function removeBorderHandle(item) {
    item.classList.remove("stdnd-border-hot");
  }

  // ---------------------------------------------------------------------------
  // Drag event handlers
  // ---------------------------------------------------------------------------

  /**
   * Initialize the shared `drag` state for an item. Used by both the native
   * dragstart handler and the touch fallback. Returns false if the item's
   * container can't be dragged from.
   */
  function beginDrag(item) {
    const containerKey = item.dataset.stdndContainerKey;
    if (!containerKey || !canDragFrom(containerKey)) return false;
    const containerEl = findContainer(containerKey);
    const items = getItems(containerEl);
    drag = {
      item: item,
      fromContainer: containerKey,
      fromIndex: items.indexOf(item),
      itemKey: getItemKey(item),
    };
    return true;
  }

  function onDragStart(e) {
    const item = e.currentTarget;
    if (!beginDrag(item)) {
      e.preventDefault();
      return;
    }
    // Don't let nested draggables (e.g. selected text) hijack the drag.
    e.stopPropagation();

    e.dataTransfer.effectAllowed = "move";
    // Some browsers require data to be set for the drag to start.
    e.dataTransfer.setData("text/plain", drag.itemKey || String(drag.fromIndex));
    // Defer so the browser captures the un-faded element as the drag image.
    setTimeout(() => item.classList.add("stdnd-dragging"), 0);
  }

  function onDragEnd(e) {
    const item = e.currentTarget;
    item.classList.remove("stdnd-dragging");
    if (config && config.handle) item.draggable = false;
    hideIndicators();
    // Cancelled drag: discard the hover preview. (A materialized ghost —
    // i.e. a successful drop — is intentionally left alone here.)
    removeGhostPreview();
    drag = null;
  }

  /**
   * Update the drop indicators for a position over a container. Shared by the
   * native dragover handler and the touch fallback (which feeds it the touch
   * point). Caller is responsible for the drag/permission guards.
   */
  function showDropIndicators(containerEl, clientX, clientY) {
    const horizontal = isHorizontal(containerEl);
    const items = getItems(containerEl);
    const color = config.color;

    if (config.indicator === "highlight") {
      const idx = computeTakeIndex(items, horizontal, clientX, clientY);
      if (idx < items.length && items[idx] !== drag.item) {
        showHighlight(items[idx], color);
        if (lineEl) lineEl.style.display = "none";
      } else if (idx >= items.length) {
        // Appending at the end: highlight the container itself.
        showHighlight(containerEl, color);
        if (lineEl) lineEl.style.display = "none";
      } else {
        hideIndicators();
      }
    } else if (config.indicator === "ghost") {
      const idx = computeInsertIndex(items, horizontal, clientX, clientY);
      placeGhost(containerEl, items, idx, color);
      hideIndicators();
    } else {
      const idx = computeInsertIndex(items, horizontal, clientX, clientY);
      showLine(containerEl, items, idx, horizontal, color);
    }
  }

  function onDragOver(e, containerEl, containerKey) {
    if (!drag) return;
    if (!canDropTo(drag.fromContainer, containerKey)) return;

    e.preventDefault(); // Required to allow dropping.
    e.stopPropagation();
    e.dataTransfer.dropEffect = "move";

    showDropIndicators(containerEl, e.clientX, e.clientY);
  }

  function onDragLeave(e, containerEl) {
    // Only hide when truly leaving the container (not entering a child).
    if (containerEl.contains(e.relatedTarget)) return;
    hideIndicators();
    removeGhostPreview();
  }

  /**
   * The insertion index represented by the ghost's current DOM position:
   * the number of real items that precede it in the container.
   */
  function ghostInsertIndex(containerEl, items) {
    let index = 0;
    for (const child of containerEl.children) {
      if (child === ghost.el) return index;
      if (items.includes(child)) index++;
    }
    return items.length;
  }

  function onDrop(e, containerEl, containerKey) {
    if (!drag) return;
    if (!canDropTo(drag.fromContainer, containerKey)) return;

    e.preventDefault();
    e.stopPropagation();

    performDrop(containerEl, containerKey, e.clientX, e.clientY);
  }

  /**
   * Commit a drop of the active drag onto a container at a screen position.
   * Shared by the native drop handler and the touch fallback; both have
   * already verified `drag` exists and the move is permitted.
   */
  function performDrop(containerEl, containerKey, clientX, clientY) {
    const horizontal = isHorizontal(containerEl);
    const items = getItems(containerEl);

    // In ghost mode the drop position is wherever the ghost preview sits,
    // so what the user sees is exactly what they get.
    let toIndex;
    if (config.indicator === "ghost" && ghost.el && ghost.el.parentElement === containerEl) {
      toIndex = ghostInsertIndex(containerEl, items);
    } else if (config.indicator === "highlight") {
      toIndex = computeTakeIndex(items, horizontal, clientX, clientY);
    } else {
      toIndex = computeInsertIndex(items, horizontal, clientX, clientY);
    }

    const event = {
      event_id: Date.now() + ":" + ++eventCounter,
      from_container: drag.fromContainer,
      to_container: containerKey,
      item_key: drag.itemKey,
      from_index: drag.fromIndex,
      to_index: toIndex,
    };

    hideIndicators();

    // Skip no-op moves (dropping an item back onto its own position).
    if (
      event.from_container === event.to_container &&
      (event.to_index === event.from_index ||
        event.to_index === event.from_index + 1)
    ) {
      drag.item.classList.remove("stdnd-dragging");
      removeGhost();
      drag = null;
      return;
    }

    if (config.indicator === "ghost") {
      // The preview becomes the real thing: full opacity + interactive,
      // original collapsed, until Streamlit's rerender takes over.
      materializeGhost();
    } else {
      // No destination clone in line/highlight mode: keep the source
      // collapsed until the rerender so it doesn't flash back into its old
      // slot.
      holdSourceUntilRerender(drag.item, containerEl);
    }
    drag = null;

    StreamlitProtocol.setComponentValue(event);
  }


  // ---------------------------------------------------------------------------
  // Touch fallback (native HTML5 drag never fires on touch devices)
  // ---------------------------------------------------------------------------

  /** Attach the document-level touch listeners once. */
  function wireTouch() {
    if (touchWired) return;
    touchWired = true;
    // touchmove must be non-passive so it can preventDefault() to stop the
    // page scrolling while a drag is in progress.
    PDOC.addEventListener("touchstart", onTouchStart, { passive: true });
    PDOC.addEventListener("touchmove", onTouchMove, { passive: false });
    PDOC.addEventListener("touchend", onTouchEnd, { passive: true });
    PDOC.addEventListener("touchcancel", onTouchCancel, { passive: true });
  }

  /** Map a screen point to one of this instance's containers, or null. */
  function containerAtPoint(x, y) {
    const target = PDOC.elementFromPoint(x, y);
    if (!target || !target.closest) return null;
    const el = target.closest("[data-stdnd-key]");
    if (!el || el.dataset.stdndContainer !== config.instanceId) return null;
    return el;
  }

  function moveTouchClone(x, y) {
    if (touchDrag && touchDrag.cloneEl) {
      touchDrag.cloneEl.style.left = x + "px";
      touchDrag.cloneEl.style.top = y + "px";
    }
  }

  function removeTouchClone() {
    if (touchDrag && touchDrag.cloneEl) {
      touchDrag.cloneEl.remove();
      touchDrag.cloneEl = null;
    }
  }

  /** Promote a pending touch into a live drag (clone + lifted source). */
  function activateTouchDrag() {
    const item = touchDrag.item;
    if (!beginDrag(item)) {
      touchDrag = null;
      return false;
    }
    touchDrag.active = true;
    // Build the finger-following clone from the still-full item, then collapse
    // the original out of flow (same lifted-out look as the native drag).
    touchDrag.cloneEl = buildTouchClone(item);
    PDOC.body.appendChild(touchDrag.cloneEl);
    item.classList.add("stdnd-dragging");
    return true;
  }

  function onTouchStart(e) {
    if (!config || drag || touchDrag) return;
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    const target = e.target;
    if (!target || !target.closest) return;
    const item = target.closest('[data-stdnd-wired="1"]');
    if (!item) return;
    const containerKey = item.dataset.stdndContainerKey;
    if (!containerKey || !canDragFrom(containerKey)) return;

    // Honor the handle mode: a corner handle requires the touch to land on the
    // grip; a border handle requires the touch to land in the edge band. In
    // both cases the interior stays free for taps on inner widgets.
    if (config.handle === "corner") {
      if (!target.closest(".stdnd-handle")) return;
    } else if (config.handle === "border") {
      if (!inBorderBand(item, t)) return;
    }

    touchDrag = {
      item: item,
      startX: t.clientX,
      startY: t.clientY,
      active: false,
      cloneEl: null,
    };
  }

  function onTouchMove(e) {
    if (!touchDrag) return;
    const t = e.touches[0];
    if (!t) return;

    if (!touchDrag.active) {
      const dx = t.clientX - touchDrag.startX;
      const dy = t.clientY - touchDrag.startY;
      if (Math.hypot(dx, dy) < TOUCH_THRESHOLD) return; // still a tap/scroll
      if (!activateTouchDrag()) return;
    }

    // Now committed to a drag: stop the page from scrolling under the finger.
    e.preventDefault();
    moveTouchClone(t.clientX, t.clientY);

    const containerEl = containerAtPoint(t.clientX, t.clientY);
    if (
      containerEl &&
      canDropTo(drag.fromContainer, containerEl.dataset.stdndKey)
    ) {
      showDropIndicators(containerEl, t.clientX, t.clientY);
    } else {
      hideIndicators();
      removeGhostPreview();
    }
  }

  function onTouchEnd(e) {
    if (!touchDrag) return;
    const item = touchDrag.item;
    const wasActive = touchDrag.active;
    removeTouchClone();
    touchDrag = null;

    if (!wasActive) return; // never crossed the threshold: it was a tap

    const t = e.changedTouches && e.changedTouches[0];
    let dropped = false;
    if (t && drag) {
      const containerEl = containerAtPoint(t.clientX, t.clientY);
      if (
        containerEl &&
        canDropTo(drag.fromContainer, containerEl.dataset.stdndKey)
      ) {
        performDrop(containerEl, containerEl.dataset.stdndKey, t.clientX, t.clientY);
        dropped = true;
      }
    }

    // Native drops rely on dragend to drop the lifted-out class; touch has no
    // dragend, so clear it here (harmless when the source is already collapsed
    // by a ghost/hold).
    item.classList.remove("stdnd-dragging");
    if (!dropped) {
      hideIndicators();
      removeGhostPreview();
      drag = null;
    }
  }

  function onTouchCancel() {
    if (!touchDrag) return;
    const item = touchDrag.item;
    const wasActive = touchDrag.active;
    removeTouchClone();
    touchDrag = null;
    if (!wasActive) return;
    item.classList.remove("stdnd-dragging");
    hideIndicators();
    removeGhostPreview();
    drag = null;
  }


  // ---------------------------------------------------------------------------
  // Re-wiring on Streamlit reruns
  // ---------------------------------------------------------------------------

  function scheduleRewire() {
    if (rewireTimer) clearTimeout(rewireTimer);
    rewireTimer = setTimeout(wireAll, 80);
  }

  /** True for DOM nodes created by this engine (ghost, handles, indicators). */
  function isOwnNode(node) {
    if (!node.classList) return false;
    return (
      node.classList.contains("stdnd-line-indicator") ||
      node.classList.contains("stdnd-handle") ||
      node.classList.contains("stdnd-ghost") ||
      node.classList.contains("stdnd-ghost-materialized")
    );
  }

  function startObserver() {
    if (observer) observer.disconnect();
    const root =
      PDOC.querySelector('[data-testid="stMainBlockContainer"]') || PDOC.body;
    observer = new MutationObserver((mutations) => {
      let streamlitChanged = false;
      let destContainerTouched = false;

      for (const m of mutations) {
        // Ignore mutations caused by our own indicator/ghost/handle elements.
        if (isOwnNode(m.target)) continue;
        const added = [...m.addedNodes].filter((n) => !isOwnNode(n));
        const removed = [...m.removedNodes].filter((n) => !isOwnNode(n));
        if (added.length === 0 && removed.length === 0 && m.type === "childList") {
          continue;
        }
        streamlitChanged = true;

        // Did Streamlit add real children to (or inside) the container the
        // ghost was dropped into? That's the rerender materializing the
        // actual moved item.
        // Streamlit can rerender a reused container by mutating its existing
        // children's content (no added child nodes), so detect any non-own
        // mutation whose target sits within the dest container — not just
        // added children — or a full container replacement.
        if (
          ghost.materialized &&
          ghost.destContainer &&
          (ghost.destContainer.contains(m.target) ||
            added.some((n) => n.contains && n.contains(ghost.destContainer)))
        ) {
          destContainerTouched = true;
        }
      }

      if (!streamlitChanged) return;

      // Streamlit rerendered the destination: the real item now exists in
      // its new spot, so the stand-in ghost is removed *synchronously*
      // (observers run before paint — no frame shows both or neither).
      if (ghost.materialized && destContainerTouched) {
        removeGhost();
      }

      scheduleRewire();
    });
    observer.observe(root, { childList: true, subtree: true });
  }

  // ---------------------------------------------------------------------------
  // Component lifecycle
  // ---------------------------------------------------------------------------

  StreamlitProtocol.onRender(function (args) {
    config = {
      instanceId: String(args.instance_id || "stdnd"),
      containers: args.containers || [],
      cross: args.cross !== false,
      sources: args.sources || null,
      destinations: args.destinations || null,
      exclude: args.exclude || [],
      // string (same text for every container) | object keyed by container
      // key | null (no placeholder).
      placeholder: args.placeholder != null ? args.placeholder : null,
      // false (grab anywhere) | "corner" (icon handle) | "border" (edge band).
      handle:
        args.handle === "border"
          ? "border"
          : args.handle
            ? "corner"
            : false,
      handleCorner: [
        "top-right",
        "top-left",
        "bottom-right",
        "bottom-left",
      ].includes(args.handle_corner)
        ? args.handle_corner
        : "top-right",
      handleIcon:
        typeof args.handle_icon === "string" && args.handle_icon.length
          ? args.handle_icon
          : "⠿",
      indicator: ["highlight", "ghost"].includes(args.indicator)
        ? args.indicator
        : "line",
      color: args.color || "#ff4b4b",
    };

    wireAll();
    startObserver();
    wireTouch();
    // The component itself stays invisible.
    StreamlitProtocol.setFrameHeight(0);
    hideOwnHost();
  });

  /**
   * Collapse the stElementContainer hosting this component's iframe so the
   * invisible component doesn't leave a gap in the page layout.
   */
  function hideOwnHost() {
    try {
      for (const iframe of PDOC.querySelectorAll("iframe")) {
        if (iframe.contentWindow === window) {
          const host = iframe.closest('[data-testid="stElementContainer"]');
          if (host) {
            host.style.display = "none";
            host.classList.add("stdnd-ignore");
          }
          break;
        }
      }
    } catch (e) {
      /* non-fatal */
    }
  }

  StreamlitProtocol.ready();
  StreamlitProtocol.setFrameHeight(0);
})();
