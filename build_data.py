#!/usr/bin/env python3
"""Stage 1-2: ingest the MPLADS exports into a unified work-level dataset."""
import argparse, json
from pathlib import Path
from mplad_shield.ingest import build, IngestConfig


def main():
    p = argparse.ArgumentParser(description="Ingest MPLADS exports.")
    p.add_argument("--data-dir", default="data/raw")
    p.add_argument("--outdir", default="data/interim")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; ages still-open works")
    args = p.parse_args()

    cfg = IngestConfig()
    if args.as_of:
        from datetime import date
        cfg.as_of_date = date.fromisoformat(args.as_of)

    result = build(args.data_dir, cfg)
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)

    result["works"].to_parquet(out / "works.parquet", index=False)
    result["payments"].to_parquet(out / "payments.parquet", index=False)
    result["allocation"].to_parquet(out / "allocation.parquet", index=False)
    if len(result.get("pipeline", [])):
        result["pipeline"].to_parquet(out / "pipeline.parquet", index=False)
    if not result["quarantine"].empty:
        result["quarantine"].to_csv(out / "quarantine.csv", index=False)
    (out / "ingest_report.json").write_text(json.dumps(result["reports"], indent=2, default=str))

    r = result["reports"]
    print("\n=== COVERAGE ===")
    for k, v in r["coverage"].items():
        print(f"  {k:<28} {v:,}")
    if r.get("recommendation_pipeline"):
        print("\n=== RECOMMENDATION PIPELINE ===")
        for k, v in r["recommendation_pipeline"].items():
            print(f"  {k:<32} {v:,.0f}" if isinstance(v, (int, float)) else f"  {k:<32} {v}")

    print("\n=== MATCHING ===")
    for k, v in r["matching"].items():
        print(f"  {k:<40} {v:,}" if isinstance(v, int) else f"  {k:<40} {v}")
    print("\n=== QUARANTINE (%d rows) ===" % r["quarantined_rows"])
    for row in r["quarantine"]:
        print(f"  {row['quarantine_source']:<20} {row['rows']:>4}  {row['quarantine_reason']}")
    print("\n=== DATE CHECKS ===")
    for k, v in r["dates"].items():
        print(f"  {k:<44} {v:,}")
    print("\n=== AMOUNT CHECKS ===")
    for k, v in r["amounts"].items():
        print(f"  {k:<40} {v}")
    print(f"\nWrote {out}/works.parquet and ingest_report.json")


if __name__ == "__main__":
    main()
