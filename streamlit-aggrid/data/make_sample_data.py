"""Generate SYNTHETIC sample data for aggrid_lab.py — service-latency telemetry.

Nothing here is real: invented service/region names, seeded random-walk
latencies. Two schema-stable parquets the lab reads:

  latency.parquet   service x percentile x date   (p95 movers, curves, history)
  regions.parquet   region  x percentile x date   (region x percentile matrix)

Regenerate:  python make_sample_data.py   (writes both parquets next to itself)
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(42)
OUT = Path(__file__).resolve().parent
dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=40)

# percentile -> multiple of the p95 anchor (latency rises with the percentile)
PCTLS = [(50.0, 0.55), (75.0, 0.72), (90.0, 0.88), (95.0, 1.0), (99.0, 1.35)]

# ------------------------------------------------------- latency.parquet --
SERVICES = {
    "auth-api": "Platform", "session-svc": "Platform", "config-svc": "Platform",
    "gateway": "Platform", "rate-limiter": "Platform",
    "checkout": "Payments", "payments-gw": "Payments", "billing": "Payments",
    "invoicing": "Payments", "fraud-check": "Payments",
    "search-api": "Search", "indexer": "Search", "ranking-svc": "Search",
    "autocomplete": "Search",
    "media-cdn": "Media", "transcoder": "Media", "thumbnailer": "Media",
    "upload-svc": "Media",
    "cart-svc": "Commerce", "catalog-api": "Commerce", "pricing-svc": "Commerce",
    "inventory": "Commerce", "recommendations": "Commerce",
    "notify-svc": "Growth", "email-worker": "Growth", "push-gateway": "Growth",
    "analytics-ingest": "Growth", "ab-testing": "Growth",
}

rows = []
for svc, team in SERVICES.items():
    base = float(rng.lognormal(np.log(210), 0.6))          # p95 anchor, ~90-600 ms
    walk = np.cumsum(rng.normal(0, base * 0.012, len(dates)))
    for pct, slope in PCTLS:
        seen = rng.random(len(dates)) < (0.9 if pct == 95.0 else 0.4)
        for d, w, hit in zip(dates, walk, seen):
            if not hit:
                continue
            lat = max((base + w) * slope + rng.normal(0, base * 0.02), 5.0)
            rum = rng.random() < 0.6                        # else synthetic-probe only
            n = int(rng.integers(1, 12))
            rows.append({
                "date": d, "service": svc, "team": team, "percentile": pct,
                "rum_ms_median": round(lat, 1) if rum else np.nan,
                "probe_ms_median": np.nan if rum else round(lat * rng.uniform(0.95, 1.05), 1),
                "n": n, "requests_sum": round(float(rng.lognormal(16.5, 0.8)) * n, -4),
                "asset": "latency",
            })
latency = pd.DataFrame(rows)
latency["date"] = latency["date"].astype("datetime64[us]")
latency.to_parquet(OUT / "latency.parquet", index=False)

# ------------------------------------------------------- regions.parquet --
# p95 latency anchor per region, in SECONDS (the lab multiplies by 1000 -> ms)
REGIONS = {
    "us-east-1": 0.14, "us-west-2": 0.16, "eu-west-1": 0.15, "eu-central-1": 0.15,
    "ap-south-1": 0.28, "ap-northeast-1": 0.24, "sa-east-1": 0.30, "af-south-1": 0.34,
}

rows = []
for reg, base in REGIONS.items():
    drift = np.cumsum(rng.normal(0, base * 0.02, len(dates)))
    for pct, slope in PCTLS:
        seen = rng.random(len(dates)) < 0.9
        for d, dr, hit in zip(dates, drift, seen):
            if not hit:
                continue
            sec = max(base * slope + dr + rng.normal(0, base * 0.03), 0.005)
            rows.append({
                "date": d, "check_type": "http", "region": reg, "percentile": pct,
                "level_median": round(sec, 4),             # seconds
                "n": int(rng.integers(2, 60)),
                "requests_sum": round(float(rng.lognormal(19, 1)), -5),
                "asset": "regions",
            })
    # a few tcp-probe rows so the http filter has something to exclude
    for d in dates[rng.random(len(dates)) < 0.3]:
        rows.append({
            "date": d, "check_type": "tcp", "region": reg, "percentile": 95.0,
            "level_median": round(base * 0.4, 4), "n": int(rng.integers(1, 8)),
            "requests_sum": round(float(rng.lognormal(18, 1)), -5), "asset": "regions",
        })
regions = pd.DataFrame(rows)
regions["date"] = regions["date"].astype("datetime64[us]")
regions.to_parquet(OUT / "regions.parquet", index=False)

print(f"latency: {latency.shape}, regions: {regions.shape} -> {OUT}")
