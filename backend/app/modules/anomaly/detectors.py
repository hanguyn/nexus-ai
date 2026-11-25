from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

FEATURES = ("traffic_in", "traffic_out", "latency")
MIN_HISTORY = 5


@dataclass(frozen=True)
class Detection:
    observed_value: float
    baseline_mean: float
    baseline_std: float
    anomaly_score: float
    is_anomaly: bool
    severity: str
    explanation: dict = field(default_factory=dict)


def statistical_score(observed: float, mean: float, std: float, threshold: float) -> Detection:
    # Bound the denominator so a flat baseline yields a finite, meaningful deviation.
    score = abs(observed - mean) / max(std, abs(mean) * 1e-6, 1e-9)
    severity = "high" if score >= 6 else "medium" if score >= threshold else "low"
    return Detection(observed, mean, std, score, score >= threshold, severity, {"threshold": threshold})


class ZScoreDetector:
    def detect(self, history: pd.Series, observed: float) -> Detection | None:
        if len(history) < MIN_HISTORY:
            return None
        return statistical_score(float(observed), float(history.mean()), float(history.std(ddof=0)), 3.0)


class EWMADetector:
    def detect(self, history: pd.Series, observed: float) -> Detection | None:
        if len(history) < MIN_HISTORY:
            return None
        weights = history.ewm(span=12, adjust=False)
        return statistical_score(
            float(observed), float(weights.mean().iloc[-1]), float(weights.std(bias=True).iloc[-1]), 3.0
        )


class IsolationForestDetector:
    def detect(self, history: pd.DataFrame, observed: pd.Series) -> Detection | None:
        if len(history) < MIN_HISTORY:
            return None
        features = {key: float(observed[key]) for key in FEATURES}
        if len(history) < 30:
            feature_scores = {
                key: ZScoreDetector().detect(history[key], value) for key, value in features.items()
            }
            key, detection = max(feature_scores.items(), key=lambda item: item[1].anomaly_score)
            return Detection(
                detection.observed_value, detection.baseline_mean, detection.baseline_std,
                detection.anomaly_score, detection.is_anomaly, detection.severity,
                {"fallback": "zscore", "feature": key, "features": features, **detection.explanation},
            )

        model = IsolationForest(contamination="auto", random_state=42)
        training = history[list(FEATURES)].to_numpy()
        model.fit(training)
        sample = np.array([list(features.values())])
        reference_scores = -model.decision_function(training)
        score = float(-model.decision_function(sample)[0])
        severity = "high" if score >= 0.15 else "medium" if score > 0 else "low"
        return Detection(
            score, float(reference_scores.mean()), float(reference_scores.std()), max(0.0, score),
            score > 0, severity, {"features": features, "observed_unit": "isolation_score"},
        )
