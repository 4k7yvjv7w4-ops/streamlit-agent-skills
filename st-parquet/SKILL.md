---
name: st-parquet
description: Best practices for storing and reading parquet datasets on S3 — hive partitioning (date-partitioned vs aggregated tables), partition pruning + column projection (predicate pushdown), S3 credentials, correct writes/overwrites, the small-files problem, and caching reads in Streamlit. Use when reading/writing parquet in S3 (or any object store), designing a dataset layout, or a read is slow because it downloads everything.
---

# parquet + S3 — read only what you need, store it so you can

The file/object-store companion to [st-connection] (which covers SQL/warehouse
access): how to load a Streamlit app's data from parquet on S3 efficiently.
Parquet is **columnar + row-grouped + partitionable**, so a good layout lets you
read a slice of a huge dataset in milliseconds. The #1 mistake is
`pd.read_parquet(whole_dataset)` then filtering in pandas — that downloads
everything. Use the **pyarrow dataset API with pushdown**. Runnable proof:
`parquet_s3_demo.py` (self-test builds a partitioned dataset, proves pruning).
Verified on **pyarrow 24 / pandas 3**.

## Two dataset shapes → two layouts

| Your data | Layout | Why |
|---|---|---|
| **Per-date, granular** (append daily) | **hive-partition by date**: `s3://bkt/events/date=2025-03-04/part-*.parquet` | reading a date range skips every other partition (pruning) |
| **Aggregated / rollups** (small) | **one file** (or a few), unpartitioned | partitioning tiny data just adds S3 LIST overhead for no gain |

Rule: partition by the column you FILTER on (date), never by a high-cardinality
column (session_id → millions of tiny files → disaster). One coarse extra
dimension (region) is fine; stop there.

## Read efficiently — pushdown is the whole game

```python
import pyarrow.dataset as ds
dset = ds.dataset("s3://bkt/events", format="parquet", partitioning="hive")
tbl = dset.to_table(
    filter=(ds.field("date") >= "2025-03-01") & (ds.field("region") == "us-east-1"),
    columns=["date", "region", "latency_ms"],     # only these columns are read
)
df = tbl.to_pandas()
```

- **Partition pruning** — a `filter` on the partition column skips whole files
  (verified: 3 partitions → 1 file read). **Column projection** — `columns=`
  reads only those columns off disk (parquet is columnar). **Row-group
  pushdown** — a filter on a *non*-partition column skips row groups by their
  min/max stats. Combine all three.
- pandas equivalent: `pd.read_parquet("s3://bkt/events",
  filters=[("date", ">=", "2025-03-01")], columns=[...])`. `filters` is DNF —
  a list of tuples is AND; a list *of lists* of tuples is OR.
- **Never** `to_pandas()` the whole thing to filter — filter in the read.

## S3 access & credentials

- **`s3://` paths work directly** — pyarrow/pandas use the standard AWS
  credential chain (env vars → `~/.aws/credentials`/profile → **IAM role** on the
  compute). Never hardcode keys; an instance/task IAM role is best.
- Internal / MinIO / non-AWS: `pyarrow.fs.S3FileSystem(endpoint_override=...,
  region=...)`, pass `filesystem=` to `ds.dataset(...)`; pandas takes
  `storage_options={...}`.
- Region matters — a wrong/missing region makes every request cross-region slow.

## Writing & overwriting correctly

```python
import pyarrow as pa, pyarrow.dataset as ds
ds.write_dataset(
    pa.Table.from_pandas(df, preserve_index=False),   # preserve dtypes; drop the index
    "s3://bkt/events", format="parquet",
    partitioning=["date"], partitioning_flavor="hive",
    existing_data_behavior="delete_matching",         # OVERWRITE the dates present in df
    max_rows_per_file=2_000_000,                      # cap file size; avoid tiny files
    file_options=ds.ParquetFileFormat().make_write_options(compression="zstd"),
)
```

- **`existing_data_behavior`**: `"error"` (default) · `"overwrite_or_ignore"` ·
  **`"delete_matching"`** — re-run one date and it replaces that partition
  cleanly. Object stores have **no atomic rename**, so partition-level
  delete-and-rewrite is the safe unit; write a whole `date=X` at once.
- **Compression**: `snappy` (default, fast, good for hot data) vs `zstd`
  (~30% smaller, great for cold/archive). Pick per dataset.
- **Preserve dtypes**: write from a pyarrow `Table` (or `preserve_index=False`);
  parquet round-trips dtypes/timestamps/categoricals — CSV does not.

## Derived tables & rollups (raw → aggregate) — best practice

Your aggregates should be **materialized views of the per-date raw data**, not
hand-maintained tables that can drift.

- **Raw is the source of truth; the aggregate is recomputable.** Keep them as
  SEPARATE datasets. You must be able to drop the aggregate and rebuild it from
  raw at any time — that is your recovery path AND your correctness guarantee.
- **Idempotent, partition-scoped recompute.** The rollup job processes ONE date
  and overwrites that date's aggregate partition (`delete_matching`). Re-running
  a date is safe (no double-count), so a late correction to `date=X` is just
  "re-run X". **Never APPEND to an aggregate** — append isn't idempotent.
- **Incremental, not full, every run** — process only new/changed dates (track a
  watermark or diff partition lists); keep a full rebuild possible for recovery.
- **Store COMPONENTS for non-additive metrics** (the correctness trap):
  - additive (`sum`, `count`) roll up directly.
  - a **weighted average** is stored as its two sums `Σ(value·weight)` and
    `Σweight`, NOT as the daily average — then weekly/monthly = `Σ/Σ` recomputed
    at each level (verified: equals direct-from-raw; averaging daily averages
    does NOT). Same idea for distinct-count (HLL sketches) and percentiles
    (t-digest, or keep raw for the tail).

```python
# daily rollup: read ONE date with pushdown, write additive components
t = ds.dataset("s3://bkt/raw", partitioning="hive").to_table(
    filter=ds.field("date") == day, columns=["date","region","latency_ms","requests"])
d = t.to_pandas().assign(lat_x_req=lambda x: x.latency_ms * x.requests)
agg = (d.groupby(["date","region"], as_index=False)
        .agg(n=("latency_ms","size"), sum_req=("requests","sum"),
             sum_lat_x_req=("lat_x_req","sum")))          # components, NOT the avg
ds.write_dataset(pa.Table.from_pandas(agg, preserve_index=False),
    "s3://bkt/agg", partitioning=["date"], partitioning_flavor="hive",
    existing_data_behavior="delete_matching")             # idempotent per date
# read time, at ANY roll-up level:  weighted_avg = sum_lat_x_req / sum_req
```

- **When to graduate to a table format:** raw parquet + hive partitions +
  `delete_matching` is great for a SINGLE-writer batch rollup. Move to **Apache
  Iceberg / Delta Lake** only when you need concurrent writers, upserts/MERGE,
  snapshot isolation, or schema-change safety — don't adopt them prematurely.

## The small-files problem (the usual S3 pain)

Many tiny parquet files (e.g. one per intraday append) → S3 **LIST + open**
overhead dominates and reads crawl. Fix: **one write per partition** (buffer the
day, write `date=X` once), or run a periodic **compaction** that rewrites a
partition's small files into one 128 MB–1 GB file. Target file size, not row
count.

## Caching reads in Streamlit

Need SQL (joins/aggregations) over the lake inside the app instead of
pandas? → [st-duckdb].

```python
@st.cache_data(ttl="30s")                 # today's partition: short ttl
def load_day(day): return pd.read_parquet(f"s3://bkt/events", filters=[("date","==",day)])

@st.cache_data                            # PAST dates are immutable: cache forever
def load_closed_day(day): return pd.read_parquet(...)   # no ttl
```
Past dates never change → cache with no ttl, keyed by date; only the live
partition needs a ttl. See [st-connection] for the caching rules.

## Gotchas (verified)

- **Partition values read back as STRINGS** (`date="2025-03-01"`, not a date) —
  cast if you need date arithmetic.
- **Schema evolution**: a newer file adds a column → the dataset reads it as
  null in older files (fine). A *type change* (int→float, timestamp **ns vs
  us**) breaks the unified read — pin an explicit `schema=` or cast on write.
- **Over-partitioning** = the killer: partition only by low-cardinality filter
  columns. `date` (+ maybe `region`), never `session_id`/`user_id`.
- **Slow partition discovery** with thousands of partitions → write a
  `_metadata` file (`pq.write_metadata`) or keep a manifest; don't LIST the
  whole prefix every read.
- `preserve_index=False` on write, or a `__index_level_0__` column appears.

## When NOT to partition

Small aggregated/rollup tables → a single file. Partitioning adds LIST overhead
and metadata for no pruning benefit when the table is already small.
