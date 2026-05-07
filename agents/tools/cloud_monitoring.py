"""Cloud Monitoring tool wrapper — Google Cloud Monitoring API."""

import os
import time
from typing import Any

from google.cloud import monitoring_v3


PROJECT = os.getenv("GCP_PROJECT", "")


def cloud_monitoring_query(metric_type: str, lookback_seconds: int = 900,
                           project: str = "") -> dict[str, Any]:
    """Query a GCP-native metric.

    metric_type examples:
      - 'kubernetes.io/container/cpu/core_usage_time'
      - 'kubernetes.io/container/memory/used_bytes'
      - 'cloudsql.googleapis.com/database/cpu/utilization'
    """
    proj = project or PROJECT
    if not proj:
        return {"success": False, "error": "GCP_PROJECT env var not set"}
    try:
        client = monitoring_v3.MetricServiceClient()
        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": seconds, "nanos": nanos},
                "start_time": {"seconds": seconds - lookback_seconds, "nanos": nanos},
            }
        )
        results = client.list_time_series(
            request={
                "name": f"projects/{proj}",
                "filter": f'metric.type="{metric_type}"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        series = []
        for ts in results:
            points = [
                {
                    "value": p.value.double_value or p.value.int64_value,
                    "timestamp": p.interval.end_time.seconds,
                }
                for p in ts.points
            ]
            series.append({
                "resource_labels": dict(ts.resource.labels),
                "metric_labels": dict(ts.metric.labels),
                "points": points[:100],
            })
        return {"success": True, "count": len(series), "series": series}
    except Exception as e:
        return {"success": False, "error": str(e)}
