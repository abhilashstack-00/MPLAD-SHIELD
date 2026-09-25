#!/usr/bin/env python3
"""Command line entry point for the MPLAD-SHIELD risk engine."""
import argparse, json
from mplad_shield import data_gen, pipeline


BANNER = """
============================================================================
 SYNTHETIC BENCHMARK — this is NOT MPLADS data.

 This entry point generates a labelled synthetic register so precision and
 recall can be measured, which is impossible on real data because no fraud
 labels exist. Output goes to outputs/synthetic_benchmark/ so it cannot
 overwrite the real payload in outputs/.

 To score the real MPLADS exports instead:
     python build_data.py      # ingest the four .xlsx exports
     python score_works.py     # score them with the V2 engine
============================================================================
"""


def main():
    print(BANNER)
    p = argparse.ArgumentParser(description="Score an MPLADS project register.")
    p.add_argument("--csv", help="Path to a real register. Omit to use the synthetic benchmark.")
    p.add_argument("--n", type=int, default=1200, help="Synthetic register size.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--top", type=int, default=50, help="Priority queue length.")
    p.add_argument("--outdir", default="outputs/synthetic_benchmark")
    args = p.parse_args()

    if args.csv:
        register = pipeline.load(args.csv)
        print(f"Loaded {len(register)} works from {args.csv}")
    else:
        register = data_gen.generate(n=args.n, seed=args.seed)
        print(f"Generated {len(register)} synthetic works "
              f"({int(register['is_anomaly'].sum())} labelled irregularities)")

    result = pipeline.run(register, top_n=args.top)
    paths = pipeline.export(result, args.outdir)

    print("\nRisk distribution")
    print(result.bands.to_string(index=False))
    print("\nTop 10 of the priority queue")
    cols = ["project_id", "district", "work_category", "risk_score", "risk_band",
            "confidence", "primary_reason"]
    print(result.queue.head(10)[cols].to_string(index=False))

    if result.metrics.get("available"):
        m = result.metrics
        print(f"\nBenchmark  ROC-AUC {m['roc_auc']}  |  avg precision {m['average_precision']}")
        for k, v in m["at_k"].items():
            print(f"  {k:<8} precision {v['precision']:.3f}  recall {v['recall']:.3f}  "
                  f"({v['caught']}/{v['of_total_irregularities']})")
        print("\n  recall by irregularity type")
        for kind, v in m["by_anomaly_type"].items():
            print(f"    {kind:<22} {v['recall']:.3f}  (mean score {v['mean_risk_score']})")

    print("\nWrote:")
    for name, path in paths.items():
        print(f"  {name:<14} {path}")


if __name__ == "__main__":
    main()
