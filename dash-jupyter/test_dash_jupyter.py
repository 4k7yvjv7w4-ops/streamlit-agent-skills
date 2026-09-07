"""Self-test for the skeleton — proves the two-sided prefix wiring.

Run:  python test_dash_jupyter.py
Simulates jupyter-server-proxy: browser keeps the prefix, server sees it stripped.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def main() -> None:
    env = dict(os.environ, JUPYTERHUB_SERVICE_PREFIX="/user/alice/")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(HERE, "skeleton"),
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(20):
            time.sleep(0.5)
            try:
                OPEN("http://127.0.0.1:8519/", timeout=2)
                break
            except Exception:
                continue

        idx = OPEN("http://127.0.0.1:8519/").read().decode()
        assets = re.findall(r'src="(/[^"]*?)/_dash-component-suites', idx)
        assert assets and assets[0] == "/user/alice/proxy/8519", assets
        print("PASS browser side: assets prefixed ->", assets[0])

        deps = json.loads(OPEN("http://127.0.0.1:8519/_dash-dependencies").read())
        assert any(d["output"] == "echo.children" for d in deps)
        print("PASS server side: routes at stripped root")

        layout = json.dumps(json.loads(OPEN("http://127.0.0.1:8519/_dash-layout").read()))
        hrefs = re.findall(r'"href": "([^"]*)"', layout)
        assert "/user/alice/proxy/8519/monitor" in hrefs, hrefs
        print("PASS pages: Link hrefs auto-prefixed ->", hrefs)

        body = json.dumps({"output": "echo.children",
                           "outputs": {"id": "echo", "property": "children"},
                           "inputs": [{"id": "thr", "property": "value", "value": "200"}],
                           "changedPropIds": ["thr.value"]}).encode()
        req = urllib.request.Request("http://127.0.0.1:8519/_dash-update-component",
                                     data=body, headers={"Content-Type": "application/json"})
        resp = json.loads(OPEN(req).read())
        assert resp["response"]["echo"]["children"] == "threshold=200"
        print("PASS callback round-trip at stripped route")
    finally:
        proc.terminate()

    print("\nALL OK")


if __name__ == "__main__":
    main()
