"""Prometheus metrics endpoint."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

_counters: dict[str, float] = defaultdict(float)
_histograms: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def inc(name: str, value: float = 1.0, labels: dict | None = None) -> None:
    key = _label_key(name, labels)
    with _lock:
        _counters[key] += value


def observe(name: str, value: float, labels: dict | None = None) -> None:
    key = _label_key(name, labels)
    with _lock:
        _histograms[key].append(value)
        if len(_histograms[key]) > 1000:
            _histograms[key] = _histograms[key][-500:]


def _label_key(name: str, labels: dict | None) -> str:
    if not labels:
        return name
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def export_prometheus() -> str:
    lines = []
    with _lock:
        for k, v in _counters.items():
            lines.append(f"ifs_{k} {v}")
        for k, vals in _histograms.items():
            if vals:
                avg = sum(vals) / len(vals)
                lines.append(f"ifs_{k}_avg {avg:.4f}")
                lines.append(f"ifs_{k}_count {len(vals)}")
    return "\n".join(lines) + "\n"
