from collections.abc import Iterator
from datetime import datetime
from os import environ

import httpx
import numpy as np
import pandas as pd

QUERIES = {
    "traffic_in": "sum by (instance) (rate(ifHCInOctets[1m]) * 8)",
    "traffic_out": "sum by (instance) (rate(ifHCOutOctets[1m]) * 8)",
    "latency": 'probe_duration_seconds{job="blackbox_icmp"}',
    "probe_success": 'probe_success{job="blackbox_icmp"}',
}


class PrometheusError(RuntimeError):
    pass


class PrometheusClient:
    def __init__(self, client: httpx.Client):
        self.client = client

    def query_range(
        self, query: str, start: datetime, end: datetime, step: int
    ) -> dict[str, pd.Series]:
        try:
            response = self.client.get(
                "/api/v1/query_range",
                params={"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": step},
            )
            response.raise_for_status()
            payload = response.json()
            if payload["status"] != "success" or payload["data"]["resultType"] != "matrix":
                raise PrometheusError("Expected a successful Prometheus matrix response")

            result = {}
            for series in payload["data"]["result"]:
                instance = series["metric"]["instance"]
                points = pd.Series(
                    [float(value) for _, value in series["values"]],
                    index=pd.to_datetime(
                        [timestamp for timestamp, _ in series["values"]], unit="s", utc=True
                    ),
                    dtype=float,
                )
                result[instance] = points[np.isfinite(points)].sort_index()
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise PrometheusError("Unable to read Prometheus range metrics") from exc


    def query_instant(self, query: str, at: datetime) -> list[tuple[dict[str, str], float]]:
        try:
            response = self.client.get("/api/v1/query", params={"query": query, "time": at.timestamp()})
            response.raise_for_status()
            payload = response.json()
            if payload["status"] != "success" or payload["data"]["resultType"] != "vector":
                raise PrometheusError("Expected a successful Prometheus vector response")
            values = [(series["metric"], float(series["value"][1])) for series in payload["data"]["result"]]
            return [(labels, value) for labels, value in values if np.isfinite(value)]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, OverflowError, IndexError) as exc:
            raise PrometheusError("Unable to read Prometheus instant metrics") from exc


def get_prometheus_client() -> Iterator[PrometheusClient]:
    with httpx.Client(
        base_url=environ.get("PROMETHEUS_URL", "http://prometheus:9090"), timeout=10.0
    ) as client:
        yield PrometheusClient(client)
