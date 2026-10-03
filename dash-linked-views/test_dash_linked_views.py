"""Headless-browser proof: clicks link views with ZERO server requests; key change = one fetch.
Run: python test_dash_linked_views.py"""
import glob
import json
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PORT = 8543
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
CHROME = (glob.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome") or [None])[0]


def main() -> None:
    import dash_linked_views_lab as lab
    with lab.app.server.app_context():
        b = lab.fetch_bundle("auth"); lab.fetch_bundle("auth")
        assert lab.FETCHES["n"] == 1 and len(b["detail"]) == 9
        assert {t["name"] for t in b["daily_fig"]["data"]} == {"us-east-1", "eu-west-1", "ap-south-1"}
        json.dumps(b)
    print("PASS bundle: one fetch per key, 9 detail rows, one trace per region, Store-safe")

    proc = subprocess.Popen([sys.executable, "-c",
                             f"import dash_linked_views_lab as l; l.app.run(port={PORT})"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            time.sleep(0.5)
            try: OPEN(f"http://127.0.0.1:{PORT}/", timeout=2); break
            except Exception: pass
        with sync_playwright() as p:
            br = p.chromium.launch(headless=True, executable_path=CHROME)
            page = br.new_page()
            server_calls = []
            page.on("request", lambda r: server_calls.append(r.url)
                    if "_dash-update-component" in r.url else None)
            page.goto(f"http://127.0.0.1:{PORT}/")
            page.wait_for_function(
                "document.querySelectorAll('#detail .ag-center-cols-container .ag-row').length === 9",
                timeout=25000)
            print("PASS initial load: detail shows all 9 rows")
            before = len(server_calls)

            page.locator("#regions .ag-row[row-index='0'] [col-id='region']").click()
            page.wait_for_function(
                "document.querySelectorAll('#detail .ag-center-cols-container .ag-row').length === 3",
                timeout=10000)
            visible = page.evaluate(
                "document.querySelector('#daily .js-plotly-plot').data.filter(t => t.visible === true).length")
            status = page.locator("#status").inner_text()
            time.sleep(0.5)
            assert len(server_calls) == before, f"click caused {len(server_calls)-before} server calls"
            assert visible == 1 and status.startswith("filter:"), (visible, status)
            print(f"PASS click: detail 9->3 rows, 1 of 3 traces visible, '{status}', "
                  f"ZERO server requests")

            page.click("#svc"); page.click("[role=option]:has-text('media')")   # dash 4 dropdown = button + portal listbox
            page.wait_for_function(
                "document.querySelector('#fetches').innerText.includes('2')", timeout=10000)
            page.wait_for_function(
                "document.querySelectorAll('#detail .ag-center-cols-container .ag-row').length === 9",
                timeout=10000)
            assert len(server_calls) > before
            print("PASS key change: ONE server fetch, selection reset, detail back to 9 rows")
            br.close()
    finally:
        proc.terminate()
    print("\nALL OK")


if __name__ == "__main__":
    main()
