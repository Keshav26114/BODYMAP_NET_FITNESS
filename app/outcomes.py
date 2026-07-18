"""
app/outcomes.py — the single source of truth for "is this result label good,
bad, or neutral news, given the user's goal?"

Before this module existed, three different places each had their own
opinion about the same label+goal combination:
  - app/insights.py's generate_goal_verdict() (the banner at the top of the
    result page)
  - app/insights.py's generate_insights() (the tips/recommendations panel)
  - app/streaks.py (consecutive-week streaks)

...and they didn't always agree — e.g. a deliberate calorie deficit while
trying to lose fat was praised as a "success" in the tips panel, ignored
(neutral) by the goal verdict, and counted as a *negative* streak. That's
exactly the kind of contradiction this module exists to prevent: every
place that needs to know whether a label is good news calls the SAME
function here, so the verdict banner, the tips, and the streaks always
tell the same story for the same data.

Every classifier below returns one of "good" / "bad" / "neutral":
  "good"    — clearly aligned with the goal, worth celebrating/reinforcing.
  "bad"     — clearly working against the goal (or against basic health,
              for outcomes that are goal-independent), worth flagging.
  "neutral" — not actionable either way — expected variation, or a state
              that isn't clearly good or bad for this particular goal.
"""

GOALS = ("lose_fat", "gain_muscle", "maintain", "improve_endurance")


def _norm_goal(goal):
    goal = (goal or "maintain").lower()
    return goal if goal in GOALS else "maintain"


# ---------------------------------------------------------------------------
# EXERCISE — training volume/balance is goal-independent: a balanced week is
# good, and being meaningfully under- or over-trained is bad no matter what
# you're training *for*.
# ---------------------------------------------------------------------------
def exercise_outcome(label, goal=None):
    if label == "Balanced":
        return "good"
    if label in ("Under-training", "Over-training"):
        return "bad"
    return "neutral"


# ---------------------------------------------------------------------------
# BMI — Normal is always good, Obese is always bad (health risk regardless
# of training goal). Overweight/Underweight depend on what you're going for.
# ---------------------------------------------------------------------------
def bmi_outcome(label, goal=None):
    goal = _norm_goal(goal)
    if label == "Normal":
        return "good"
    if label == "Obese":
        return "bad"
    if label == "Overweight":
        if goal == "gain_muscle":
            return "neutral"  # BMI can't tell muscle from fat during a bulk
        return "bad"
    if label == "Underweight":
        if goal == "gain_muscle":
            return "good"     # ideal starting point for a lean bulk
        if goal == "improve_endurance":
            return "neutral"  # common and not inherently unhealthy for endurance athletes
        return "bad"          # lose_fat / maintain
    return "neutral"


# ---------------------------------------------------------------------------
# BODY FAT — Fitness/Athletic are always good, Obese is always bad. Average
# and Essential depend on the goal.
# ---------------------------------------------------------------------------
def bodyfat_outcome(label, goal=None):
    goal = _norm_goal(goal)
    if label in ("Fitness", "Athletic"):
        return "good"
    if label == "Obese":
        return "bad"
    if label == "Essential":
        return "neutral"  # very lean — a caution, not a failure
    if label == "Average":
        if goal in ("gain_muscle", "improve_endurance"):
            return "neutral"
        return "bad"  # lose_fat / maintain
    return "neutral"


# ---------------------------------------------------------------------------
# CALORIES — On-target is always good. Over-eating and Under-eating cut
# both ways depending on the goal: a deliberate deficit is a WIN for
# lose_fat, not something to flag as bad.
# ---------------------------------------------------------------------------
def calorie_outcome(label, goal=None):
    goal = _norm_goal(goal)
    if label == "On-target":
        return "good"
    if label == "Over-eating":
        if goal in ("gain_muscle", "improve_endurance"):
            return "neutral"  # an intentional surplus is expected here
        return "bad"  # lose_fat / maintain
    if label == "Under-eating":
        if goal == "lose_fat":
            return "good"   # this is the point of a cut
        if goal == "gain_muscle":
            return "bad"    # a deficit directly undermines building muscle
        return "neutral"    # maintain / improve_endurance — a mild deficit, not clearly bad
    return "neutral"


# ---------------------------------------------------------------------------
# ARCHETYPE — matches the goal's target archetype = good, matches its
# opposite-of-goal archetype = bad, anything else = neutral.
# ---------------------------------------------------------------------------
GOAL_TARGET_ARCHETYPE = {
    "lose_fat":          "Average / Balanced",
    "gain_muscle":        "Buff / Muscular",
    "maintain":           "Average / Balanced",
    "improve_endurance":  "Endurance-Focused",
}
GOAL_ANTI_ARCHETYPE = {
    "lose_fat":          "Obesity Risk",
    "gain_muscle":        "Skinny Athlete",
    "maintain":           "Obesity Risk",
    "improve_endurance":  "Obesity Risk",
}


def archetype_outcome(archetype, goal=None):
    goal = _norm_goal(goal)
    if archetype == GOAL_TARGET_ARCHETYPE.get(goal):
        return "good"
    if archetype == GOAL_ANTI_ARCHETYPE.get(goal):
        return "bad"
    return "neutral"


# ---------------------------------------------------------------------------
# Shared display helpers, so the same outcome always maps to the same
# color/wording wherever it's rendered.
# ---------------------------------------------------------------------------
def badge_type(outcome):
    """Map an outcome to the insight-badge CSS type used in the tips panel."""
    return {"good": "success", "bad": "warning", "neutral": "tip"}.get(outcome, "info")


def streak_direction(outcome):
    """Map an outcome to a streak direction, or None if it shouldn't count
    toward any streak at all (neutral outcomes break a streak in progress
    but never start one of their own — same treatment as "no data")."""
    return {"good": "positive", "bad": "negative"}.get(outcome)
