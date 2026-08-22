"""
SVG charts for survey reporting - pure standard library.

Four forms, chosen for what survey data actually has to show:

    dot_plot_ci     a score with its uncertainty, because a favourable rate
                    without an interval invites over-reading
    heatmap         dimension x segment, the standard survey read-out grid
    quadrant        impact against performance - where the priorities are
    diverging_bars  sentiment, which has a natural zero and two directions

Colours come from a validated palette: blue #2a78d6, orange #eb6834 and aqua
#1baf7a for categories (checked for colour-vision deficiency separation), a
single blue ramp for magnitude, and blue-to-red through neutral grey for
polarity. Every mark that carries meaning is also labelled, so nothing depends
on colour alone.
"""

from __future__ import annotations

import math
from pathlib import Path

W, H = 900, 520
M = {"top": 104, "right": 56, "bottom": 88, "left": 250}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
SURFACE = "#fcfcfb"
INK = "#14161a"
SECONDARY = "#52514e"
MUTED = "#7a7975"
GRID = "#e7e7e4"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED = "#e34948"
NEUTRAL = "#c9c8c3"

# One-hue sequential ramp, light to dark, for magnitude.
SEQUENTIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
              "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab"]


def esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, color=INK, anchor="start", weight="400", opacity=1.0):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}" '
            f'opacity="{opacity}">{esc(s)}</text>')


def frame(title: str, subtitle: str = "") -> list[str]:
    out = [f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
           text(48, 42, title, size=19, weight="600")]
    if subtitle:
        out.append(text(48, 65, subtitle, size=13, color=SECONDARY))
    return out


def save(path: Path, body: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" role="img">' + "".join(body) + "</svg>", encoding="utf-8")
    return path


def ramp_color(value: float, low: float, high: float) -> str:
    """Position on the sequential ramp for a value inside [low, high]."""
    if high <= low:
        return SEQUENTIAL[len(SEQUENTIAL) // 2]
    t = max(0.0, min(1.0, (value - low) / (high - low)))
    return SEQUENTIAL[min(len(SEQUENTIAL) - 1, int(t * len(SEQUENTIAL)))]


# --------------------------------------------------------------------------

def dot_plot_ci(path, labels, values, lows, highs, title, subtitle="",
                reference=None, reference_label="", fmt=lambda v: f"{v:.0%}",
                color=BLUE, xlabel="") -> Path:
    """Horizontal dot plot with 95% confidence intervals."""
    left, right = M["left"], W - M["right"]
    top, bottom = M["top"], H - M["bottom"]
    body = frame(title, subtitle)

    lo = min(min(lows), reference or 1) * 0.92
    hi = max(max(highs), reference or 0) * 1.04
    span = hi - lo or 1

    def sx(v):
        return left + (v - lo) / span * (right - left)

    tick = 0.1 if span > 0.25 else 0.05
    t = math.ceil(lo / tick) * tick
    while t <= hi:
        body.append(f'<line x1="{sx(t):.1f}" y1="{top - 14}" x2="{sx(t):.1f}" y2="{bottom}" '
                    f'stroke="{GRID}" stroke-width="1"/>')
        body.append(text(sx(t), bottom + 24, fmt(t), size=12, color=MUTED, anchor="middle"))
        t += tick

    if reference is not None:
        body.append(f'<line x1="{sx(reference):.1f}" y1="{top - 14}" x2="{sx(reference):.1f}" '
                    f'y2="{bottom}" stroke="{SECONDARY}" stroke-width="1.5" '
                    f'stroke-dasharray="5 4"/>')
        body.append(text(sx(reference), top - 22, reference_label, size=12,
                         color=SECONDARY, anchor="middle", weight="600"))

    slot = (bottom - top) / len(values)
    for i, (label, value, low, high) in enumerate(zip(labels, values, lows, highs)):
        y = top + slot * (i + 0.5)
        body.append(f'<line x1="{sx(low):.1f}" y1="{y:.1f}" x2="{sx(high):.1f}" y2="{y:.1f}" '
                    f'stroke="{color}" stroke-width="2" opacity="0.42" stroke-linecap="round"/>')
        for edge in (low, high):
            body.append(f'<line x1="{sx(edge):.1f}" y1="{y - 4:.1f}" x2="{sx(edge):.1f}" '
                        f'y2="{y + 4:.1f}" stroke="{color}" stroke-width="2" opacity="0.42"/>')
        body.append(f'<circle cx="{sx(value):.1f}" cy="{y:.1f}" r="6" fill="{color}" '
                    f'stroke="{SURFACE}" stroke-width="2"/>')
        body.append(text(left - 16, y + 5, label, size=13, anchor="end"))
        body.append(text(sx(high) + 12, y + 5, fmt(value), size=12.5,
                         color=SECONDARY, weight="600"))

    if xlabel:
        body.append(text((left + right) / 2, H - 26, xlabel, size=12,
                         color=MUTED, anchor="middle"))
    return save(Path(path), body)


def heatmap(path, row_labels, col_labels, matrix, title, subtitle="",
            fmt=lambda v: f"{v:.0%}", note="") -> Path:
    """Sequential heatmap with a value in every cell - never colour alone."""
    left = 250
    top = M["top"]
    right, bottom = W - 40, H - 96
    body = frame(title, subtitle)

    flat = [v for row in matrix for v in row if v == v]
    lo, hi = (min(flat), max(flat)) if flat else (0, 1)

    cell_w = (right - left) / len(col_labels)
    cell_h = (bottom - top) / len(row_labels)

    for j, col in enumerate(col_labels):
        x = left + cell_w * (j + 0.5)
        body.append(text(x, top - 14, col, size=12, color=SECONDARY, anchor="middle"))

    for i, row_label in enumerate(row_labels):
        y = top + cell_h * i
        body.append(text(left - 16, y + cell_h / 2 + 5, row_label, size=13, anchor="end"))
        for j, value in enumerate(matrix[i]):
            x = left + cell_w * j
            if value != value:                      # suppressed cell
                body.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{cell_w - 2:.1f}" '
                            f'height="{cell_h - 2:.1f}" rx="3" fill="{SURFACE}" '
                            f'stroke="{GRID}" stroke-width="1"/>')
                body.append(text(x + cell_w / 2, y + cell_h / 2 + 4, "n/a", size=11,
                                 color=MUTED, anchor="middle"))
                continue
            fill = ramp_color(value, lo, hi)
            dark = value > lo + (hi - lo) * 0.62
            body.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{cell_w - 2:.1f}" '
                        f'height="{cell_h - 2:.1f}" rx="3" fill="{fill}"/>')
            body.append(text(x + cell_w / 2, y + cell_h / 2 + 5, fmt(value), size=12.5,
                             color="#ffffff" if dark else INK, anchor="middle", weight="600"))

    legend_x = left
    body.append(text(legend_x, bottom + 34, f"{fmt(lo)}", size=11, color=MUTED))
    for k, colour in enumerate(SEQUENTIAL):
        body.append(f'<rect x="{legend_x + 40 + k * 15}" y="{bottom + 24}" width="14" '
                    f'height="9" fill="{colour}"/>')
    body.append(text(legend_x + 40 + len(SEQUENTIAL) * 15 + 6, bottom + 34, f"{fmt(hi)}",
                     size=11, color=MUTED))
    if note:
        body.append(text(right, bottom + 34, note, size=11, color=MUTED, anchor="end"))
    return save(Path(path), body)


def quadrant(path, labels, x_values, y_values, title, subtitle="",
             xlabel="", ylabel="", x_fmt=lambda v: f"{v:.0%}",
             y_fmt=lambda v: f"{v:.0%}", highlight=()) -> Path:
    """Impact against performance: the priority map."""
    left, right = 96, W - 56
    top, bottom = M["top"] + 6, H - 92
    body = frame(title, subtitle)

    x_lo, x_hi = min(x_values), max(x_values)
    y_lo, y_hi = min(y_values), max(y_values)
    x_pad, y_pad = (x_hi - x_lo) * 0.22 or 0.05, (y_hi - y_lo) * 0.22 or 0.05
    x_lo, x_hi = x_lo - x_pad, x_hi + x_pad
    y_lo, y_hi = y_lo - y_pad, y_hi + y_pad

    def sx(v):
        return left + (v - x_lo) / (x_hi - x_lo) * (right - left)

    def sy(v):
        return bottom - (v - y_lo) / (y_hi - y_lo) * (bottom - top)

    x_mid = sum(x_values) / len(x_values)
    y_mid = sum(y_values) / len(y_values)

    body.append(f'<rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}" '
                f'fill="none" stroke="{GRID}" stroke-width="1"/>')
    body.append(f'<line x1="{sx(x_mid):.1f}" y1="{top}" x2="{sx(x_mid):.1f}" y2="{bottom}" '
                f'stroke="{GRID}" stroke-width="1.5"/>')
    body.append(f'<line x1="{left}" y1="{sy(y_mid):.1f}" x2="{right}" y2="{sy(y_mid):.1f}" '
                f'stroke="{GRID}" stroke-width="1.5"/>')

    quadrant_labels = [
        (sx(x_mid) + 10, top + 20, "Maintain", "start"),
        (sx(x_mid) - 10, top + 20, "Monitor", "end"),
        (sx(x_mid) + 10, bottom - 12, "Fix first", "start"),
        (sx(x_mid) - 10, bottom - 12, "Low priority", "end"),
    ]
    for qx, qy, label, anchor in quadrant_labels:
        body.append(text(qx, qy, label.upper(), size=11, color=MUTED, anchor=anchor,
                         weight="600"))

    for label, xv, yv in zip(labels, x_values, y_values):
        priority = xv > x_mid and yv < y_mid
        colour = ORANGE if priority or label in highlight else BLUE
        body.append(f'<circle cx="{sx(xv):.1f}" cy="{sy(yv):.1f}" r="8" fill="{colour}" '
                    f'stroke="{SURFACE}" stroke-width="2"/>')
        anchor = "end" if sx(xv) > (left + right) / 2 else "start"
        offset = -14 if anchor == "end" else 14
        body.append(text(sx(xv) + offset, sy(yv) + 4.5, label, size=12.5,
                         color=INK if priority else SECONDARY,
                         anchor=anchor, weight="600" if priority else "400"))

    body.append(text((left + right) / 2, H - 30, xlabel, size=12, color=MUTED, anchor="middle"))
    body.append(f'<text x="26" y="{(top + bottom) / 2:.1f}" font-family="{FONT}" '
                f'font-size="12" fill="{MUTED}" text-anchor="middle" '
                f'transform="rotate(-90 26 {(top + bottom) / 2:.1f})">{esc(ylabel)}</text>')
    return save(Path(path), body)


def diverging_bars(path, labels, values, counts, title, subtitle="",
                   xlabel="", fmt=lambda v: f"{v:+.2f}") -> Path:
    """Sentiment around a true zero: blue for positive, red for negative."""
    left, right = M["left"], W - M["right"]
    top, bottom = M["top"], H - M["bottom"]
    body = frame(title, subtitle)

    extent = max(abs(min(values)), abs(max(values))) * 1.25 or 1
    centre = (left + right) / 2
    half = (right - left) / 2

    def sx(v):
        return centre + v / extent * half

    for t in (-extent, -extent / 2, 0.0, extent / 2, extent):
        body.append(f'<line x1="{sx(t):.1f}" y1="{top - 12}" x2="{sx(t):.1f}" y2="{bottom}" '
                    f'stroke="{GRID if t else NEUTRAL}" stroke-width="{1.5 if not t else 1}"/>')
        body.append(text(sx(t), bottom + 24, f"{t:+.1f}" if t else "0", size=11,
                         color=MUTED, anchor="middle"))

    slot = (bottom - top) / len(values)
    height = min(slot * 0.55, 26)
    for i, (label, value, count) in enumerate(zip(labels, values, counts)):
        y = top + slot * (i + 0.5) - height / 2
        x0, x1 = (sx(0), sx(value)) if value >= 0 else (sx(value), sx(0))
        body.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(2, x1 - x0):.1f}" '
                    f'height="{height:.1f}" rx="3" fill="{BLUE if value >= 0 else RED}"/>')
        body.append(text(left - 16, y + height / 2 + 5, label, size=13, anchor="end"))
        # Long bars carry their value inside; short ones outside, where there is room.
        inside = (x1 - x0) > 96
        if inside:
            label_x = x0 + 10 if value < 0 else x1 - 10
            anchor = "start" if value < 0 else "end"
            colour = "#ffffff"
        else:
            label_x = x0 - 10 if value < 0 else x1 + 10
            anchor = "end" if value < 0 else "start"
            colour = SECONDARY
        body.append(text(label_x, y + height / 2 + 5, f"{fmt(value)}  ({count})", size=12,
                         color=colour, anchor=anchor, weight="600" if inside else "400"))

    if xlabel:
        body.append(text(centre, H - 26, xlabel, size=12, color=MUTED, anchor="middle"))
    return save(Path(path), body)


def histogram(path, values, title, subtitle="", bins=14, xlabel="", ylabel="teams",
              markers=(), fmt=lambda v: f"{v:.0%}") -> Path:
    """Distribution of team-level scores, with optional reference markers."""
    left, right = 96, W - 56
    top, bottom = M["top"], H - M["bottom"]
    body = frame(title, subtitle)

    lo, hi = min(values), max(values)
    width = (hi - lo) / bins or 1
    counts = [0] * bins
    for v in values:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    peak = max(counts)

    for k in range(0, peak + 1, max(1, peak // 4)):
        y = bottom - k / peak * (bottom - top)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                    f'stroke="{GRID}" stroke-width="1"/>')
        body.append(text(left - 12, y + 4, str(k), size=11, color=MUTED, anchor="end"))

    slot = (right - left) / bins
    for i, count in enumerate(counts):
        h = count / peak * (bottom - top)
        body.append(f'<rect x="{left + slot * i + 1.5:.1f}" y="{bottom - h:.1f}" '
                    f'width="{slot - 3:.1f}" height="{h:.1f}" rx="3" fill="{BLUE}"/>')

    for i in range(0, bins + 1, max(1, bins // 7)):
        x = left + slot * i
        body.append(text(x, bottom + 24, fmt(lo + width * i), size=11,
                         color=MUTED, anchor="middle"))

    for value, label, colour in markers:
        x = left + (value - lo) / (hi - lo) * (right - left)
        body.append(f'<line x1="{x:.1f}" y1="{top - 12}" x2="{x:.1f}" y2="{bottom}" '
                    f'stroke="{colour}" stroke-width="2" stroke-dasharray="5 4"/>')
        body.append(text(x, top - 20, label, size=12, color=colour, anchor="middle",
                         weight="600"))

    body.append(text((left + right) / 2, H - 26, xlabel, size=12, color=MUTED, anchor="middle"))
    body.append(f'<text x="26" y="{(top + bottom) / 2:.1f}" font-family="{FONT}" '
                f'font-size="12" fill="{MUTED}" text-anchor="middle" '
                f'transform="rotate(-90 26 {(top + bottom) / 2:.1f})">{esc(ylabel)}</text>')
    return save(Path(path), body)
