"""Peer benchmarking math (Playbook P6.1) — pure functions.

Percentile method (documented, small-sample honest): the percentile of the
observed set — rank of the target among the n observed values,
pct = (# strictly below) / (n - 1), n = target + peers. With n = 4 the
target can land on 0, 33, 67, or 100 — pretending more precision would be
dishonest.

Directions: for most metrics higher is better; debt_to_equity is inverted.
"""

import statistics

COMPARISON_METRICS: list[tuple[str, str, str]] = [
    # (metric_key, label, direction) direction: "higher" | "lower"
    ("revenue_growth", "Revenue growth", "higher"),
    ("ebitda_margin", "EBITDA margin", "higher"),
    ("roe", "ROE", "higher"),
    ("debt_to_equity", "Debt / equity", "lower"),
    ("fcf_margin", "FCF margin", "higher"),
    ("interest_cover", "Interest cover", "higher"),
    ("roic", "ROIC", "higher"),
]

RADAR_AXES = ["revenue_growth", "ebitda_margin", "roe", "debt_to_equity",
              "fcf_margin", "interest_cover"]


def build_comparison(target_metrics: dict[str, float | None],
                     peers: list[dict[str, dict[str, float | None]]]) -> dict:
    """metric x company matrix + percentiles + best/worst flags."""
    rows: list[dict] = []
    for key, label, direction in COMPARISON_METRICS:
        target_value = target_metrics.get(key)
        peer_values = [(p["name"], p.get("metrics", {}).get(key)) for p in peers]
        observed = [v for _, v in peer_values if v is not None]
        if target_value is not None:
            observed.append(target_value)

        below = sum(1 for v in observed if v < (target_value or 0))
        percentile = (below / (len(observed) - 1) * 100) if (
            target_value is not None and len(observed) > 1) else None

        best = worst = None
        if observed:
            best = max(observed) if direction == "higher" else min(observed)
            worst = min(observed) if direction == "higher" else max(observed)

        rows.append({
            "metric": key, "label": label, "direction": direction,
            "target": target_value,
            "peers": {name: value for name, value in peer_values},
            "median": statistics.median(observed) if observed else None,
            "p25": _percentile_sorted(sorted(observed), 0.25) if observed else None,
            "p75": _percentile_sorted(sorted(observed), 0.75) if observed else None,
            "target_percentile": percentile,
            "best": best, "worst": worst,
            "target_is_best": target_value is not None and target_value == best,
            "target_is_worst": target_value is not None and target_value == worst,
        })
    return {"metrics": rows, "n_observed": len(peers) + 1,
            "percentile_method": "rank / (n-1) of the observed set; "
                                 "documented for small samples"}


def _percentile_sorted(sorted_values: list[float], q: float) -> float:
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = q * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def radar_payload(target_metrics: dict[str, float | None],
                  peers: list[dict[str, dict[str, float | None]]]) -> dict:
    """6 axes normalized 0-1 against the observed min-max per axis."""
    axes = []
    for key in RADAR_AXES:
        values = [p.get("metrics", {}).get(key) for p in peers
                  if p.get("metrics", {}).get(key) is not None]
        if target_metrics.get(key) is not None:
            values.append(target_metrics[key])
        values = [v for v in values if v is not None]  # type: ignore[misc]
        if not values:
            continue
        lo, hi = min(values), max(values)  # type: ignore[type-var]
        span = (hi - lo) or 1.0
        norm = lambda v: (v - lo) / span  # noqa: E731
        inverted = key == "debt_to_equity"
        axes.append({
            "axis": key,
            "target": 1 - norm(target_metrics[key]) if inverted and target_metrics.get(key) is not None
            else (norm(target_metrics[key]) if target_metrics.get(key) is not None else None),
            "peer_median": 1 - norm(statistics.median(values)) if inverted
            else norm(statistics.median(values)),
        })
    return {"axes": axes}


def implied_valuation_range(target_ebitda: float,
                            peer_multiples: list[float]) -> dict:
    """Apply peer EV/EBITDA multiples (min/median/max) to target EBITDA."""
    if not peer_multiples or target_ebitda <= 0:
        return {}
    return {
        "min_multiple": min(peer_multiples),
        "median_multiple": statistics.median(peer_multiples),
        "max_multiple": max(peer_multiples),
        "ev_min": min(peer_multiples) * target_ebitda,
        "ev_median": statistics.median(peer_multiples) * target_ebitda,
        "ev_max": max(peer_multiples) * target_ebitda,
        "method": "peer EV/EBITDA applied to latest target EBITDA",
    }
