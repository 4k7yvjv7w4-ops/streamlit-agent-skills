"""Self-test: cache discipline, cursor concurrency, Store-safety.  Run: python test_dash_data.py"""
import json
import threading

import dash_data_lab as lab


def main() -> None:
    with lab.app.server.app_context():               # flask-caching needs the app context
        lab.fetch_regions("auth"); lab.fetch_regions("auth")
        assert lab.FETCHES["n"] == 1, lab.FETCHES
        lab.fetch_regions("media")
        assert lab.FETCHES["n"] == 2
        lab.fetch_regions("auth")
        assert lab.FETCHES["n"] == 2
        print("PASS memoize: same key cached, new key fetched once, old key still cached")

        rows = lab.fetch_regions("auth")
        json.dumps(rows)                             # must be Store-safe
        assert {"region", "avg_ms", "requests"} <= set(rows[0])
        print("PASS results are JSON-able records (dcc.Store safe)")

        rows_out, msg = lab.load("search")
        assert len(rows_out) == 3 and "fetches" in msg
        assert lab.show(rows_out) == rows_out and lab.show(None) == []
        print("PASS callbacks as plain functions:", msg)

    res = []
    def hit():
        res.append(lab.db().cursor().execute("SELECT count(*) FROM events").fetchone()[0])
    ths = [threading.Thread(target=hit) for _ in range(8)]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert len(set(res)) == 1 and res[0] == 90
    print("PASS 8 concurrent cursors on the singleton connection:", res[0], "rows each")
    print("\nALL OK")


if __name__ == "__main__":
    main()
