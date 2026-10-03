"""Headless-browser test: grid renders, JS-function props run, selection reaches Python.
Run: python test_dash_grid.py   (uses the preinstalled Chromium via Playwright)"""
import glob
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PORT = 8541
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
CHROME = (glob.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome") or [None])[0]


def main() -> None:
    import dash_grid_lab as lab
    assert "selected: auth" in lab.picked([lab.DF.iloc[0].to_dict()])
    print("PASS callback direct-call")

    proc = subprocess.Popen([sys.executable, "-c",
                             f"import dash_grid_lab as l; l.app.run(port={PORT})"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            time.sleep(0.5)
            try: OPEN(f"http://127.0.0.1:{PORT}/", timeout=2); break
            except Exception: pass
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, executable_path=CHROME)
            page = b.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/")
            page.wait_for_selector("#grid .ag-center-cols-container .ag-row", timeout=20000)
            rows = page.locator("#grid .ag-center-cols-container .ag-row")
            print("PASS grid renders rows in browser:", rows.count())
            statuses = page.locator("#grid .ag-center-cols-container [col-id='status']").all_inner_texts()
            assert set(statuses) <= {"BREACH", "ok"} and statuses, statuses
            print("PASS custom assets/ function ran per cell:", sorted(set(statuses)))
            fmt = page.locator("#grid .ag-row[row-index='0'] [col-id='requests']").inner_text()
            assert "," in fmt or len(fmt) <= 3, fmt
            print("PASS d3 valueFormatter applied:", fmt)
            page.locator("#grid .ag-row[row-index='0'] [col-id='service']").click()
            page.wait_for_function("document.querySelector('#picked').innerText.startsWith('selected:')",
                                   timeout=10000)
            print("PASS selection -> Python callback:", page.locator("#picked").inner_text())
            b.close()
    finally:
        proc.terminate()
    print("\nALL OK")


if __name__ == "__main__":
    main()
