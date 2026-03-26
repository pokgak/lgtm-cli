"""Terminal chart rendering for Prometheus range query results."""

from __future__ import annotations

import math
import re
from datetime import datetime

import plotext as plt


def render_chart(
    data: dict,
    chart_type: str = "timeseries",
    title: str | None = None,
    width: int | None = None,
    height: int = 20,
) -> None:
    """Render a Prometheus range query result as a terminal chart."""
    series = _parse_prom_response(data)
    if not series:
        plt.clear_figure()
        plt.title("No data")
        plt.show()
        return

    w = width or plt.terminal_width()
    h = height

    if chart_type == "bar":
        _render_bar(series, title, w, h)
    elif chart_type == "heatmap":
        _render_heatmap(series, title, w, h)
    else:
        _render_timeseries(series, title, w, h)


# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------

def _render_timeseries(series: list[dict], title: str | None, width: int, height: int) -> None:
    plt.clear_figure()
    plt.plot_size(width, height)
    plt.theme("dark")
    if title:
        plt.title(title)

    plt.date_form("H:M")
    labels = _simplify_labels([s["label"] for s in series])

    for s, label in zip(series, labels):
        dates = [datetime.fromtimestamp(t).strftime("%H:%M") for t in s["timestamps"]]
        plt.plot(dates, s["values"], label=label)

    # Custom y-axis ticks with nice formatting
    all_vals = [v for s in series for v in s["values"]]
    if all_vals:
        mn, mx = min(all_vals), max(all_vals)
        ticks = _nice_ticks(mn, mx, max_ticks=8)
        plt.yticks(ticks, [_fmt(t) for t in ticks])

    plt.xlabel("Time")
    plt.show()

    # Stats table
    _print_stats_table(series, labels)


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------

def _render_bar(series: list[dict], title: str | None, width: int, height: int) -> None:
    bars = sorted(
        [(s["label"], s["values"][-1]) for s in series],
        key=lambda x: x[1],
        reverse=True,
    )[:20]

    labels = _simplify_labels([b[0] for b in bars])
    values = [b[1] for b in bars]
    max_val = max(values) if values else 1

    label_width = min(max(len(l) for l in labels), 30)
    val_width = max(len(_fmt(v)) for v in values)
    bar_area = max(width - label_width - val_width - 4, 10)

    if title:
        print(f"\033[1m{title}\033[0m")
        print()

    colors = ["\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
              "\033[31m", "\033[92m", "\033[93m", "\033[94m", "\033[95m"]
    reset = "\033[0m"

    for i, (label, value) in enumerate(zip(labels, values)):
        short = label[:label_width - 3] + "..." if len(label) > label_width else label.ljust(label_width)
        bar_len = round((value / max_val) * bar_area) if max_val > 0 else 0
        empty = bar_area - bar_len
        color = colors[i % len(colors)]
        val_str = _fmt(value).rjust(val_width)
        print(f"{short} {color}{'█' * bar_len}{'░' * empty}{reset} {val_str}")

    if len(series) > 20:
        print(f"\n\033[2mShowing top 20 of {len(series)} series\033[0m")


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def _render_heatmap(series: list[dict], title: str | None, width: int, height: int) -> None:
    sorted_series = sorted(series, key=lambda s: _extract_le(s["label"]))

    # Compute deltas for cumulative histogram buckets
    is_cumulative = _detect_cumulative(sorted_series)
    if is_cumulative:
        delta_values = []
        for i, s in enumerate(sorted_series):
            if i == 0:
                delta_values.append(s["values"])
            else:
                delta_values.append([
                    max(0, v - sorted_series[i - 1]["values"][j])
                    for j, v in enumerate(s["values"])
                ])
    else:
        delta_values = [s["values"] for s in sorted_series]

    bucket_labels = [_extract_bucket_label(s["label"]) for s in sorted_series]
    timestamps = sorted_series[0]["timestamps"]

    # Build matrix (rows = buckets, cols = time)
    matrix = delta_values

    plt.clear_figure()
    plt.plot_size(width, height)
    plt.theme("dark")
    if title:
        plt.title(title)

    plt.matrix_plot(matrix)
    plt.yticks(list(range(len(bucket_labels))), bucket_labels)

    # Time axis ticks
    n = len(timestamps)
    tick_count = min(5, n)
    if tick_count > 1:
        indices = [int(i * (n - 1) / (tick_count - 1)) for i in range(tick_count)]
        time_labels = [datetime.fromtimestamp(timestamps[i]).strftime("%H:%M") for i in indices]
        plt.xticks(indices, time_labels)

    plt.xlabel("Time")
    plt.ylabel("Bucket")
    plt.show()


# ---------------------------------------------------------------------------
# Data parsing
# ---------------------------------------------------------------------------

def _parse_prom_response(data: dict) -> list[dict]:
    """Parse Prometheus range query JSON into series list."""
    result_data = data.get("data", data)
    if isinstance(result_data, dict):
        if result_data.get("resultType") != "matrix":
            return []
        results = result_data.get("result", [])
    else:
        return []

    series = []
    for result in results:
        label = _format_metric_label(result.get("metric", {}))
        values_raw = result.get("values", [])
        timestamps = [v[0] for v in values_raw]
        values = [float(v[1]) for v in values_raw]
        series.append({"label": label, "timestamps": timestamps, "values": values})
    return series


def _format_metric_label(metric: dict) -> str:
    name = metric.get("__name__", "")
    rest = {k: v for k, v in metric.items() if k != "__name__"}
    if not rest and name:
        return name
    labels = ", ".join(f'{k}="{v}"' for k, v in rest.items())
    if name:
        return f"{name}{{{labels}}}"
    return f"{{{labels}}}"


# ---------------------------------------------------------------------------
# Label simplification
# ---------------------------------------------------------------------------

def _simplify_labels(labels: list[str]) -> list[str]:
    if len(labels) <= 1:
        return labels

    parsed = [_parse_label(l) for l in labels]
    if all(p is not None for p in parsed):
        all_keys = [sorted(p.keys()) for p in parsed]
        if all(k == all_keys[0] for k in all_keys):
            keys = all_keys[0]
            varying = [k for k in keys if len({p[k] for p in parsed}) > 1]
            if varying:
                if len(varying) == 1:
                    values = [p[varying[0]] for p in parsed]
                    return _strip_common_affixes(values)
                return [", ".join(f"{k}={p[k]}" for k in varying) for p in parsed]

    return _strip_common_affixes(labels)


def _parse_label(label: str) -> dict | None:
    match = re.search(r"\{(.+)\}", label)
    if not match:
        return None
    pairs = re.findall(r'(\w+)="([^"]*)"', match.group(1))
    return dict(pairs) if pairs else None


def _strip_common_affixes(labels: list[str]) -> list[str]:
    if len(labels) <= 1:
        return labels

    seps = set("-_/.")

    # Common prefix
    prefix = 0
    first = labels[0]
    for i in range(len(first)):
        if all(i < len(l) and l[i] == first[i] for l in labels):
            prefix = i + 1
        else:
            break

    # Snap prefix: keep one word segment for context
    if prefix > 0:
        sep1 = -1
        for i in range(prefix - 1, -1, -1):
            if first[i] in seps:
                sep1 = i
                break
        if sep1 > 0:
            sep2 = -1
            for i in range(sep1 - 1, -1, -1):
                if first[i] in seps:
                    sep2 = i
                    break
            prefix = sep2 + 1 if sep2 >= 0 else 0
        else:
            prefix = 0

    # Common suffix
    suffix = 0
    for i in range(len(first)):
        if all(i < len(l) and l[-(i + 1)] == first[-(i + 1)] for l in labels):
            suffix = i + 1
        else:
            break
    if suffix > 0 and suffix < len(first):
        for i in range(suffix, -1, -1):
            idx = len(first) - 1 - i
            if 0 <= idx < len(first) and first[idx] in seps:
                suffix = i
                break

    return [l[prefix: len(l) - suffix if suffix else len(l)] or l for l in labels]


# ---------------------------------------------------------------------------
# Histogram helpers
# ---------------------------------------------------------------------------

def _extract_le(label: str) -> float:
    m = re.search(r'le="([^"]+)"', label)
    if not m:
        return 0
    if m.group(1) == "+Inf":
        return float("inf")
    return float(m.group(1))


def _extract_bucket_label(label: str) -> str:
    m = re.search(r'le="([^"]+)"', label)
    if m:
        if m.group(1) == "+Inf":
            return "+Inf"
        return _fmt(float(m.group(1)))
    return label[:16]


def _detect_cumulative(sorted_series: list[dict]) -> bool:
    if len(sorted_series) < 2:
        return False
    if not any('le="' in s["label"] for s in sorted_series):
        return False
    for vi in range(min(len(sorted_series[0]["values"]), 5)):
        for si in range(1, len(sorted_series)):
            if sorted_series[si]["values"][vi] < sorted_series[si - 1]["values"][vi]:
                return False
    return True


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    if 0 < abs(v) < 0.01:
        return f"{v:.1e}"
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


def _nice_num(value: float, do_round: bool) -> float:
    if value == 0:
        return 0
    exp = math.floor(math.log10(abs(value)))
    frac = value / (10 ** exp)
    if do_round:
        if frac < 1.5:
            nice = 1
        elif frac < 3:
            nice = 2
        elif frac < 7:
            nice = 5
        else:
            nice = 10
    else:
        if frac <= 1:
            nice = 1
        elif frac <= 2:
            nice = 2
        elif frac <= 5:
            nice = 5
        else:
            nice = 10
    return nice * (10 ** exp)


def _nice_ticks(mn: float, mx: float, max_ticks: int = 8) -> list[float]:
    if mx == mn:
        return [mn]
    rng = _nice_num(mx - mn, False)
    spacing = _nice_num(rng / (max_ticks - 1), True)
    nice_min = math.floor(mn / spacing) * spacing
    nice_max = math.ceil(mx / spacing) * spacing

    ticks = []
    v = nice_min
    while v <= nice_max + spacing * 0.5:
        ticks.append(round(v, 10))
        v += spacing
    return ticks


def _print_stats_table(series: list[dict], labels: list[str]) -> None:
    lw = 38
    print()
    print(f"{'Series':<{lw}} {'Min':>10} {'Max':>10} {'Avg':>10} {'Last':>10}")
    print("─" * (lw + 44))
    for s, label in zip(series, labels):
        vals = s["values"]
        mn, mx = min(vals), max(vals)
        avg = sum(vals) / len(vals)
        last = vals[-1]
        short = label[: lw - 3] + "..." if len(label) > lw else label
        print(f"{short:<{lw}} {_fmt(mn):>10} {_fmt(mx):>10} {_fmt(avg):>10} {_fmt(last):>10}")
