"""Second probe: horizontal containers, columns, dataframes, iframe parent access."""

from playwright.sync_api import sync_playwright

JS_WALK = """
() => {
    const lines = [];
    function describe(el) {
        const cls = (typeof el.className === 'string' ? el.className : '')
            .split(/\\s+/).filter(c => c).slice(0, 5).join('.');
        const tid = el.getAttribute && el.getAttribute('data-testid');
        return el.tagName.toLowerCase() + (tid ? '[' + tid + ']' : '') + (cls ? '.' + cls : '');
    }
    for (const k of ['probe_container_d', 'probe_container_e', 'probe_container_f', 'probe_container_b']) {
        lines.push('');
        lines.push('##### .st-key-' + k + ' #####');
        const el = document.querySelector('.st-key-' + k);
        if (!el) { lines.push('NOT FOUND'); continue; }
        lines.push(describe(el));
        for (const c of el.children) {
            lines.push('  CHILD: ' + describe(c));
            for (const cc of c.children) lines.push('    ' + describe(cc));
        }
    }
    // List all iframes
    lines.push('');
    lines.push('##### IFRAMES #####');
    document.querySelectorAll('iframe').forEach(f => {
        lines.push('iframe src=' + (f.src || '(none)').slice(0, 120) + ' title=' + f.title);
    });
    return lines.join('\\n');
}
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8599", wait_until="networkidle")
        page.wait_for_selector('[class*="st-key-probe_container_a"]', timeout=20000)
        page.wait_for_timeout(3000)

        print("Exceptions on page:", page.locator('[data-testid="stException"]').count())
        print(page.evaluate(JS_WALK))

        # Iframe parent-access test: find component iframe and read its body
        iframe_count = page.locator("iframe").count()
        print(f"\niframe count: {iframe_count}")
        for i in range(iframe_count):
            try:
                body = page.frame_locator("iframe").nth(i).locator("body").inner_text(timeout=5000)
                print(f"iframe[{i}] body: {body[:200]!r}")
            except Exception as e:  # noqa: BLE001
                print(f"iframe[{i}] error: {str(e)[:120]}")

        browser.close()


if __name__ == "__main__":
    main()
