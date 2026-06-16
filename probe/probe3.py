"""Probe 3: verify iframe parent access + setComponentValue round-trip."""

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        msgs = []
        page.on("console", lambda m: msgs.append(m.text))
        page.goto("http://localhost:8599", wait_until="networkidle")
        page.wait_for_selector('[class*="st-key-iframe_probe_container"]', timeout=20000)
        page.wait_for_timeout(4000)

        print("Exceptions:", page.locator('[data-testid="stException"]').count())
        if page.locator('[data-testid="stException"]').count():
            print(page.locator('[data-testid="stException"]').first.inner_text()[:1500])

        # srcdoc iframe result
        n_iframes = page.locator("iframe").count()
        print(f"iframes: {n_iframes}")
        for i in range(n_iframes):
            fl = page.frame_locator("iframe").nth(i)
            for res_id in ("result1", "result2"):
                try:
                    txt = fl.locator(f"#{res_id}").inner_text(timeout=3000)
                    print(f"iframe[{i}] #{res_id}: {txt}")
                except Exception:  # noqa: BLE001
                    pass

        # Did the custom component value round-trip to Python?
        body_text = page.locator('[data-testid="stMainBlockContainer"]').inner_text()
        print("\n--- Page text ---")
        print(body_text)

        if msgs:
            print("\n--- Console (last 10) ---")
            for m in msgs[-10:]:
                print(m[:200])

        browser.close()


if __name__ == "__main__":
    main()
