# 📊 Building the real CBD office cohorts (per city) — runbook

> Run this **on your Mac** (normal internet). The sandbox can't fetch the CBD
> register. Output is `data/benchmarks/cbd_office_cohorts.json` — the real
> whole-building office EUI cohorts the demo benchmarks each baseline against.

## What you get

Per city (Sydney · Melbourne · Brisbane · Perth), a **medium** and **large**
office cohort with `n`, min/p25/median/p75/max EUI (kWh/m²·yr), typical NABERS
star, and a `verified` flag. `verified=true` only when the cohort is big enough
(n ≥ 30) **and** its median is a physically plausible office EUI (50–400) — it
fails closed against a units/column bug.

## Step 1 — download the register

Either source works (the script auto-detects the schema):

- **cbd.gov.au BEEC download** — the official "Find a rated building" export
  (filter/export to CSV): <https://www.cbd.gov.au/which-buildings-are-affected/find-rated-building/find-rated-building>
- **data.gov.au CBD/NABERS mirror** — the CC-BY register CSV (CRT_*/B_* columns).

Save it anywhere, e.g. `~/Downloads/cbd_register.csv`.

## Step 2 — build

```bash
cd retrofitgpt
pip install pandas openpyxl
python3 scripts/build_cbd_cohorts.py --input ~/Downloads/cbd_register.csv
# multiple files (e.g. a CSV + an XLSX BEEC export) are merged:
python3 scripts/build_cbd_cohorts.py --input cbd.csv --input beec.xlsx
```

The script enforces three correctness rules: **whole-building only** (≈79% of rows
are base-building and aren't comparable to a whole-building sim), **offices ≥1,000 m²**
(small offices aren't in the data), and **per-city metro postcode bands**:

| City | State | Postcode band (tunable) | NCC zone |
|---|---|---|---|
| Sydney | NSW | 2000–2249 | 5 |
| Melbourne | VIC | 3000–3207 | 6 |
| Brisbane | QLD | 4000–4179 | 2 |
| Perth | WA | 6000–6199 | 5 |

Override one city's band if needed:

```bash
python3 scripts/build_cbd_cohorts.py --input cbd.csv --city perth \
    --postcode-min 6000 --postcode-max 6230
```

## Step 3 — wire the medians into the demo

The frontend shows a benchmark line per selection from `COHORTS` in
`frontend/lib/energy-modeller-catalog.ts`. After a build, copy each **verified**
cohort's `median` and `n` in, keyed `${city}_${building}`:

```ts
export const COHORTS: Partial<Record<string, Cohort>> = {
  // sydney_medium_office is the ONE real, verified cohort today (n=96, median 213).
  sydney_medium_office: { n: 96, medianEui: 213, verified: true },
  // Add the others ONLY from your real script output — do not hand-type:
  //   <city>_<building>: { n: <n>, medianEui: <median>, verified: true },
};
```

Leave a cohort **out** if the script flagged it `verified=false` (too small) — the
UI then honestly shows "builds locally from CBD register" instead of a weak number.
Don't hand-type medians you didn't get from the script.

## Notes

- Large-office cohorts are real but **thinner** (fewer large buildings per city);
  expect smaller `n` than medium, and possibly `verified=false` in Perth/Brisbane.
- Units: NABERS reports annual energy in **MJ**; the script auto-detects and
  divides by 3.6 to get kWh. The `[units]` log line tells you which path ran.
- Provenance is stamped into the JSON (`status: REAL`, `generated`, `provenance`).
