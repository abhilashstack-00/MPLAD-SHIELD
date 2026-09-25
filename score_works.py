#!/usr/bin/env python3
"""Stage 3: score the unified dataset with the V2 risk engine."""
import argparse, json
from pathlib import Path
import pandas as pd
from mplad_shield.risk.config import RiskConfig
from mplad_shield.risk import pipeline


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interim", default="data/interim")
    p.add_argument("--outdir", default="outputs")
    p.add_argument(
        "--top",
        type=int,
        default=0,
        help="Maximum queue rows to export; 0 exports the full scored register",
    )
    p.add_argument("--detail-scope", default="all", choices=["flagged", "all"],
                   help="Which works get a full detail record exported")
    args = p.parse_args()

    works = pd.read_parquet(Path(args.interim) / "works.parquet")
    allocation_path = Path(args.interim) / "allocation.parquet"
    allocation = pd.read_parquet(allocation_path) if allocation_path.exists() else None
    pipeline_path = Path(args.interim) / "pipeline.parquet"
    rec_pipeline = pd.read_parquet(pipeline_path) if pipeline_path.exists() else None
    report = json.loads((Path(args.interim) / "ingest_report.json").read_text())
    print(f"Loaded {len(works):,} works")

    result = pipeline.run(works, RiskConfig())
    queue_size = args.top
    if queue_size <= 0:
        queue_size = int((result["scored"]["risk_band"] != "Low").sum())
    paths = pipeline.export(
        result,
        report,
        args.outdir,
        top_n=queue_size,
        detail_scope=args.detail_scope,
        allocation=allocation,
        recommendation_pipeline=rec_pipeline,
    )
    s = result["scored"]

    print("\n=== DETECTORS ===")
    for d in result["detectors"]:
        print(f"  {d['detector']:<26} {d['status']:<8} evaluated={d['records_evaluated']:>6,}  flagged={d['records_flagged']:>6,}")
        if d["missing_fields"]:
            print(f"      missing: {', '.join(d['missing_fields'])}")

    print("\n=== RULES ===")
    for r in result["rules"]:
        print(f"  {r['rule_id']:<10} {r['status']:<14} flagged={r['records_flagged']:>5,}  [{r['rule_type']}] {r['name'][:52]}")

    print("\n=== RISK BANDS ===")
    print(s["risk_band"].value_counts().reindex(["High","Medium","Low"]).to_string())
    print("\nscore describe:"); print(s["risk_score"].describe().round(2).to_string())
    print("\nconfidence bands:"); print(s["confidence_band"].value_counts().to_string())
    print("\npeer levels used:"); print(s["peer_level"].value_counts().to_string())

    print("\n=== DECOMPOSITION CHECK ===")
    pts = s[[c for c in s.columns if c.startswith("points_")]].sum(axis=1)
    print(f"  max |sum(points) - risk_score| = {(pts - s['risk_score']).abs().max():.3f}")

    print("\n=== TOP 5 ===")
    for _, r in s.nlargest(5, "risk_score").iterrows():
        print(f"\n  {r['work_id']}  {r['risk_score']:.0f}/100 {r['risk_band']} conf={r['confidence']:.2f} ({r['confidence_band']})")
        print(f"    {str(r['work_description'])[:80]}  |  {r['district']}, {r['state']}")
        for e in r["explanation"]:
            print(f"      - {e['indicator']:<32} {e['points']:>5.1f} pts | {e['detail'][:96]}")
    print(f"\nWrote {paths['scored_json']}")


if __name__ == "__main__":
    main()
