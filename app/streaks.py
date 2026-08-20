"""
app/streaks.py — consecutive-WEEK consistency streaks.

This is deliberately separate from db.database's check-in streak, which
counts consecutive *days* the user logged any test at all. These streaks
instead look at the *content* of each logged week (one entry per
week_start, via db.get_weeks_for_user) and ask: for how many consecutive
weeks in a row has a given metric been trending the same direction?

Positive streaks   — consistent training, eating on target, healthy BMI,
                      on track for the user's goal.
Negative streaks    — inconsistent/over-under training, eating off target,
                      BMI drifting the wrong way, missing a specific muscle
                      group week after week, off track from the goal.

Every per-metric judgment call ("is this label good or bad news, given the
user's goal?") is delegated to app/outcomes.py — the same module the
goal-verdict banner and the tips panel use — so a week can never be a
"positive" streak here while being called out as a problem elsewhere.
A "neutral" outcome (e.g. a deliberate calorie surplus while bulking) ends
a streak in progress, exactly like an opposite-direction week would — and
critically, if the *most recent* logged week is neutral, that means there
is NO current streak for that metric, even if an older run of good/bad
weeks sits further back. A neutral week is real data, not a gap, so it's
never skipped past when deciding what's "current."

Only streaks of 2+ consecutive weeks are surfaced (a single week is not a
streak). "Consecutive" requires the two weeks' week_start dates to be
exactly 7 days apart — a gap week (or a week where that particular metric
wasn't tested at all) breaks the streak the same way, but unlike a neutral
result, a true gap IS skipped over when searching for the most recent
week that has real data for a metric.
"""

from datetime import datetime, timedelta

import config
from app import outcomes


def _weeks_apart(newer_iso, older_iso):
    """Number of days between two ISO week_start dates, or None if unparsable."""
    try:
        d_new = datetime.fromisoformat(newer_iso).date()
        d_old = datetime.fromisoformat(older_iso).date()
    except (TypeError, ValueError):
        return None
    return (d_new - d_old).days


def _is_next_week_back(newer_week, older_week):
    """True if older_week is exactly the calendar week right before newer_week."""
    diff = _weeks_apart(newer_week.get("week_start"), older_week.get("week_start"))
    return diff == 7


def _direction(outcome):
    """'good'/'bad' -> 'positive'/'negative'; 'neutral' stays 'neutral' (a
    real, present-this-week result that just isn't good or bad news) so
    _walk_streak can tell it apart from None (no data at all -- the test
    simply wasn't run that week)."""
    return outcomes.streak_direction(outcome) or "neutral"


# ---------------------------------------------------------------------------
# Per-metric weekly status functions — thin wrappers that pull the relevant
# label out of a week's stored result JSON and hand it to app/outcomes.py.
# Each returns "positive", "negative", "neutral", or None:
#   None     = this test wasn't logged at all that week (safe to look past,
#              to find the most recent week that actually has data).
#   "neutral"= the test WAS logged, but the outcome isn't good or bad news
#              (e.g. an intentional surplus while bulking). This must NOT be
#              treated like "no data" -- it firmly ends any streak as of
#              that week, the same as an opposite-direction result would.
# ---------------------------------------------------------------------------
def _status_workout(week, goal):
    er = week.get("exercise_result_json")
    if not er:
        return None
    return _direction(outcomes.exercise_outcome(er.get("label"), goal))


def _status_eating(week, goal):
    cr = week.get("calorie_result_json")
    if not cr:
        return None
    return _direction(outcomes.calorie_outcome(cr.get("label"), goal))


def _status_bmi(week, goal):
    br = week.get("bmi_result_json")
    if not br:
        return None
    return _direction(outcomes.bmi_outcome(br.get("label"), goal))


def _status_goal(week, goal):
    fr = week.get("fused_result_json")
    if not fr:
        return None
    return _direction(outcomes.archetype_outcome(fr.get("archetype"), goal))


def _status_group_untrained(week, group):
    """'negative' if this muscle group got zero sets that week, 'positive'
    if it was trained, None if the exercise test wasn't logged/scored that
    week. (Not goal-dependent — a missed muscle group is a missed muscle
    group regardless of what you're training for.)"""
    er = week.get("exercise_result_json")
    if not er:
        return None
    gs = er.get("group_scores")
    if gs is None or group not in gs:
        return None
    return "negative" if gs.get(group, 0) == 0.0 else "positive"


_METRICS = [
    ("workout", "Consistent training", "Inconsistent training", _status_workout),
    ("eating", "Eating on target", "Eating off target", _status_eating),
    ("bmi", "Healthy BMI", "BMI drifting off", _status_bmi),
    ("goal", "On track for your goal", "Off track from your goal", _status_goal),
]

_MESSAGES = {
    ("workout", "positive"): "{count} weeks in a row of balanced, well-rounded training.",
    ("workout", "negative"): "{count} weeks in a row of over- or under-training — dial in your volume.",
    ("eating", "positive"): "{count} weeks in a row eating in a way that matches your goal.",
    ("eating", "negative"): "{count} weeks in a row eating in a way that works against your goal.",
    ("bmi", "positive"): "{count} weeks in a row with a BMI that matches your goal.",
    ("bmi", "negative"): "{count} weeks in a row with a BMI that works against your goal.",
    ("goal", "positive"): "{count} weeks in a row trending toward your goal.",
    ("goal", "negative"): "{count} weeks in a row trending away from your goal.",
}


def _walk_streak(weeks, status_fn):
    """
    Given weeks ordered most-recent-first and a status_fn(week) ->
    'positive'|'negative'|'neutral'|None, return (direction, count) for the
    CURRENT streak (i.e. the one ending at the most recent week that
    actually has data for this metric), or None if there's no data or no
    current streak.

    Only a true "no data" week (None -- the test wasn't logged at all) is
    skipped while searching for where the current streak would start from.
    A "neutral" week is real data and must NOT be skipped past: if the most
    recent week with data is neutral, there is no current streak for this
    metric, full stop -- we don't reach back further in time and report an
    old, since-broken streak as if it were still active.
    """
    idx = 0
    while idx < len(weeks) and status_fn(weeks[idx]) is None:
        idx += 1
    if idx >= len(weeks):
        return None

    current_direction = status_fn(weeks[idx])
    if current_direction == "neutral":
        return None  # most recent applicable week is neutral -> no active streak

    count = 1
    j = idx + 1
    while j < len(weeks):
        s = status_fn(weeks[j])
        if s != current_direction:
            break
        if not _is_next_week_back(weeks[j - 1], weeks[j]):
            break
        count += 1
        j += 1

    if count < 2:
        return None
    return (current_direction, count)


def compute_weekly_streaks(user, weeks):
    """
    `weeks` = one row per distinct logged week, most-recent first (as
    returned by db.database.get_weeks_for_user). Returns a list of streak
    dicts sorted positive-first then by length descending:
        {"key", "direction", "count", "label", "message"}
    """
    if not weeks:
        return []

    goal = (user or {}).get("body_goal", "maintain")
    out = []

    for key, good_label, bad_label, status_fn in _METRICS:
        result = _walk_streak(weeks, lambda w, f=status_fn: f(w, goal))
        if result is None:
            continue
        direction, count = result
        label = good_label if direction == "positive" else bad_label
        out.append({
            "key": key,
            "direction": direction,
            "count": count,
            "label": label,
            "message": _MESSAGES[(key, direction)].format(count=count),
        })

    # Negative-only: muscle groups missed for consecutive weeks.
    for group in config.EXERCISE_GROUPS:
        result = _walk_streak(weeks, lambda w, g=group: _status_group_untrained(w, g))
        if result is None:
            continue
        direction, count = result
        if direction != "negative":
            continue  # "trained every week" isn't tracked per-group, only misses are
        out.append({
            "key": f"group_{group.lower()}",
            "direction": "negative",
            "count": count,
            "label": f"{group} untrained",
            "message": f"{group} has had no sets logged for {count} weeks in a row.",
        })

    out.sort(key=lambda s: (s["direction"] != "positive", -s["count"]))
    return out
