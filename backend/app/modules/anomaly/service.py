from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.prometheus.client import QUERIES, PrometheusClient
from app.models import Device
from app.modules.anomaly.detectors import (
    FEATURES, Detection, EWMADetector, IsolationForestDetector, ZScoreDetector,
)
from app.modules.anomaly.models import Algorithm, AnomalyResult

STEP = 15
LOOKBACK = timedelta(hours=1)
DEMO_BASELINES = {"traffic_in": 20000.0, "traffic_out": 10000.0, "latency": 0.02, "probe_success": 1.0}


def demo_series(metric: str, points: pd.Series, end: datetime) -> pd.Series:
    history = points if len(points) >= 30 else pd.Series(
        DEMO_BASELINES[metric] * (1 + 0.02 * np.sin(np.arange(40)))
        if metric != "probe_success" else np.ones(40),
        index=pd.date_range(end=end - timedelta(seconds=STEP), periods=40, freq=f"{STEP}s"),
    )
    if metric == "probe_success":
        spike = float(history.mean() < 0.5)
    else:
        maximum = float(history.abs().max())
        spike = 10 * max(maximum, DEMO_BASELINES[metric])
    return pd.concat([history, pd.Series([spike], index=[pd.Timestamp(end)])])


def row(
    device_id: int, metric: str, algorithm: Algorithm, result: Detection,
    window_start: pd.Timestamp, window_end: pd.Timestamp, sample_count: int, synthetic: bool,
) -> dict:
    return {
        "device_id": device_id,
        "metric_name": metric,
        "algorithm": algorithm,
        "observed_value": result.observed_value,
        "baseline_mean": result.baseline_mean,
        "baseline_std": result.baseline_std,
        "anomaly_score": result.anomaly_score,
        "is_anomaly": result.is_anomaly,
        "severity": result.severity,
        "window_start": window_start.to_pydatetime(),
        "window_end": window_end.to_pydatetime(),
        "explanation_json": {
            "synthetic": synthetic, "baseline_samples": sample_count, **result.explanation,
        },
    }


def scan(db: Session, prometheus: PrometheusClient, synthetic: bool) -> dict:
    devices = db.execute(select(Device.id, Device.ip_address, Device.hostname).where(
        Device.monitoring_enabled.is_(True)
    )).all()
    db.rollback()  # Release the read transaction while fetching Prometheus metrics.
    if not devices:
        return {"devices_scanned": 0, "results_saved": 0, "anomalies_detected": 0}

    now = datetime.now(UTC)
    end = datetime.fromtimestamp(int(now.timestamp()) // STEP * STEP, UTC)
    metrics = {
        metric: prometheus.query_range(query, end - LOOKBACK, end, STEP)
        for metric, query in QUERIES.items()
    }
    observation_end = now if synthetic else end
    freshness_limit = end - timedelta(seconds=STEP)
    empty_series = pd.Series(dtype=float)
    rows = []
    for device_id, address, hostname in devices:
        data = {}
        for metric, instances in metrics.items():
            points = instances.get(address, instances.get(hostname, empty_series))
            if synthetic:
                points = demo_series(metric, points, observation_end)
            if points.empty or points.index[-1] < freshness_limit:
                continue
            data[metric] = points
            history, observed = points.iloc[:-1], points.iloc[-1]
            for algorithm, detector in ((Algorithm.zscore, ZScoreDetector()), (Algorithm.ewma, EWMADetector())):
                detection = detector.detect(history, observed)
                if detection is not None:
                    rows.append(row(
                        device_id, metric, algorithm, detection, history.index[0],
                        points.index[-1], len(history), synthetic,
                    ))

        if all(feature in data for feature in FEATURES):
            frame = pd.concat([data[feature].rename(feature) for feature in FEATURES], axis=1).dropna()
            if not frame.empty and frame.index[-1] >= freshness_limit:
                history = frame.iloc[:-1]
                detection = IsolationForestDetector().detect(history, frame.iloc[-1])
                if detection is not None:
                    rows.append(row(
                        device_id, "traffic_latency", Algorithm.isolation_forest, detection,
                        history.index[0], frame.index[-1], len(history), synthetic,
                    ))

    saved = []
    if rows:
        # Keep repeat scans of the same observation idempotent, including concurrent requests.
        statement = insert(AnomalyResult).on_conflict_do_nothing(constraint="uq_anomaly_result_window")
        saved = db.scalars(statement.returning(AnomalyResult.is_anomaly), rows).all()
        db.commit()
    return {
        "devices_scanned": len(devices),
        "results_saved": len(saved),
        "anomalies_detected": sum(result["is_anomaly"] for result in rows),
    }
