"""Dump the rendered DOM of the probe app using Playwright."""

import json
import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        # Wait for Streamlit to finish rendering
        page.wait_for_selector('[class*="st-key-probe_container_a"]', timeout=20000)
        page.wait_for_timeout(2000)

        # 1. Check iframe parent access result
        try:
            frame = page.frame_locator("iframe").first
            probe_result = frame.locator("#probe-result").inner_text(timeout=5000)
        except Exception as e:  # noqa: BLE001
            probe_result = f"ERROR: {e}"
        print("IFRAME PARENT ACCESS:", probe_result)
        print("=" * 80)

        # 2. Walk the DOM tree around keyed containers and print structure
        structure = page.evaluate(
            """
            () => {
                const lines = [];
                function describe(el) {
                    const cls = (typeof el.className === 'string' ? el.className : '')
                        .split(/\\s+/).filter(c => c).slice(0, 6).join('.');
                    const tid = el.getAttribute && el.getAttribute('data-testid');
                    return el.tagName.toLowerCase()
                        + (tid ? `[data-testid=${tid}]` : '')
                        + (cls ? '.' + cls : '');
                }
                function walk(el, depth, maxDepth) {
                    if (depth > maxDepth) return;
                    lines.push('  '.repeat(depth) + describe(el));
                    for (const child of el.children) walk(child, depth + 1, maxDepth);
                }

                // Find each keyed probe container and walk down 4 levels
                for (const sel of ['probe_container_a', 'probe_container_c', 'probe_container_d']) {
                    const el = document.querySelector(`.st-key-${sel}`);
                    lines.push('');
                    lines.push(`########## .st-key-${sel} ##########`);
                    if (!el) { lines.push('NOT FOUND'); continue; }
                    walk(el, 0, 5);
                }

                // Also walk UP from a keyed button to see ancestor chain
                lines.push('');
                lines.push('########## ANCESTORS of .st-key-probe_btn_1 (up to container a) ##########');
                let node = document.querySelector('.st-key-probe_btn_1');
                if (!node) lines.push('NOT FOUND');
                while (node && !node.classList.contains('st-key-probe_container_a')) {
                    lines.push(describe(node));
                    node = node.parentElement;
                }
                if (node) lines.push('-> ' + describe(node));

                // Check direct children of the vertical block inside container a
                lines.push('');
                lines.push('########## Distance: container -> child elements ##########');
                const cont = document.querySelector('.st-key-probe_container_a');
                if (cont) {
                    const btn = document.querySelector('.st-key-probe_btn_1');
                    let hops = 0;
                    let cur = btn;
                    while (cur && cur !== cont) { cur = cur.parentElement; hops++; }
                    lines.push(`hops from .st-key-probe_btn_1 up to .st-key-probe_container_a: ${hops}`);
                    // What does the container's child chain look like?
                    lines.push(`container tag: ${describe(cont)}`);
                    lines.push(`container children count: ${cont.children.length}`);
                    for (const c of cont.children) {
                        lines.push(`  child: ${describe(c)} (children: ${c.children.length})`);
                        for (const cc of c.children) {
                            lines.push(`    grandchild: ${describe(cc)}`);
                        }
                    }
                }
                return lines.join('\\n');
            }
            """
        )
        print(structure)

        # 3. Dump data-testid inventory
        testids = page.evaluate(
            """
            () => {
                const ids = {};
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const t = el.getAttribute('data-testid');
                    ids[t] = (ids[t] || 0) + 1;
                });
                return ids;
            }
            """
        )
        print("\n########## data-testid inventory ##########")
        print(json.dumps(testids, indent=2, sort_keys=True))

        browser.close()


if __name__ == "__main__":
    main()
