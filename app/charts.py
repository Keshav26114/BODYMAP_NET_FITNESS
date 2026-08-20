"""
app/charts.py — server-side Matplotlib chart builders. Each returns a base64
PNG string for direct use in <img src="data:image/png;base64,{{ chart }}">.
Colors are pulled live from the site's shared appearance settings (theme +
accent color), so charts always match whatever look is currently active
instead of a fixed white/orange palette.
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
from db import database as db  # noqa: E402

# Fallback palette if appearance can't be read for any reason.
_DEFAULT_ACCENT = "#FF3E00"


def _palette():
    """
    Build the color palette to draw this chart with, from the site's
    current shared theme + accent color (Settings > Appearance). Called
    fresh for every chart so it always reflects whatever's active right
    now, rather than being baked in at import time.
    """
    try:
        appearance = db.get_appearance()
    except Exception:
        appearance = {}
    theme = (appearance or {}).get("theme") or "light"
    accent = (appearance or {}).get("accent_color") or _DEFAULT_ACCENT

    if theme == "dark":
        ink = "#FFFFFF"
        base = "#242428"
        surface = "#131316"
        muted = "#999999"
        grid = "#3A3A3E"
    else:
        ink = "#000000"
        base = "#FFFFFF"
        surface = "#F5F5F0"
        muted = "#888888"
        grid = "#DDDDDD"

    return {
        "ink": ink, "base": base, "safety": accent,
        "muted": muted, "surface": surface, "grid": grid,
    }


def _rc(pal):
    """Matplotlib rcParams matching the given palette."""
    return {
        "font.family": "monospace",
        "axes.edgecolor": pal["ink"],
        "axes.linewidth": 1.5,
        "text.color": pal["ink"],
        "axes.labelcolor": pal["ink"],
        "xtick.color": pal["ink"],
        "ytick.color": pal["ink"],
        "figure.facecolor": pal["base"],
        "axes.facecolor": pal["base"],
        "savefig.facecolor": pal["base"],
    }


def _fig_to_base64(fig, pal):
    fig.patch.set_facecolor(pal["base"])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=pal["base"])
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def make_exercise_bar_chart(group_scores):
    """One bar per of the 9 groups; reference line at 1.0 (baseline)."""
    pal = _palette()
    groups = list(config.EXERCISE_GROUPS)
    values = [group_scores.get(g, 0.0) for g in groups]
    colors = [pal["safety"] if v >= 1.0 else pal["ink"] for v in values]

    with plt.rc_context(_rc(pal)):
        fig, ax = plt.subplots(figsize=(6.2, 3.2))
        ax.bar(range(len(groups)), values, color=colors, edgecolor=pal["ink"], linewidth=1.2)
        ax.axhline(1.0, color=pal["safety"], linewidth=1.4, linestyle="--")
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(groups, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("ratio to baseline", fontsize=8)
        ax.set_title("VOLUME BY MUSCLE GROUP", fontsize=9, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return _fig_to_base64(fig, pal)


def make_gauge_bar_chart(value, bands, label):
    """Single horizontal bar showing where `value` falls across the bands."""
    pal = _palette()
    with plt.rc_context(_rc(pal)):
        fig, ax = plt.subplots(figsize=(6.2, 1.5))
        band_names = [bands[k] for k in sorted(bands.keys())]
        n = len(band_names)
        # segmented background track
        for i in range(n):
            ax.barh(0, 1, left=i, height=0.5,
                    color=pal["surface"] if i % 2 == 0 else pal["grid"],
                    edgecolor=pal["ink"], linewidth=1.0)
            ax.text(i + 0.5, 0, band_names[i], ha="center", va="center",
                    fontsize=6.5, color=pal["muted"])
        if value is not None:
            # map value onto [0, n] using a simple clamp for display
            pos = max(0.0, min(float(value), n))
            ax.axvline(pos, color=pal["safety"], linewidth=2.5)
            ax.text(pos, 0.45, f"{label}", ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=pal["safety"])
        ax.set_xlim(0, n)
        ax.set_ylim(-0.4, 0.7)
        ax.axis("off")
        ax.set_title(label.upper(), fontsize=9, fontweight="bold", loc="left")
        return _fig_to_base64(fig, pal)


def make_calorie_bar_chart(current_intake, target):
    """Two bars: current vs target daily calories."""
    pal = _palette()
    current_intake = float(current_intake) if current_intake else 0.0
    target = float(target) if target else 0.0
    with plt.rc_context(_rc(pal)):
        fig, ax = plt.subplots(figsize=(4.6, 3.0))
        ax.bar(["Current", "Target"], [current_intake, target],
               color=[pal["safety"], pal["ink"]], edgecolor=pal["ink"], linewidth=1.2)
        for i, v in enumerate([current_intake, target]):
            ax.text(i, v, f"{int(v)}", ha="center", va="bottom", fontsize=8, fontweight="bold")
        ax.set_ylabel("kcal / day", fontsize=8)
        ax.set_title("INTAKE vs TARGET", fontsize=9, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return _fig_to_base64(fig, pal)


def _archetype_centroids(radius=3.0):
    pts = {}
    for label in range(len(config.ARCHETYPES)):
        angle = math.radians(label * 72.0)
        pts[label] = (radius * math.cos(angle), radius * math.sin(angle))
    return pts


def make_archetype_map_chart(user_point, archetype_label):
    """Scatter with 5 fixed labeled centroids + the highlighted user point."""
    pal = _palette()
    centroids = _archetype_centroids()
    with plt.rc_context(_rc(pal)):
        fig, ax = plt.subplots(figsize=(5.4, 5.0))

        for label, (cx, cy) in centroids.items():
            is_user = (label == archetype_label)
            ax.scatter([cx], [cy], s=260 if is_user else 180,
                       color=pal["safety"] if is_user else pal["surface"],
                       edgecolor=pal["ink"], linewidth=1.4, zorder=2)
            ax.annotate(config.ARCHETYPES[label], (cx, cy),
                        textcoords="offset points", xytext=(0, 14),
                        ha="center", fontsize=7, fontweight="bold")

        if user_point is not None:
            ux, uy = float(user_point[0]), float(user_point[1])
            ax.scatter([ux], [uy], s=320, marker="X", color=pal["ink"],
                       edgecolor=pal["safety"], linewidth=2.0, zorder=5)
            ax.annotate("YOU", (ux, uy), textcoords="offset points",
                        xytext=(0, -18), ha="center", fontsize=8,
                        fontweight="bold", color=pal["safety"])

        ax.set_title("BEHAVIOUR PROFILE MAP", fontsize=9, fontweight="bold")
        ax.set_xlim(-5, 5)
        ax.set_ylim(-5, 5)
        ax.set_aspect("equal")
        ax.axhline(0, color=pal["muted"], linewidth=0.5, alpha=0.4)
        ax.axvline(0, color=pal["muted"], linewidth=0.5, alpha=0.4)
        ax.set_xticks([])
        ax.set_yticks([])
        return _fig_to_base64(fig, pal)
