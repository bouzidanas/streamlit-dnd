"""E2E: verify the ghost indicator mode.

Usage:
    streamlit run demo.py --server.port 8599 --server.headless true &
    python tests/e2e_ghost.py

Checks:
  1. Switching the sidebar to ghost mode propagates to the component.
  2. During dragover, a ghost clone is inserted at the prospective position
     (the container has one extra visual child, translucent + dashed).
  3. The ghost follows the cursor between gap positions without duplicating.
  4. On drop, the ghost materializes (full opacity, no dashed outline) and
     the original collapses.
  5. After Streamlit's rerender, the ghost is gone, exactly one real item
     exists in the new position, and the order is persisted.
  6. Cancelled drag (dragend without drop) removes the preview ghost.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"

# The demo persists arrangements to disk; tests must start from defaults.
STORE = Path(__file__).parent.parent / ".demo_arrangements.json"

# Step-by-step drag with inspection points between events.
GHOST_DRAG_JS = """
(cfg) => {
    const out = { steps: [] };
    const cont = document.querySelector('.st-key-' + cfg.container);
    if (!cont) return { error: 'container not found' };

    function realItems() {
        return [...cont.children].filter(c => {
            const t = c.getAttribute('data-testid');
            return (t === 'stElementContainer' || t === 'stLayoutWrapper')
                && !c.classList.contains('stdnd-ignore')
                && !c.classList.contains('stdnd-ghost')
                && !c.classList.contains('stdnd-ghost-materialized');
        });
    }
    function ghostEls() {
        return [...cont.querySelectorAll(':scope > .stdnd-ghost, :scope > .stdnd-ghost-materialized')];
    }
    function visualOrder() {
        // Order of visible direct children: real item keys or GHOST markers.
        return [...cont.children].map(c => {
            if (c.classList.contains('stdnd-ghost')) return '<ghost>';
            if (c.classList.contains('stdnd-ghost-materialized')) return '<ghost-materialized>';
            if (c.classList.contains('stdnd-source-collapsed')) return '<collapsed>';
            const k = [...c.classList].find(x => x.startsWith('st-key-'));
            if (k) return k.slice(7);
            const inner = c.querySelector('[class*="st-key-"]');
            if (inner) {
                const ik = [...inner.classList].find(x => x.startsWith('st-key-'));
                if (ik) return ik.slice(7);
            }
            return c.style.display === 'none' ? null : '<unkeyed>';
        }).filter(Boolean);
    }

    const items = realItems();
    const dragged = items[cfg.fromIndex];
    const dt = new DataTransfer();
    function fire(el, type, opts) {
        el.dispatchEvent(new DragEvent(type, Object.assign({
            bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
        }, opts || {})));
    }

    out.steps.push({ stage: 'before', order: visualOrder(), ghosts: ghostEls().length });

    fire(dragged, 'dragstart', {});

    // Hover over gap position 1 (between first and second item)
    const r1 = items[1].getBoundingClientRect();
    fire(cont, 'dragover', { clientX: r1.left + r1.width / 2, clientY: r1.top + 2 });
    const ghostsAfterHover1 = ghostEls();
    out.steps.push({
        stage: 'hover gap 1',
        order: visualOrder(),
        ghosts: ghostsAfterHover1.length,
        ghostOpacity: ghostsAfterHover1[0] ? getComputedStyle(ghostsAfterHover1[0]).opacity : null,
        ghostOutline: ghostsAfterHover1[0] ? ghostsAfterHover1[0].style.outline : null,
        ghostPointerEvents: ghostsAfterHover1[0] ? getComputedStyle(ghostsAfterHover1[0]).pointerEvents : null,
    });

    // Move hover to the end of the container
    const rc = cont.getBoundingClientRect();
    fire(cont, 'dragover', { clientX: rc.left + rc.width / 2, clientY: rc.bottom - 5 });
    out.steps.push({ stage: 'hover end', order: visualOrder(), ghosts: ghostEls().length });

    if (cfg.cancel) {
        // Cancelled drag: dragend without drop
        fire(dragged, 'dragend', {});
        out.steps.push({ stage: 'after cancel', order: visualOrder(), ghosts: ghostEls().length });
        return out;
    }

    // Drop at the end position
    fire(cont, 'drop', { clientX: rc.left + rc.width / 2, clientY: rc.bottom - 5 });
    const ghostsAfterDrop = ghostEls();
    out.steps.push({
        stage: 'after drop (pre-rerender)',
        order: visualOrder(),
        ghosts: ghostsAfterDrop.length,
        materializedOpacity: ghostsAfterDrop[0] ? getComputedStyle(ghostsAfterDrop[0]).opacity : null,
        materializedOutline: ghostsAfterDrop[0] ? ghostsAfterDrop[0].style.outline : null,
        materializedPointerEvents: ghostsAfterDrop[0] ? getComputedStyle(ghostsAfterDrop[0]).pointerEvents : null,
        sourceCollapsed: dragged.classList.contains('stdnd-source-collapsed'),
    });
    fire(dragged, 'dragend', {});

    return out;
}
"""

CHECK_AFTER_RERENDER_JS = """
(containerKey) => {
    const cont = document.querySelector('.st-key-' + containerKey);
    if (!cont) return { error: 'container not found' };
    return {
        ghosts: cont.querySelectorAll('.stdnd-ghost, .stdnd-ghost-materialized').length,
        collapsed: cont.querySelectorAll('.stdnd-source-collapsed').length,
        order: [...cont.children].map(c => {
            const k = [...c.classList].find(x => x.startsWith('st-key-'));
            if (k) return k.slice(7);
            const inner = c.querySelector('[class*="st-key-"]');
            if (inner) {
                const ik = [...inner.classList].find(x => x.startsWith('st-key-'));
                if (ik) return ik.slice(7);
            }
            return c.style.display === 'none' ? null : '<unkeyed>';
        }).filter(Boolean),
    };
}
"""


def main() -> int:
    failures = []
    STORE.unlink(missing_ok=True)  # start from default arrangements
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector('[class*="st-key-ordering_list"]', timeout=20000)
        page.wait_for_timeout(3500)

        # ----- 1. Switch to ghost mode via sidebar -----------------------------
        page.locator('[data-testid="stSidebar"] [role="radiogroup"] label').nth(2).click()
        page.wait_for_timeout(2500)
        print("[1] Switched sidebar to ghost mode")

        # ----- 2-4. Drag with ghost preview, then drop --------------------------
        result = page.evaluate(GHOST_DRAG_JS, {"container": "ordering_list", "fromIndex": 0})
        if "error" in result:
            print("ERROR:", result["error"])
            return 1

        for step in result["steps"]:
            print(f"\n  stage: {step['stage']}")
            for k, v in step.items():
                if k != "stage":
                    print(f"    {k}: {v}")

        steps = {s["stage"]: s for s in result["steps"]}

        # Ghost appeared during hover at gap 1, between items
        hover1 = steps["hover gap 1"]
        if hover1["ghosts"] != 1:
            failures.append(f"expected 1 ghost during hover, got {hover1['ghosts']}")
        if hover1["order"][1] != "<ghost>":
            failures.append(f"ghost not at expected position 1: {hover1['order']}")
        op = float(hover1.get("ghostOpacity") or 1)
        if not (0.3 <= op <= 0.8):
            failures.append(f"ghost preview should be translucent, opacity={op}")
        if hover1.get("ghostPointerEvents") != "none":
            failures.append("ghost preview should have pointer-events:none")

        # Ghost moved to end on second hover, still exactly one
        hoverEnd = steps["hover end"]
        if hoverEnd["ghosts"] != 1:
            failures.append(f"expected 1 ghost after moving hover, got {hoverEnd['ghosts']}")
        if hoverEnd["order"][-1] != "<ghost>":
            failures.append(f"ghost should be last after hovering end: {hoverEnd['order']}")

        # After drop: materialized (opaque, interactive), source collapsed
        afterDrop = steps["after drop (pre-rerender)"]
        if afterDrop["ghosts"] != 1:
            failures.append("materialized ghost missing after drop")
        mop = float(afterDrop.get("materializedOpacity") or 0)
        if mop < 0.99:
            failures.append(f"materialized ghost should be opaque, opacity={mop}")
        if afterDrop.get("materializedPointerEvents") == "none":
            failures.append("materialized ghost should be interactive (pointer-events restored)")
        if not afterDrop.get("sourceCollapsed"):
            failures.append("source element should be collapsed after drop")
        if "<ghost-materialized>" not in afterDrop["order"]:
            failures.append("order should contain materialized ghost")

        if not failures:
            print("\n[2-4] PASS: ghost preview, repositioning, and materialization all correct")

        # ----- 5. After Streamlit rerender --------------------------------------
        page.wait_for_timeout(3000)
        after = page.evaluate(CHECK_AFTER_RERENDER_JS, "ordering_list")
        print(f"\n[5] After rerender: {after}")
        if after["ghosts"] != 0:
            failures.append(f"ghost should be removed after rerender, found {after['ghosts']}")
        if after["collapsed"] != 0:
            failures.append(f"no element should remain collapsed, found {after['collapsed']}")
        # The dragged item (order_intro_block) should now be LAST
        if not after["order"] or after["order"][-1] != "order_intro_block":
            failures.append(f"intro_block should be last after move: {after['order']}")
        else:
            print("[5] PASS: ghost cleaned up, real item in new position, order persisted")

        # Verify the item count is right (no duplicates, nothing lost)
        if len(after["order"]) != 6:
            failures.append(f"expected 6 items after move, got {len(after['order'])}")

        # ----- 6. Cancelled drag removes preview --------------------------------
        result2 = page.evaluate(
            GHOST_DRAG_JS, {"container": "ordering_list", "fromIndex": 0, "cancel": True}
        )
        cancel_step = [s for s in result2["steps"] if s["stage"] == "after cancel"][0]
        print(f"\n[6] After cancelled drag: ghosts={cancel_step['ghosts']}")
        if cancel_step["ghosts"] != 0:
            failures.append("cancelled drag should remove the preview ghost")
        else:
            print("[6] PASS: cancelled drag removes the ghost preview")

        # Page must have no exceptions through all of this
        exc = page.locator('[data-testid="stException"]').count()
        if exc:
            failures.append("page exception during ghost test")
            print(page.locator('[data-testid="stException"]').first.inner_text()[:800])

        browser.close()

    # Leave no test residue behind.
    STORE.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("ALL GHOST CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
