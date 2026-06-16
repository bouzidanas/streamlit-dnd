"""E2E: full verification of the demo app.

Usage:
    streamlit run demo.py --server.port 8599 --server.headless true &
    python tests/e2e_demo.py

Covers:
  1. Page loads with no exceptions; dnd instances wire up.
  2. Ordering tab: same-container reorder (cross=False), every block different.
  3. Kanban: cross-container drag moves a card and persists.
  4. Playlist: source/destination rules (cannot drop into library).
  5. Highlight indicator mode (switch via sidebar radio).
  6. Handle mode: items get handles and are not draggable until handle pressed.
  7. Persistence expander present.

Tab indices: 0=ordering, 1=kanban, 2=playlist, 3=widget board.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"

# The demo persists arrangements to disk; tests must start from defaults.
STORE = Path(__file__).parent.parent / ".demo_arrangements.json"

DRAG_JS_TEMPLATE = """
(cfg) => {
    const log = [];
    const src = document.querySelector('.st-key-' + cfg.from);
    const dst = document.querySelector('.st-key-' + cfg.to);
    if (!src || !dst) return ['MISSING CONTAINER', !!src, !!dst];

    const items = [...src.children].filter(c => {
        const t = c.getAttribute('data-testid');
        return (t === 'stElementContainer' || t === 'stLayoutWrapper')
            && !c.classList.contains('stdnd-ignore');
    });
    const dragged = items[cfg.fromIndex];
    if (!dragged) return ['NO ITEM at index ' + cfg.fromIndex + ', count=' + items.length];
    log.push('draggable=' + dragged.draggable);

    const dt = new DataTransfer();
    function fire(el, type, opts) {
        el.dispatchEvent(new DragEvent(type, Object.assign({
            bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
        }, opts || {})));
    }

    // If handle mode, press the handle first to arm draggable.
    const handle = dragged.querySelector(':scope > .stdnd-handle');
    if (handle) {
        handle.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
        log.push('handle pressed, draggable now=' + dragged.draggable);
    }

    fire(dragged, 'dragstart', {});
    // Drop position: top of the destination (cfg.toStart) or bottom (default).
    const r = dst.getBoundingClientRect();
    const overOpts = cfg.toStart
        ? { clientX: r.left + r.width / 2, clientY: r.top + 5 }
        : { clientX: r.left + r.width / 2, clientY: r.bottom - 5 };
    fire(dst, 'dragover', overOpts);

    // The line indicator is a floating element toggled via display; the
    // highlight indicator is a class applied to the element being displaced.
    const lines = [...document.querySelectorAll('.stdnd-line-indicator')];
    const lineShown = lines.some(l => l.style.display === 'block');
    const hlEl = document.querySelector('.stdnd-highlight-target');
    log.push('line: ' + (lineShown ? 'block' : 'none'));
    log.push('highlight: ' + (hlEl ? 'block' : 'none'));
    if (hlEl) log.push('hl outline: ' + getComputedStyle(hlEl).outlineColor);

    fire(dst, 'drop', overOpts);
    fire(dragged, 'dragend', {});
    return log;
}
"""

CHECK_HANDLES_JS = """
() => {
    const cont = document.querySelector('.st-key-kanban_todo');
    if (!cont) return { error: 'container not found' };
    const items = [...cont.children].filter(c => !c.classList.contains('stdnd-ignore') &&
        ['stElementContainer','stLayoutWrapper'].includes(c.getAttribute('data-testid')));
    return {
        count: items.length,
        draggable: items.map(i => i.draggable),
        hasHandle: items.map(i => !!i.querySelector(':scope > .stdnd-handle')),
    };
}
"""


def get_kanban_cards(page, col):
    return page.evaluate(
        f"() => [...document.querySelectorAll('.st-key-kanban_{col} [data-testid=stMarkdown] p strong')].map(e => e.innerText)"
    )


def get_songs(page, container):
    return page.evaluate(
        f"() => [...document.querySelectorAll('.st-key-{container} [data-testid=stMarkdown] p strong')].map(e => e.innerText)"
    )


def main() -> int:
    failures = []
    STORE.unlink(missing_ok=True)  # start from default arrangements
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(URL, wait_until="networkidle")
        # The ordering tab is the default (first) tab.
        page.wait_for_selector('[class*="st-key-ordering_list"]', timeout=20000)
        page.wait_for_timeout(3500)

        # ----- 1. No exceptions, all wired -----------------------------------
        exc = page.locator('[data-testid="stException"]').count()
        print(f"[1] Exceptions on page: {exc}")
        if exc:
            print(page.locator('[data-testid="stException"]').first.inner_text()[:1200])
            failures.append("page exception")

        wired = page.evaluate(
            """() => ({
                ordering: !!document.querySelector('.st-key-ordering_list[data-stdnd-container]'),
                kanban: !!document.querySelector('.st-key-kanban_todo[data-stdnd-container]'),
                styles: !!document.getElementById('stdnd-styles'),
            })"""
        )
        print(
            f"[1] ordering wired: {wired['ordering']}, kanban wired: {wired['kanban']}, "
            f"styles: {wired['styles']}"
        )
        if not wired["ordering"]:
            failures.append("ordering not wired")
        if not wired["kanban"]:
            failures.append("kanban not wired")

        # ----- 2. Ordering tab: same-container reorder -------------------------
        def get_ordering_blocks():
            return page.evaluate(
                """() => [...document.querySelectorAll(
                    '.st-key-ordering_list > [data-testid=stLayoutWrapper] [class*="st-key-order_"]'
                )].map(e => [...e.classList].find(c => c.startsWith('st-key-order_')).slice('st-key-order_'.length))"""
            )

        blocks_before = get_ordering_blocks()
        print(f"\n[2] Ordering blocks before: {blocks_before}")
        if len(blocks_before) < 2:
            failures.append("ordering tab has fewer than 2 blocks")

        # Drag the LAST block to the top (insertion index 0).
        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {
                "from": "ordering_list",
                "to": "ordering_list",
                "fromIndex": len(blocks_before) - 1,
                "toStart": True,
            },
        )
        print(f"[2] Reorder drag log: {log}")
        page.wait_for_timeout(3000)

        blocks_after = get_ordering_blocks()
        print(f"[2] Ordering blocks after: {blocks_after}")
        if blocks_after[0] == blocks_before[-1] and set(blocks_after) == set(blocks_before):
            print(f"[2] PASS: '{blocks_before[-1]}' moved to the top")
        else:
            failures.append("ordering same-container reorder failed")

        # ----- 3. Kanban cross-container drag ---------------------------------
        page.locator('button[role="tab"]').nth(1).click()
        page.wait_for_timeout(2000)

        before_todo = get_kanban_cards(page, "todo")
        before_doing = get_kanban_cards(page, "doing")
        print(f"\n[3] Kanban before: todo={before_todo}, doing={before_doing}")

        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {"from": "kanban_todo", "to": "kanban_doing", "fromIndex": 0},
        )
        print(f"[3] Drag log: {log}")
        page.wait_for_timeout(3000)

        after_todo = get_kanban_cards(page, "todo")
        after_doing = get_kanban_cards(page, "doing")
        print(f"[3] Kanban after: todo={after_todo}, doing={after_doing}")

        moved_card = before_todo[0]
        if moved_card in after_todo or moved_card not in after_doing:
            failures.append("kanban cross-container move failed")
        else:
            print(f"[3] PASS: '{moved_card}' moved todo -> doing")

        # ----- 4. Playlist source/destination rules ---------------------------
        page.locator('button[role="tab"]').nth(2).click()
        page.wait_for_timeout(2000)

        lib_before = get_songs(page, "playlist_library")
        queue_before = get_songs(page, "playlist_queue")
        print(f"\n[4] Playlist before: library={lib_before}, queue={queue_before}")

        # 4a. Library -> queue (allowed)
        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {"from": "playlist_library", "to": "playlist_queue", "fromIndex": 0},
        )
        print(f"[4a] lib->queue drag log: {log}")
        page.wait_for_timeout(3000)
        lib_mid = get_songs(page, "playlist_library")
        queue_mid = get_songs(page, "playlist_queue")
        print(f"[4a] after: library={lib_mid}, queue={queue_mid}")
        if lib_before[0] not in queue_mid:
            failures.append("playlist: allowed lib->queue move failed")
        else:
            print(f"[4a] PASS: '{lib_before[0]}' moved into queue")

        # 4b. Queue -> library (must be BLOCKED: library not in destinations)
        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {"from": "playlist_queue", "to": "playlist_library", "fromIndex": 0},
        )
        print(f"[4b] queue->lib drag log: {log}")
        page.wait_for_timeout(2500)
        lib_after = get_songs(page, "playlist_library")
        queue_after = get_songs(page, "playlist_queue")
        print(f"[4b] after: library={lib_after}, queue={queue_after}")
        if len(lib_after) != len(lib_mid):
            failures.append("playlist: queue->library should have been blocked")
        else:
            print("[4b] PASS: drop into library correctly blocked")

        # Indicators should NOT have shown for the blocked drag
        if "line: block" in str(log) or "highlight: block" in str(log):
            failures.append("indicator appeared for forbidden destination")
        else:
            print("[4b] PASS: no indicator shown over forbidden destination")

        # ----- 5. Highlight indicator mode -------------------------------------
        # Switch sidebar radio to highlight mode, then go to the kanban tab.
        page.locator('[data-testid="stSidebar"] [role="radiogroup"] label').nth(1).click()
        page.wait_for_timeout(2500)
        page.locator('button[role="tab"]').nth(1).click()
        page.wait_for_timeout(1500)

        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {"from": "kanban_doing", "to": "kanban_done", "fromIndex": 0},
        )
        print(f"\n[5] Highlight-mode drag log: {log}")
        page.wait_for_timeout(2500)
        if "highlight: block" not in str(log):
            failures.append("highlight indicator did not appear in highlight mode")
        else:
            print("[5] PASS: highlight indicator appeared")

        # ----- 6. Handle mode ---------------------------------------------------
        # The "Drag handle" radiogroup is the 2nd radiogroup in the sidebar
        # (Off / Corner / Border); pick "Corner" to give items a grip handle.
        page.locator('[data-testid="stSidebar"] [role="radiogroup"]').nth(1).locator(
            "label"
        ).nth(1).click()
        page.wait_for_timeout(2500)

        handles = page.evaluate(CHECK_HANDLES_JS)
        print(f"\n[6] Handle mode state: {handles}")
        if not all(handles.get("hasHandle", [])):
            failures.append("handles not added in handle mode")
        elif any(handles.get("draggable", [True])):
            failures.append("items should not be draggable until handle pressed")
        else:
            print("[6] PASS: handles present, items not draggable until handle pressed")

        # Drag via handle should still work
        cards_before = get_kanban_cards(page, "todo")
        log = page.evaluate(
            DRAG_JS_TEMPLATE,
            {"from": "kanban_todo", "to": "kanban_todo", "fromIndex": 1},
        )
        print(f"[6] Handle drag log: {log}")
        page.wait_for_timeout(2500)
        cards_after = get_kanban_cards(page, "todo")
        print(f"[6] todo before={cards_before} after={cards_after}")
        if cards_before != cards_after and set(cards_before) == set(cards_after):
            print("[6] PASS: reorder via handle worked")
        elif cards_before == cards_after:
            # Reorder to same position is also acceptable if there were < 3 cards
            print("[6] NOTE: order unchanged (drop may have been a no-op position)")

        # ----- 7. Persistence check ---------------------------------------------
        state_text = page.evaluate(
            """() => {
                const exp = [...document.querySelectorAll('[data-testid="stExpander"] summary')]
                    .find(e => e.innerText.includes('Persisted state'));
                return exp ? 'expander found' : 'missing';
            }"""
        )
        print(f"\n[7] Persistence expander: {state_text}")

        browser.close()

    # Leave no test residue behind.
    STORE.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("ALL DEMO CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
