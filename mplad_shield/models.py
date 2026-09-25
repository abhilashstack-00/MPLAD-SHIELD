"""
The unsupervised layer.

The rule engine and the univariate detectors catch works that are extreme on one
dimension. This layer catches works that are unremarkable on every dimension
individually but implausible in combination -- a mildly high cost, a mildly slow
timeline and a mildly odd spend pattern that no single threshold would stop.

Two models are used because they fail differently. Isolation Forest is a global
density model and gives a smooth score for every work. DBSCAN is local: it
identifies clusters of ordinary behaviour and labels whatever refuses to join a
cluster as noise. A work both agree on is a strong candidate.

Neither model sees a fraud label, because none exists. That is the operating
constraint the deck states, and it is what these models are for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from .config import MODEL_PARAMS


class MultivariateDetector:
    """Isolation Forest plus DBSCAN over the scaled feature matrix."""

    def __init__(self, params=MODEL_PARAMS):
        self.params = params
        self.scaler = RobustScaler()
        self.forest = IsolationForest(
            n_estimators=params.isolation_forest_estimators,
            contamination=params.isolation_forest_contamination,
            random_state=params.random_state,
            n_jobs=-1,
        )
        self.feature_names: list[str] = []
        self._scaled: np.ndarray | None = None

    def fit_score(self, matrix: np.ndarray, feature_names: list[str]) -> dict:
        """
        Fit both models and return per-work signals.

        RobustScaler is used rather than StandardScaler for the same reason the
        cost detector uses MAD: the outliers being hunted would otherwise define
        the scale they are measured against.
        """
        self.feature_names = feature_names
        scaled = self.scaler.fit_transform(matrix)
        self._scaled = scaled

        self.forest.fit(scaled)
        # decision_function is positive for inliers, negative for outliers.
        # Flip and min-max it so higher always means more unusual.
        raw = -self.forest.decision_function(scaled)
        spread = raw.max() - raw.min()
        forest_score = (raw - raw.min()) / spread if spread > 0 else np.zeros_like(raw)

        dbscan = DBSCAN(
            eps=self.params.dbscan_eps,
            min_samples=self.params.dbscan_min_samples,
            n_jobs=-1,
        )
        labels = dbscan.fit_predict(scaled)
        is_noise = (labels == -1).astype(float)

        # DBSCAN is a corroborating vote, not a co-equal score: it is binary and
        # sensitive to eps, so it lifts a work rather than deciding it.
        blended = np.clip(forest_score + 0.25 * is_noise, 0.0, 1.0)

        # Keep only the upper tail. Isolation Forest scores every work, so
        # passing the raw value on would hand every record in the register a
        # standing contribution to its risk score. Ranking first also makes the
        # signal robust to the score's absolute scale, which shifts with the
        # composition of each batch.
        ranks = pd.Series(blended).rank(pct=True).to_numpy()
        floor = self.params.multivariate_percentile_floor
        combined = np.clip((ranks - floor) / (1.0 - floor), 0.0, 1.0)

        return {
            "isolation_forest_score": forest_score,
            "dbscan_label": labels,
            "dbscan_is_noise": is_noise,
            "multivariate_score": combined,
        }

    def attribute(self, max_rows: int | None = None) -> pd.DataFrame | None:
        """
        Per-feature SHAP attributions for the Isolation Forest score.

        This is what makes the multivariate component explainable instead of a
        black box: rather than telling a reviewer the model dislikes a work, it
        names which features drove that opinion and by how much.

        Returns None if SHAP is unavailable, so the pipeline degrades to the
        transparent weighted breakdown rather than failing.
        """
        if self._scaled is None:
            return None
        try:
            import shap
        except ImportError:
            return None

        rows = self._scaled if max_rows is None else self._scaled[:max_rows]
        try:
            explainer = shap.TreeExplainer(self.forest)
            values = np.asarray(explainer.shap_values(rows, check_additivity=False))
        except Exception:
            # SHAP's tree support for Isolation Forest is version-sensitive;
            # a failure here must not take the whole scoring run down.
            return None

        if values.ndim == 3:
            values = values[..., 0]
        # Sign convention follows decision_function, where lower means more
        # anomalous. Negate so a positive attribution pushes toward "unusual".
        return pd.DataFrame(-values, columns=self.feature_names)
