"""
Risk engine V2 — operates on the unified dataset built from official exports.

The legacy modules one level up (`features`, `detectors`, `scoring`, `models`)
are kept unchanged: they run the labelled synthetic benchmark, which is the only
place precision and recall can be measured. This package is what runs on real
MPLADS data, where no fraud labels exist.
"""
from .pipeline import run, export

__all__ = ["run", "export"]
