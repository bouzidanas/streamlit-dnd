"""True E2E test: real browser input against a live, wheel-installed app.

The test intentionally does not import ``streamlit_dnd``. The Streamlit child
process runs from an isolated temporary working directory, so the app imports
the installed wheel rather than the repository checkout.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).parents[1].resolve()
APP = Path(__file__).with_name("e2e_app.py").resolve()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(url: str, process: subprocess.Popen, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Streamlit exited early with status {process.returncode}"
            )
        try:
            with urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Streamlit did not become ready at {url}")


def wait_for_text(page: Page, text: str) -> None:
    page.get_by_text(text, exact=True).wait_for(state="visible", timeout=15_000)


def wait_for_wiring(page: Page, container: str, count: int) -> None:
    page.wait_for_function(
        """({container, count}) =>
            document.querySelectorAll(
                `.st-key-${container} > [data-stdnd-wired='1']`
            ).length === count
        """,
        arg={"container": container, "count": count},
        timeout=15_000,
    )


def drag_to_container(page: Page, source_selector: str, target_selector: str) -> None:
    """Drive native drag-and-drop through Playwright's real mouse backend."""
    source = page.locator(source_selector).first
    target = page.locator(target_selector).first
    source.wait_for(state="visible")
    target.wait_for(state="visible")
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if not source_box or not target_box:
        raise AssertionError("source or target has no rendered bounding box")

    # Start inside the default 12px border handle. Playwright's drag_to uses
    # browser mouse input and waits for the native dragstart signal before
    # completing the gesture; no DragEvent is constructed by the test.
    source.drag_to(
        target,
        source_position={"x": 4, "y": source_box["height"] / 2},
        target_position={
            "x": target_box["width"] / 2,
            "y": target_box["height"] - 8,
        },
        timeout=15_000,
    )


def assert_clean_page(page: Page, console_errors: list[str]) -> None:
    exceptions = page.locator('[data-testid="stException"]')
    if exceptions.count():
        raise AssertionError(exceptions.first.inner_text())
    if console_errors:
        raise AssertionError("browser console errors:\n" + "\n".join(console_errors))


def exercise_browser(playwright, browser_name: str, url: str, artifacts: Path) -> None:
    browser = getattr(playwright, browser_name).launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    console_errors: list[str] = []

    def record_console_error(message) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    page.on("console", record_console_error)
    try:
        page.goto(url, wait_until="networkidle")
        wait_for_text(page, "PACKAGE_VERSION=0.2.0")
        wait_for_wiring(page, "e2e_left", 2)
        wait_for_wiring(page, "frames_left", 2)
        wait_for_wiring(page, "legacy_items", 3)

        package_path = page.get_by_text("PACKAGE_FILE=", exact=False).first.inner_text()
        if str(ROOT / "streamlit_dnd") in package_path:
            raise AssertionError(
                "E2E app imported the checkout instead of the installed wheel: "
                + package_path
            )

        # Safe default: headings are fixed, keyed cards are wired, and an empty
        # container with a heading still shows its hint.
        left = page.locator(".st-key-e2e_left")
        right = page.locator(".st-key-e2e_right")
        wired = left.locator(":scope > [data-stdnd-wired='1']")
        if wired.count() != 2:
            raise AssertionError("expected exactly two keyed cards in left board")
        if wired.first.get_attribute("data-stdnd-index") != "0":
            raise AssertionError("fixed heading shifted the first card index")
        placeholder = right.locator(":scope > .stdnd-placeholder")
        if (
            not placeholder.is_visible()
            or placeholder.inner_text() != "Drop a card here"
        ):
            raise AssertionError("empty target placeholder is not visible")

        # Default border handle, real mouse input, empty destination.
        drag_to_container(
            page,
            ".st-key-e2e_left > [data-stdnd-wired='1']",
            ".st-key-e2e_right",
        )
        wait_for_text(page, "STATE_BOARD_LEFT=Bravo")
        wait_for_text(page, "STATE_BOARD_RIGHT=Alpha")
        wait_for_wiring(page, "e2e_left", 1)
        wait_for_wiring(page, "e2e_right", 1)

        # A second real drag proves wiring survives Streamlit reruns.
        drag_to_container(
            page,
            ".st-key-e2e_left > [data-stdnd-wired='1']",
            ".st-key-e2e_right",
        )
        wait_for_text(page, "STATE_BOARD_LEFT=")
        wait_for_text(page, "STATE_BOARD_RIGHT=Alpha|Bravo")
        wait_for_wiring(page, "e2e_right", 2)

        # Interactive content remains clickable after moves.
        page.get_by_role("button", name="Select Bravo").click()
        wait_for_text(page, "STATE_CLICKED=Bravo")
        wait_for_wiring(page, "frames_left", 2)

        # Dict-of-DataFrames move, using the generalized apply_move.
        drag_to_container(
            page,
            ".st-key-frames_left > [data-stdnd-wired='1']",
            ".st-key-frames_right",
        )
        wait_for_text(page, "STATE_FRAMES_LEFT=df2")
        wait_for_text(page, "STATE_FRAMES_RIGHT=df1")
        wait_for_wiring(page, "legacy_items", 3)

        # Explicit legacy mode still wires unkeyed direct children.
        legacy_items = ".st-key-legacy_items > [data-stdnd-wired='1']"
        if page.locator(legacy_items).count() != 3:
            raise AssertionError("item_mode='all' did not wire unkeyed items")
        drag_to_container(page, legacy_items, ".st-key-legacy_items")
        wait_for_text(page, "STATE_LEGACY=Two|Three|One")

        # A new page creates a new Streamlit session; board state must be
        # restored from the app's durable store.
        page.close()
        page = context.new_page()
        page.on("console", record_console_error)
        page.goto(url, wait_until="networkidle")
        wait_for_text(page, "STATE_BOARD_LEFT=")
        wait_for_text(page, "STATE_BOARD_RIGHT=Alpha|Bravo")
        assert_clean_page(page, console_errors)
        context.tracing.stop()
    except Exception:
        if not page.is_closed():
            page.screenshot(
                path=artifacts / f"{browser_name}-failure.png", full_page=True
            )
        context.tracing.stop(path=artifacts / f"{browser_name}-trace.zip")
        raise
    finally:
        context.close()
        browser.close()


def run(browser_name: str, artifacts: Path) -> None:
    artifacts.mkdir(parents=True, exist_ok=True)
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="streamlit-dnd-e2e-") as temp_dir:
        temp_path = Path(temp_dir)
        server_log_path = temp_path / "streamlit.log"
        environment = os.environ.copy()
        environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        with server_log_path.open("w") as server_log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(APP),
                    "--server.headless=true",
                    f"--server.port={port}",
                    "--server.address=127.0.0.1",
                ],
                cwd=temp_path,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            failed = False
            try:
                wait_for_server(url, process)
                with sync_playwright() as playwright:
                    exercise_browser(playwright, browser_name, url, artifacts)
            except Exception:
                failed = True
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                if failed:
                    server_log.flush()
                    shutil.copy2(
                        server_log_path, artifacts / f"{browser_name}-streamlit.log"
                    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--browser", choices=("chromium", "firefox", "webkit"), default="chromium"
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path(tempfile.gettempdir()) / "streamlit-dnd-e2e-artifacts",
    )
    args = parser.parse_args()
    run(args.browser, args.artifacts.resolve())
    print(f"PASS: packaged real-input E2E ({args.browser})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
