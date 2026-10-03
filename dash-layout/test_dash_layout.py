"""Headless-browser test: vendored CSS applied, modal/offcanvas/tabs callbacks work.
Run: python test_dash_layout.py"""
import glob
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PORT = 8542
HERE = os.path.dirname(os.path.abspath(__file__))
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
CHROME = (glob.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome") or [None])[0]


def main() -> None:
    sys.path.insert(0, os.path.join(HERE, "skeleton"))
    import app as lab
    assert lab.toggle_modal(1, None, False) is True and lab.tab("t-table").startswith("a grid")
    print("PASS callbacks direct-call")

    proc = subprocess.Popen([sys.executable, "-c", f"import app; app.app.run(port={PORT})"],
                            cwd=os.path.join(HERE, "skeleton"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            time.sleep(0.5)
            try: OPEN(f"http://127.0.0.1:{PORT}/", timeout=2); break
            except Exception: pass
        idx = OPEN(f"http://127.0.0.1:{PORT}/").read().decode()
        assert "assets/bootstrap.min.css" in idx and "cdn.jsdelivr" not in idx
        print("PASS index links the VENDORED css, no CDN")
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, executable_path=CHROME)
            page = b.new_page(); page.goto(f"http://127.0.0.1:{PORT}/")
            page.wait_for_selector("#summary", timeout=15000)
            bg = page.evaluate("getComputedStyle(document.querySelector('.navbar')).backgroundColor")
            assert bg not in ("rgba(0, 0, 0, 0)", "transparent"), bg
            print("PASS bootstrap CSS actually applied (navbar bg):", bg)
            page.click("#open-modal"); page.wait_for_selector(".modal.show", timeout=5000)
            page.click("#close-modal"); page.wait_for_selector(".modal.show", state="detached", timeout=5000)
            print("PASS modal opens and closes via callback")
            page.click("#open-sidebar"); page.wait_for_selector(".offcanvas.show", timeout=5000)
            page.click("#open-sidebar", force=True)
            page.wait_for_selector(".offcanvas.show", state="detached", timeout=5000)
            print("PASS offcanvas sidebar opens and closes")
            page.click(".nav-link:has-text('table')"); page.wait_for_function(
                "document.querySelector('#tab-body').innerText.includes('grid')", timeout=5000)
            print("PASS tabs render active tab only")
            b.close()
    finally:
        proc.terminate()
    print("\nALL OK")


if __name__ == "__main__":
    main()
