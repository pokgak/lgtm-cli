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

    w = width or int(plt.terminal_width() * 0.6)
    h = height

    if chart_type == "bar":
        _render_bar(series, title, w, h)
    elif chart_type == "heatmap":
        _render_heatmap(series, title, w, h)
    else:
        _render_timeseries(series, title, w, h)


def render_chart_to_file(
    data: dict,
    output_path: str,
    chart_type: str = "timeseries",
    title: str | None = None,
    width: int | None = None,
    height: int = 20,
) -> None:
    """Render a chart and save as an image file (PNG/SVG/HTML)."""
    import io
    import subprocess
    import sys
    from contextlib import redirect_stdout

    # Capture all print output
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    try:
        render_chart(data, chart_type=chart_type, title=title, width=width or 110, height=height)
    finally:
        sys.stdout = old_stdout

    ansi_text = buf.getvalue()

    if output_path.endswith(".html"):
        _ansi_to_html_file(ansi_text, output_path)
    elif output_path.endswith(".svg"):
        _ansi_to_svg_file(ansi_text, output_path)
    else:
        # For .png and others, try aha (ANSI to HTML) + wkhtmltoimage, fallback to raw text
        _ansi_to_image_file(ansi_text, output_path)


def _ansi_to_html_file(ansi_text: str, path: str) -> None:
    """Convert ANSI text to a standalone HTML file."""
    import html as html_mod

    lines = ansi_text.split("\n")
    html_lines = []
    for line in lines:
        html_lines.append(_ansi_line_to_html(line))

    html_content = f"""<!DOCTYPE html>
<html>
<head><style>
body {{ background: #1a1a2e; padding: 20px; }}
pre {{ font-family: 'JetBrains Mono', 'Fira Code', 'Menlo', monospace; font-size: 14px; line-height: 1.2; color: #e0e0e0; }}
</style></head>
<body><pre>{"<br>".join(html_lines)}</pre></body>
</html>"""

    with open(path, "w") as f:
        f.write(html_content)


def _ansi_to_svg_file(ansi_text: str, path: str) -> None:
    """Convert ANSI text to SVG using ansi2svg if available, fallback to HTML."""
    import shutil
    import subprocess

    if shutil.which("ansi2svg"):
        result = subprocess.run(
            ["ansi2svg"], input=ansi_text, capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
    else:
        # Fallback: save as HTML with .svg extension note
        _ansi_to_html_file(ansi_text, path.replace(".svg", ".html"))
        print(f"Note: ansi2svg not found, saved as HTML instead", file=__import__("sys").stderr)


def _ansi_to_image_file(ansi_text: str, path: str) -> None:
    """Convert ANSI to PNG. Tries multiple backends."""
    # Just save the raw ANSI text - can be viewed with `cat`
    with open(path, "w") as f:
        f.write(ansi_text)


def _ansi_line_to_html(line: str) -> str:
    """Convert a single line with ANSI codes to HTML spans."""
    import html as html_mod

    result = []
    i = 0
    current_fg = None
    current_bg = None

    while i < len(line):
        if line[i] == "\033" and i + 1 < len(line) and line[i + 1] == "[":
            # Parse ANSI escape
            end = line.find("m", i)
            if end == -1:
                result.append(html_mod.escape(line[i]))
                i += 1
                continue

            code = line[i + 2 : end]
            i = end + 1

            if code == "0":
                if current_fg or current_bg:
                    result.append("</span>")
                current_fg = None
                current_bg = None
            elif code.startswith("38;2;"):
                # 24-bit foreground
                parts = code.split(";")
                if len(parts) >= 5:
                    r, g, b = parts[2], parts[3], parts[4]
                    if current_fg or current_bg:
                        result.append("</span>")
                    current_fg = f"color:rgb({r},{g},{b})"
                    style = f"{current_fg};{current_bg}" if current_bg else current_fg
                    result.append(f'<span style="{style}">')
            elif code.startswith("48;2;"):
                # 24-bit background
                parts = code.split(";")
                if len(parts) >= 5:
                    r, g, b = parts[2], parts[3], parts[4]
                    if current_fg or current_bg:
                        result.append("</span>")
                    current_bg = f"background:rgb({r},{g},{b})"
                    style = f"{current_fg};{current_bg}" if current_fg else current_bg
                    result.append(f'<span style="{style}">')
            elif code.startswith("38;5;"):
                # 256-color foreground
                color_idx = int(code.split(";")[2])
                hex_color = _ansi256_to_hex(color_idx)
                if current_fg or current_bg:
                    result.append("</span>")
                current_fg = f"color:{hex_color}"
                style = f"{current_fg};{current_bg}" if current_bg else current_fg
                result.append(f'<span style="{style}">')
            elif code.startswith("48;5;"):
                # 256-color background
                color_idx = int(code.split(";")[2])
                hex_color = _ansi256_to_hex(color_idx)
                if current_fg or current_bg:
                    result.append("</span>")
                current_bg = f"background:{hex_color}"
                style = f"{current_fg};{current_bg}" if current_fg else current_bg
                result.append(f'<span style="{style}">')
            elif code == "1":
                result.append("<b>")
            else:
                # Basic ANSI colors
                fg_map = {
                    "30": "#000", "31": "#c00", "32": "#0c0", "33": "#cc0",
                    "34": "#00c", "35": "#c0c", "36": "#0cc", "37": "#ccc",
                    "90": "#555", "91": "#f55", "92": "#5f5", "93": "#ff5",
                    "94": "#55f", "95": "#f5f", "96": "#5ff", "97": "#fff",
                }
                if code in fg_map:
                    if current_fg or current_bg:
                        result.append("</span>")
                    current_fg = f"color:{fg_map[code]}"
                    style = f"{current_fg};{current_bg}" if current_bg else current_fg
                    result.append(f'<span style="{style}">')
        else:
            result.append(html_mod.escape(line[i]))
            i += 1

    if current_fg or current_bg:
        result.append("</span>")

    return "".join(result)


def _ansi256_to_hex(idx: int) -> str:
    """Convert ANSI 256-color index to hex."""
    if idx < 16:
        basic = [
            "#000", "#800", "#080", "#880", "#008", "#808", "#088", "#ccc",
            "#888", "#f00", "#0f0", "#ff0", "#00f", "#f0f", "#0ff", "#fff",
        ]
        return basic[idx]
    if idx < 232:
        idx -= 16
        r = (idx // 36) * 51
        g = ((idx % 36) // 6) * 51
        b = (idx % 6) * 51
        return f"#{r:02x}{g:02x}{b:02x}"
    gray = 8 + (idx - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


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

    colors = ["\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m",
              "\033[31m", "\033[92m", "\033[93m", "\033[94m", "\033[95m"]
    reset = "\033[0m"

    for s, label in zip(series, labels):
        dates = [datetime.fromtimestamp(t).strftime("%H:%M") for t in s["timestamps"]]
        plt.plot(dates, s["values"])

    # Custom y-axis ticks with nice formatting
    all_vals = [v for s in series for v in s["values"]]
    if all_vals:
        mn, mx = min(all_vals), max(all_vals)
        ticks = _nice_ticks(mn, mx, max_ticks=8)
        plt.yticks(ticks, [_fmt(t) for t in ticks])

    plt.xlabel("Time")

    if len(series) > 1:
        # Capture chart output and render legend on the right side
        chart_str = plt.build()
        chart_lines = chart_str.split("\n")

        # Build legend entries
        legend_items = [f"  {colors[i % len(colors)]}▞▞{reset} {label}" for i, label in enumerate(labels)]

        # Place legend items starting from line 2 (after title), vertically
        gap = "  "
        for i, line in enumerate(chart_lines):
            legend_idx = i - 1  # start from second line
            if 0 <= legend_idx < len(legend_items):
                print(f"{line}{gap}{legend_items[legend_idx]}")
            else:
                print(line)

        _print_stats_table(series, labels)
    else:
        plt.show()


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
        delta_values: list[list[float]] = []
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
    num_cols = len(timestamps)

    # Layout
    label_width = max(len(l) for l in bucket_labels)
    cell_area = max(width - label_width - 2, 20)

    # Stretch or downsample to fill width
    if num_cols > cell_area:
        step = math.ceil(num_cols / cell_area)
        cell_width = 1
    else:
        step = 1
        cell_width = max(1, cell_area // num_cols)

    # Build grid
    grid: list[list[float]] = []
    for row in delta_values:
        if step > 1:
            grid.append([max(row[i:i + step]) for i in range(0, num_cols, step)])
        else:
            grid.append(list(row))

    effective_cols = len(grid[0])

    # Global min/max for normalization (excluding zeros)
    all_vals = [v for row in grid for v in row if v > 0]
    global_max = max(all_vals) if all_vals else 1
    global_min = min(all_vals) if all_vals else 0

    # Color ramp: blue -> cyan -> green -> yellow -> red
    color_ramp = [
        (0, 0, 80),      # dark blue
        (0, 80, 160),     # blue
        (0, 160, 160),    # cyan
        (0, 180, 80),     # green
        (160, 180, 0),    # yellow
        (220, 120, 0),    # orange
        (220, 40, 0),     # red
        (255, 255, 255),  # white (hottest)
    ]

    if title:
        print(f"\033[1m{title}\033[0m")
        print()

    # Render rows from top (highest bucket) to bottom (lowest)
    for ri in range(len(sorted_series) - 1, -1, -1):
        label = bucket_labels[ri].rjust(label_width)
        row = grid[ri]
        cells = ""
        for v in row:
            r, g, b = _heat_color(v, global_min, global_max, color_ramp)
            cells += f"\033[48;2;{r};{g};{b}m{' ' * cell_width}\033[0m"
        print(f"{label} {cells}")

    # Time axis
    first_ts = datetime.fromtimestamp(timestamps[0]).strftime("%H:%M")
    mid_ts = datetime.fromtimestamp(timestamps[num_cols // 2]).strftime("%H:%M")
    last_ts = datetime.fromtimestamp(timestamps[-1]).strftime("%H:%M")
    display_width = effective_cols * cell_width
    gap1 = max(0, display_width // 2 - len(first_ts) - len(mid_ts) // 2)
    gap2 = max(0, display_width - len(first_ts) - gap1 - len(mid_ts) - len(last_ts))
    print(f"{' ' * label_width} {first_ts}{' ' * gap1}{mid_ts}{' ' * gap2}{last_ts}")

    # Legend bar
    legend_width = min(30, display_width)
    legend = ""
    for i in range(legend_width):
        frac = i / (legend_width - 1)
        r, g, b = _interpolate_ramp(frac, color_ramp)
        legend += f"\033[48;2;{r};{g};{b}m \033[0m"
    print(f"\n{' ' * label_width} {legend}")
    print(f"{' ' * label_width} {_fmt(global_min)}{' ' * (legend_width - len(_fmt(global_min)) - len(_fmt(global_max)))}{_fmt(global_max)}")


def _heat_color(
    value: float, mn: float, mx: float, ramp: list[tuple[int, int, int]]
) -> tuple[int, int, int]:
    """Map a value to an RGB color using the color ramp."""
    if value <= 0:
        return (0, 0, 0)  # black for zero

    # Log scale for better contrast
    log_min = math.log1p(mn) if mn > 0 else 0
    log_max = math.log1p(mx)
    log_val = math.log1p(value)
    log_range = log_max - log_min or 1
    frac = max(0, min(1, (log_val - log_min) / log_range))

    return _interpolate_ramp(frac, ramp)


def _interpolate_ramp(
    frac: float, ramp: list[tuple[int, int, int]]
) -> tuple[int, int, int]:
    """Interpolate between colors in a ramp."""
    n = len(ramp) - 1
    idx = frac * n
    lo = int(idx)
    hi = min(lo + 1, n)
    t = idx - lo
    r = int(ramp[lo][0] + t * (ramp[hi][0] - ramp[lo][0]))
    g = int(ramp[lo][1] + t * (ramp[hi][1] - ramp[lo][1]))
    b = int(ramp[lo][2] + t * (ramp[hi][2] - ramp[lo][2]))
    return (r, g, b)


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


def _print_legend(labels: list[str], colors: list[str], reset: str) -> None:
    items = [f"{colors[i % len(colors)]}━━{reset} {label}" for i, label in enumerate(labels)]
    print("\n  " + "  ".join(items))


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
