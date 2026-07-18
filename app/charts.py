"""
app/charts.py — server-side Matplotlib chart builders. Each returns a base64
PNG string for direct use in <img src="data:image/png;base64,{{ chart }}">.
Styled to match the Axis Industrial theme (mono type, safety-orange accent).
"""

import os
import sys
import io
import math
import base64

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402

# Axis Industrial palette
INK = "#000000"
BASE = "#FFFFFF"
SAFETY = "#FF3E00"
MUTED = "#888888"
SURFACE = "#F5F5F0"

plt.rcParams.update({
    "font.family": "monospace",
    "axes.edgecolor": INK,
    "axes.linewidth": 1.5,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "figure.facecolor": BASE,
    "axes.facecolor": BASE,
})


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def make_exercise_bar_chart(group_scores):
    """One bar per of the 9 groups; reference line at 1.0 (baseline)."""
    groups = list(config.EXERCISE_GROUPS)
    values = [group_scores.get(g, 0.0) for g in groups]
    colors = [SAFETY if v >= 1.0 else INK for v in values]

    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.bar(range(len(groups)), values, color=colors, edgecolor=INK, linewidth=1.2)
    ax.axhline(1.0, color=SAFETY, linewidth=1.4, linestyle="--")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("ratio to baseline", fontsize=8)
    ax.set_title("VOLUME BY MUSCLE GROUP", fontsize=9, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_base64(fig)


def make_gauge_bar_chart(value, bands, label):
    """Single horizontal bar showing where `value` falls across the bands."""
    fig, ax = plt.subplots(figsize=(6.2, 1.5))
    band_names = [bands[k] for k in sorted(bands.keys())]
    n = len(band_names)
    # segmented background track
    for i in range(n):
        ax.barh(0, 1, left=i, height=0.5,
                color=SURFACE if i % 2 == 0 else "#E6E6E0",
                edgecolor=INK, linewidth=1.0)
        ax.text(i + 0.5, 0, band_names[i], ha="center", va="center",
                fontsize=6.5, color=MUTED)
    if value is not None:
        # map value onto [0, n] using a simple clamp for display
        pos = max(0.0, min(float(value), n))
        ax.axvline(pos, color=SAFETY, linewidth=2.5)
        ax.text(pos, 0.45, f"{label}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color=SAFETY)
    ax.set_xlim(0, n)
    ax.set_ylim(-0.4, 0.7)
    ax.axis("off")
    ax.set_title(label.upper(), fontsize=9, fontweight="bold", loc="left")
    return _fig_to_base64(fig)


def make_calorie_bar_chart(current_intake, target):
    """Two bars: current vs target daily calories."""
    current_intake = float(current_intake) if current_intake else 0.0
    target = float(target) if target else 0.0
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.bar(["Current", "Target"], [current_intake, target],
           color=[SAFETY, INK], edgecolor=INK, linewidth=1.2)
    for i, v in enumerate([current_intake, target]):
        ax.text(i, v, f"{int(v)}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_ylabel("kcal / day", fontsize=8)
    ax.set_title("INTAKE vs TARGET", fontsize=9, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_base64(fig)


def _archetype_centroids(radius=3.0):
    pts = {}
    for label in range(len(config.ARCHETYPES)):
        angle = math.radians(label * 72.0)
        pts[label] = (radius * math.cos(angle), radius * math.sin(angle))
    return pts


def make_archetype_map_chart(user_point, archetype_label):
    """Scatter with 5 fixed labeled centroids + the highlighted user point."""
    centroids = _archetype_centroids()
    fig, ax = plt.subplots(figsize=(5.4, 5.0))

    for label, (cx, cy) in centroids.items():
        is_user = (label == archetype_label)
        ax.scatter([cx], [cy], s=260 if is_user else 180,
                   color=SAFETY if is_user else SURFACE,
                   edgecolor=INK, linewidth=1.4, zorder=2)
        ax.annotate(config.ARCHETYPES[label], (cx, cy),
                    textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=7, fontweight="bold")

    if user_point is not None:
        ux, uy = float(user_point[0]), float(user_point[1])
        ax.scatter([ux], [uy], s=320, marker="X", color=INK,
                   edgecolor=SAFETY, linewidth=2.0, zorder=5)
        ax.annotate("YOU", (ux, uy), textcoords="offset points",
                    xytext=(0, -18), ha="center", fontsize=8,
                    fontweight="bold", color=SAFETY)

    ax.set_title("BEHAVIOUR PROFILE MAP", fontsize=9, fontweight="bold")
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_aspect("equal")
    ax.axhline(0, color=MUTED, linewidth=0.5, alpha=0.4)
    ax.axvline(0, color=MUTED, linewidth=0.5, alpha=0.4)
    ax.set_xticks([])
    ax.set_yticks([])
    return _fig_to_base64(fig)
