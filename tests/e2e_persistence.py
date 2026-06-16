"""E2E: verify arrangements persist across page refreshes and reset works.

Usage:
    streamlit run demo.py --server.port 8599 --server.headless true &
    python tests/e2e_persistence.py

Covers:
  1. Fresh start: defaults shown, no store file.
  2. Drag a kanban card -> store file is written.
  3. Page reload (new Streamlit session) -> moved card is still in its new
     column.
  4. Full browser restart (new context) -> arrangement still there.
  5. Reset button -> defaults restored AND store file deleted.
  6. Reload after reset -> still defaults (reset survives refresh too).
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"
STORE = Path(__file__).parent.parent / ".demo_arrangements.json"

DRAG_JS = """
(cfg) => {
    const src = document.querySelector('.st-key-' + cfg.from);
    const dst = document.querySelector('.st-key-' + cfg.to);
    if (!src || !dst) return 'MISSING: src=' + !!src + ' dst=' + !!dst;
    const items = [...src.children].filter(c => {
        const t = c.getAttribute('data-testid');
        return (t === 'stElementContainer' || t === 'stLayoutWrapper')
            && !c.classList.contains('stdnd-ignore');
    });
    const dragged = items[cfg.fromIndex];
    if (!dragged) return 'NO ITEM';
    const dt = new DataTransfer();
    function fire(el, type, opts) {
        el.dispatchEvent(new DragEvent(type, Object.assign({
            bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
        }, opts || {})));
    }
    fire(dragged, 'dragstart', {});
    const r = dst.getBoundingClientRect();
    const opts = { clientX: r.left + r.width / 2, clientY: r.bottom - 5 };
    fire(dst, 'dragover', opts);
    fire(dst, 'drop', opts);
    fire(dragged, 'dragend', {});
    return 'OK';
}
"""


def goto_kanban(page):
    page.goto(URL, wait_until="networkidle")
    page.wait_for_selector('[class*="st-key-ordering_list"]', timeout=20000)
    page.wait_for_timeout(3000)
    page.locator('button[role="tab"]').nth(1).click()
    page.wait_for_timeout(2000)


def get_cards(page, col):
    return page.evaluate(
        f"() => [...document.querySelectorAll('.st-key-kanban_{col} [data-testid=stMarkdown] p strong')].map(e => e.innerText)"
    )


def main() -> int:
    failures = []

    # Make sure we start clean.
    STORE.unlink(missing_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ----- 1. Fresh start: defaults, no store file ------------------------
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        goto_kanban(page)
        todo = get_cards(page, "todo")
        doing = get_cards(page, "doing")
        print(f"[1] Fresh: todo={todo}, doing={doing}")
        if todo != ["Write spec", "Design schema", "Set up CI"] or doing != ["Build API"]:
            failures.append("fresh start should show defaults")
        if STORE.exists():
            failures.append("store file should not exist before any move")

        # ----- 2. Drag a card -> file written ----------------------------------
        result = page.evaluate(
            DRAG_JS, {"from": "kanban_todo", "to": "kanban_doing", "fromIndex": 0}
        )
        print(f"[2] Drag result: {result}")
        page.wait_for_timeout(3000)

        todo2 = get_cards(page, "todo")
        doing2 = get_cards(page, "doing")
        print(f"[2] After drag: todo={todo2}, doing={doing2}")
        if "Write spec" in todo2 or "Write spec" not in doing2:
            failures.append("drag did not move the card")
        if not STORE.exists():
            failures.append("store file was not written after the move")
        else:
            print(f"[2] PASS: store file written ({STORE.stat().st_size} bytes)")

        # ----- 3. Page reload (same browser, new Streamlit session) ------------
        goto_kanban(page)
        todo3 = get_cards(page, "todo")
        doing3 = get_cards(page, "doing")
        print(f"[3] After reload: todo={todo3}, doing={doing3}")
        if "Write spec" in todo3 or "Write spec" not in doing3:
            failures.append("arrangement lost after page reload")
        else:
            print("[3] PASS: arrangement survived page reload")
        page.close()

        # ----- 4. Entirely new browser context (like new visitor/restart) ------
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        goto_kanban(page)
        todo4 = get_cards(page, "todo")
        doing4 = get_cards(page, "doing")
        print(f"[4] New browser context: todo={todo4}, doing={doing4}")
        if "Write spec" in todo4 or "Write spec" not in doing4:
            failures.append("arrangement lost in new browser context")
        else:
            print("[4] PASS: arrangement survived new browser context")

        # ----- 5. Reset button -> defaults + file deleted -----------------------
        page.locator('[data-testid="stSidebar"] button', has_text="Reset").click()
        page.wait_for_timeout(3000)
        # After reset we land back on the first tab; go to kanban again.
        page.locator('button[role="tab"]').nth(1).click()
        page.wait_for_timeout(1500)

        todo5 = get_cards(page, "todo")
        doing5 = get_cards(page, "doing")
        print(f"[5] After reset: todo={todo5}, doing={doing5}")
        if todo5 != ["Write spec", "Design schema", "Set up CI"] or doing5 != ["Build API"]:
            failures.append("reset did not restore defaults")
        else:
            print("[5] PASS: reset restored defaults")
        if STORE.exists():
            failures.append("reset should delete the store file")
        else:
            print("[5] PASS: store file deleted by reset")

        # ----- 6. Reload after reset -> still defaults ---------------------------
        goto_kanban(page)
        todo6 = get_cards(page, "todo")
        doing6 = get_cards(page, "doing")
        print(f"[6] Reload after reset: todo={todo6}, doing={doing6}")
        if todo6 != ["Write spec", "Design schema", "Set up CI"] or doing6 != ["Build API"]:
            failures.append("defaults not stable after reset + reload")
        else:
            print("[6] PASS: reset persists across reload")

        # No exceptions anywhere
        exc = page.locator('[data-testid="stException"]').count()
        if exc:
            failures.append("page exception")
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
    print("ALL PERSISTENCE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
