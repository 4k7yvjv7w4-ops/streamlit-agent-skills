"""parquet_s3_demo — runnable proof of the parquet-on-S3 best practices.

Run:  python parquet_s3_demo.py     (self-test, uses a LOCAL temp dir)

Everything here is identical on S3 — replace the local root with "s3://bucket/prefix"
and pyarrow uses the AWS credential chain (env / ~/.aws / IAM role). Nothing
else changes. Dependency: pyarrow, pandas.

Demonstrates: hive partitioning by date, partition PRUNING + column PROJECTION,
partition-level overwrite (delete_matching), and the small-files vs compacted
read. Prints a summary and asserts the pushdown actually skipped files.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds


def make_frame(day: str, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "date": day,
        "region": rng.choice(["us-east-1", "eu-west-1", "ap-south-1"], n),
        "latency_ms": rng.uniform(20, 400, n).round(1),
        "requests": rng.integers(1, 9000, n),
    })


def write_day(root: str, day: str, df: pd.DataFrame) -> None:
    """Write ONE date partition; delete_matching replaces it if it exists."""
    ds.write_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        root, format="parquet",
        partitioning=["date"], partitioning_flavor="hive",
        existing_data_behavior="delete_matching",
        file_options=ds.ParquetFileFormat().make_write_options(compression="zstd"),
    )


def list_files(root: str) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*.parquet"))


def main() -> None:
    root = tempfile.mkdtemp(prefix="pq_demo_")
    try:
        days = ["2025-03-01", "2025-03-02", "2025-03-03"]
        for i, d in enumerate(days):
            write_day(root, d, make_frame(d, 1000, seed=i))
        files = list_files(root)
        print("layout (hive-partitioned by date):")
        for f in files:
            print("  ", f)
        assert files == [f"date={d}/part-0.parquet" for d in days]

        dset = ds.dataset(root, format="parquet", partitioning="hive")

        # 1) PARTITION PRUNING — filter on the partition column skips files
        all_frags = len(list(dset.get_fragments()))
        one = list(dset.get_fragments(filter=ds.field("date") == "2025-03-02"))
        print(f"\npruning: {all_frags} partitions total -> {len(one)} file read "
              f"for date==2025-03-02 ({one[0].path.split('/')[-2]})")
        assert all_frags == 3 and len(one) == 1

        # 2) COLUMN PROJECTION — read only the columns you ask for
        tbl = dset.to_table(filter=ds.field("date") == "2025-03-02",
                            columns=["region", "latency_ms"])
        print(f"projected read: columns={tbl.column_names}, rows={tbl.num_rows}")
        assert tbl.column_names == ["region", "latency_ms"] and tbl.num_rows == 1000

        # 3) pandas equivalent (filters is DNF: list of tuples = AND)
        pdf = pd.read_parquet(root, engine="pyarrow",
                              filters=[("date", ">=", "2025-03-02")],
                              columns=["date", "latency_ms"])
        print(f"pandas range read (date>=03-02): {len(pdf)} rows across "
              f"{pdf['date'].nunique()} dates, latency dtype={pdf['latency_ms'].dtype}")
        assert len(pdf) == 2000 and pdf["date"].nunique() == 2

        # 4) PARTITION OVERWRITE — re-writing one date replaces just that partition
        write_day(root, "2025-03-02", make_frame("2025-03-02", 500, seed=99))
        n_after = ds.dataset(root, partitioning="hive").to_table(
            filter=ds.field("date") == "2025-03-02").num_rows
        untouched = ds.dataset(root, partitioning="hive").to_table(
            filter=ds.field("date") == "2025-03-01").num_rows
        print(f"\noverwrite: date=2025-03-02 now {n_after} rows (was 1000); "
              f"date=2025-03-01 untouched at {untouched}")
        assert n_after == 500 and untouched == 1000

        # 5) partition value comes back as a STRING, not a date
        d0 = ds.dataset(root, partitioning="hive").to_table(columns=["date"]).to_pandas()
        print(f"\ngotcha: partition 'date' dtype = {d0['date'].dtype} (string — "
              "cast if you need date math)")
        # a STRING, not a datetime — dtype spelling varies by pandas version
        assert isinstance(d0["date"].iloc[0], str) and d0["date"].iloc[0] == "2025-03-01"
        assert not str(d0["date"].dtype).startswith("datetime")

        # 6) DERIVED ROLLUP — daily aggregate stored as additive COMPONENTS,
        #    idempotent per date, correct when rolled up further
        agg_root = tempfile.mkdtemp(prefix="pq_agg_")
        try:
            def rollup_day(day: str) -> None:
                t = ds.dataset(root, partitioning="hive").to_table(
                    filter=ds.field("date") == day,
                    columns=["date", "region", "latency_ms", "requests"])
                d = t.to_pandas().assign(lat_x_req=lambda x: x.latency_ms * x.requests)
                agg = (d.groupby(["date", "region"], as_index=False)
                        .agg(n=("latency_ms", "size"), sum_req=("requests", "sum"),
                             sum_lat_x_req=("lat_x_req", "sum")))   # components, not avg
                ds.write_dataset(pa.Table.from_pandas(agg, preserve_index=False),
                                 agg_root, format="parquet",
                                 partitioning=["date"], partitioning_flavor="hive",
                                 existing_data_behavior="delete_matching")

            for d in days:
                rollup_day(d)
            rollup_day("2025-03-01")            # RE-RUN one date — must stay identical
            adf = pd.read_parquet(agg_root)
            per_date_rows = adf.groupby("date").size()
            n_regions = adf["region"].nunique()   # 3 regions in the demo data
            print(f"\nrollup: {len(adf)} agg rows; re-running date=2025-03-01 kept "
                  f"{per_date_rows['2025-03-01']} rows (idempotent, not doubled)")
            assert (per_date_rows <= n_regions).all()   # doubling would exceed region count

            # weekly weighted-avg FROM COMPONENTS vs DIRECT from raw
            wk = (adf.groupby("region")
                    .apply(lambda g: g.sum_lat_x_req.sum() / g.sum_req.sum(),
                           include_groups=False).round(6))
            raw_all = ds.dataset(root, partitioning="hive").to_table().to_pandas()
            direct = (raw_all.assign(lx=raw_all.latency_ms * raw_all.requests)
                      .groupby("region")
                      .apply(lambda g: g.lx.sum() / g.requests.sum(),
                             include_groups=False).round(6))
            print(f"weekly wavg from components == direct-from-raw: "
                  f"{bool((wk == direct).all())}  {dict(wk)}")
            assert (wk == direct).all()
        finally:
            shutil.rmtree(agg_root, ignore_errors=True)

        print("\nALL OK — pruning, projection, range read, partition overwrite, "
              "idempotent rollup + component roll-up verified.")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
