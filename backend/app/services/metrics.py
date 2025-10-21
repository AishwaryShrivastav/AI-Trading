"""Prometheus metrics for guardrails and pipeline.

Falls back to no-op metrics if prometheus_client is unavailable.
"""
from typing import Dict, Any

try:
    from prometheus_client import Counter, Histogram  # type: ignore
    _PROM = True
except Exception:  # pragma: no cover - optional dependency
    _PROM = False

    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

    # Shims
    def Counter(name: str, doc: str, labelnames=None):  # type: ignore
        return _NoopMetric()

    def Histogram(name: str, doc: str, buckets=None):  # type: ignore
        return _NoopMetric()


# Guardrail metrics
guardrail_checks_total = Counter(
    "guardrail_checks_total",
    "Total guardrail checks by type and result",
    ["check_type", "result"],
)

guardrail_evaluation_latency_ms = Histogram(
    "guardrail_evaluation_latency_ms",
    "Guardrail evaluation latency in ms",
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2000),
)

blocked_cards_total = Counter(
    "blocked_cards_total",
    "Total count of cards blocked by guardrails",
    ["reason"],
)


def record_guardrail_check(result: Dict[str, Any]) -> None:
    """Record metrics for a single guardrail evaluation."""
    # Individual checks
    for check in (
        "liquidity_check",
        "position_size_check",
        "exposure_check",
        "event_window_check",
        "regime_check",
        "catalyst_freshness_check",
    ):
        if check in result:
            guardrail_checks_total.labels(
                check_type=check.replace("_check", ""),
                result="pass" if result.get(check) else "fail",
            ).inc()

    # Latency
    if "evaluation_duration_ms" in result and result["evaluation_duration_ms"] is not None:
        try:
            guardrail_evaluation_latency_ms.observe(float(result["evaluation_duration_ms"]))
        except Exception:
            pass

    # Blocked reasons
    if result.get("has_critical_failures") and result.get("risk_warnings"):
        # Use first critical warning code as reason
        reason = "UNKNOWN"
        for w in result["risk_warnings"]:
            try:
                if (w.get("type") or "").upper() == "CRITICAL":
                    reason = w.get("code", reason)
                    break
            except Exception:
                continue
        blocked_cards_total.labels(reason=reason).inc()


