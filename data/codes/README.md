# 📜 data/codes — download these yourself (free, but copyrighted)

This folder is **gitignored**. Code documents are copyrighted and must never be
committed to the repo. Download them locally, then run `python -m rag.ingestion`
to build the RAG index.

| Document | Where to get it (free) |
|----------|------------------------|
| NCC 2022 Volume One (Section J — Energy Efficiency) | https://ncc.abcb.gov.au (free account required) |
| NABERS Energy guides & rules | https://www.nabers.gov.au |

Not needed:
- **ASHRAE Guideline 14** — its calibration thresholds (NMBE ≤10%, CV-RMSE ≤30%,
  monthly) are public knowledge and hardcoded in `verification/ashrae_checks.py`
  with citation. Do not purchase or commit the PDF.
