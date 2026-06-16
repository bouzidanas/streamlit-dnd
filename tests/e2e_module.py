"""E2E: verify streamlit_dnd wiring and simulate a drag-and-drop with Playwright.

Usage:
    streamlit run tests/minimal_app.py --server.port 8599 --server.headless true &
    python tests/e2e_module.py

HTML5 drag-and-drop can't be triggered by mouse moves alone in Chromium;
we dispatch the DragEvent sequence (dragstart -> dragover -> drop -> dragend)
on the parent document elements directly, which exercises the exact handlers
the component wires up.
"""

import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"


CHECK_WIRING_JS = """
() => {
    const out = {};
    const contA = document.querySelector('.st-key-cont_a');
    const contB = document.querySelector('.st-key-cont_b');
    out.cont_a_found = !!contA;
    out.cont_b_found = !!contB;
    if (!contA || !contB) return out;

    out.cont_a_marked = contA.dataset.stdndContainer || null;
    out.cont_b_marked = contB.dataset.stdndContainer || null;

    const items = [];
    for (const c of contA.children) {
        items.push({
            testid: c.getAttribute('data-testid'),
            draggable: c.draggable,
            wired: c.dataset.stdndWired || null,
            index: c.dataset.stdndIndex || null,
            containerKey: c.dataset.stdndContainerKey || null,
            classes: [...c.classList].filter(x => x.startsWith('st-key-') || x.startsWith('stdnd-')),
        });
    }
    out.cont_a_items = items;

    const itemsB = [];
    for (const c of contB.children) {
        itemsB.push({
            testid: c.getAttribute('data-testid'),
            draggable: c.draggable,
            classes: [...c.classList].filter(x => x.startsWith('st-key-') || x.startsWith('stdnd-')),
        });
    }
    out.cont_b_items = itemsB;

    out.styles_injected = !!document.getElementById('stdnd-styles');
    out.dnd_iframe_hidden = (() => {
        for (const f of document.querySelectorAll('iframe')) {
            const host = f.closest('[data-testid="stElementContainer"]');
            if (host && host.style.display === 'none') return true;
        }
        return false;
    })();
    return out;
}
"""

# Simulate a full drag of item 0 in cont_a to the end of cont_b using
# synthesized DragEvents (Chromium honors synthetic DragEvent dispatch for
# listeners, which is what our engine uses).
SIMULATE_DRAG_JS = """
() => {
    const log = [];
    const contA = document.querySelector('.st-key-cont_a');
    const contB = document.querySelector('.st-key-cont_b');
    const items = [...contA.children].filter(c => {
        const t = c.getAttribute('data-testid');
        return t === 'stElementContainer' || t === 'stLayoutWrapper';
    });
    const dragged = items[0];
    log.push('dragging: ' + [...dragged.classList].filter(x => x.startsWith('st-key')).join(','));

    const dt = new DataTransfer();

    function fire(el, type, opts) {
        const ev = new DragEvent(type, Object.assign({
            bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
        }, opts || {}));
        el.dispatchEvent(ev);
        return ev;
    }

    // dragstart on the dragged item
    fire(dragged, 'dragstart', {});

    // dragover near the bottom of cont_b
    const rB = contB.getBoundingClientRect();
    const overOpts = { clientX: rB.left + rB.width / 2, clientY: rB.bottom - 5 };
    fire(contB, 'dragover', overOpts);

    // Capture indicator state while hovering. Line mode uses a floating
    // element toggled via display; highlight mode adds a class to the
    // displaced element (this app runs in line mode, so highlight is absent).
    const line = document.querySelector('.stdnd-line-indicator');
    const hl = document.querySelector('.stdnd-highlight-target');
    log.push('line visible during dragover: ' + (line ? line.style.display : 'no element'));
    log.push('highlight target during dragover: ' + (hl ? 'present' : 'none'));
    if (line && line.style.display === 'block') {
        log.push('line color: ' + line.style.background);
    }

    // drop on cont_b
    fire(contB, 'drop', overOpts);
    // dragend on the item
    fire(dragged, 'dragend', {});

    return log;
}
"""


def main() -> int:
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        console_errors = []
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector('[class*="st-key-cont_a"]', timeout=20000)
        # Give the component time to wire up.
        page.wait_for_timeout(3500)

        exc = page.locator('[data-testid="stException"]').count()
        if exc:
            print("PAGE EXCEPTION:")
            print(page.locator('[data-testid="stException"]').first.inner_text()[:1500])
            failures.append("page exception")

        wiring = page.evaluate(CHECK_WIRING_JS)
        print("=== WIRING ===")
        for k, v in wiring.items():
            print(f"  {k}: {v}")

        if not wiring.get("cont_a_marked"):
            failures.append("container A not wired")
        if not wiring.get("styles_injected"):
            failures.append("styles not injected")
        items_a = wiring.get("cont_a_items", [])
        draggable_items = [i for i in items_a if i["draggable"]]
        if not draggable_items:
            failures.append("no draggable items in container A")

        # Simulate the drag
        print("\n=== DRAG SIMULATION ===")
        order_before = page.evaluate(
            "() => [...document.querySelectorAll('.st-key-cont_a [data-testid=stMarkdown]')].map(e => e.innerText)"
        )
        print("order in A before:", order_before)
        log = page.evaluate(SIMULATE_DRAG_JS)
        for line in log:
            print(" ", line)

        # The drop should trigger setComponentValue -> Python rerun -> moved item
        page.wait_for_timeout(3000)

        order_a_after = page.evaluate(
            "() => [...document.querySelectorAll('.st-key-cont_a [data-testid=stMarkdown]')].map(e => e.innerText)"
        )
        order_b_after = page.evaluate(
            "() => [...document.querySelectorAll('.st-key-cont_b [data-testid=stMarkdown]')].map(e => e.innerText)"
        )
        print("order in A after:", order_a_after)
        print("order in B after:", order_b_after)

        body = page.locator('[data-testid="stMainBlockContainer"]').inner_text()
        print("\n=== PAGE STATE ===")
        for line in body.splitlines():
            if "Order" in line or "Last event" in line or "[" in line:
                print(" ", line)

        # Check the move actually happened (Alpha moved from A to B)
        if "Alpha" in str(order_a_after):
            failures.append("item did not leave container A")
        if "Alpha" not in str(order_b_after):
            failures.append("item did not arrive in container B")

        if console_errors:
            print("\n=== CONSOLE ERRORS ===")
            for e in console_errors[:10]:
                print(" ", e[:300])

        browser.close()

    print("\n" + "=" * 50)
    if failures:
        print("FAILURES:", failures)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
