"""Self-test for dash_core_lab — callbacks as plain functions + served endpoints.

Run:  python test_dash_core.py
"""
import json
import subprocess
import sys
import time
import urllib.request

import dash_core_lab as lab


def no_proxy_get(url: str) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=5).read()


def main() -> None:
    # 1. callbacks are plain functions — direct-call them
    fig = lab.draw("auth")
    assert fig.data and len(fig.data[0].y) == 30
    print("PASS draw: figure with 30 points")

    verdict, runs = lab.evaluate(1, 150, "auth", [])
    assert "auth" in verdict and len(runs) == 1
    print("PASS evaluate:", verdict)

    verdict2, runs2 = lab.evaluate(2, None, "auth", runs)
    assert verdict2 == "enter a threshold"
    print("PASS evaluate guards None threshold with no_update")

    ul = lab.show_log(["a", "b"])
    assert len(ul.children) == 2
    print("PASS show_log renders items")

    # 2. the app actually serves: layout + dependency map over HTTP
    proc = subprocess.Popen([sys.executable, "-c",
                             "import dash_core_lab as l; l.app.run(port=8517)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(20):
            time.sleep(0.5)
            try:
                no_proxy_get("http://127.0.0.1:8517/")
                break
            except Exception:
                continue
        layout = json.loads(no_proxy_get("http://127.0.0.1:8517/_dash-layout"))
        deps = json.loads(no_proxy_get("http://127.0.0.1:8517/_dash-dependencies"))
        assert any(c.get("props", {}).get("id") == "chart"
                   for c in layout["props"]["children"])
        assert {d["output"] for d in deps} >= {"chart.figure", "clock.children"}
        print("PASS server: layout + dependency map served")
    finally:
        proc.terminate()

    print("\nALL OK")


if __name__ == "__main__":
    main()
