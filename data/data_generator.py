"""
data/data_generator.py — synthesize one wide CSV (data/raw/fused_logs.csv)
holding, per synthetic user-week, all 44 exercise volumes + BMI/BodyFat/
Calorie inputs + the ground-truth labels for all 4 branches and the fused
archetype. This single file is the row-level source of truth; model/dataset.py
later slices it into branch-specific train/val/test CSVs.

Extended with more diverse personas, realistic body-composition co-variance,
age-stratified profiles, seasonal variation, and edge cases.
"""

import os
import sys
import csv
import random
import math

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402

# ---------------------------------------------------------------------------
# Extended training style sub-types within each persona
# ---------------------------------------------------------------------------
# Each sub-type biases which muscle groups get the most volume.
_SUBTYPE_BIAS = {
    # (group -> relative multiplier adjustment)
    "push_focused":   {"Chest": 1.4, "Shoulder": 1.3, "Triceps": 1.3, "Biceps": 0.6, "Hamstrings": 0.7},
    "pull_focused":   {"Biceps": 1.4, "Shoulder": 1.2, "Chest": 0.7, "Triceps": 0.7},
    "legs_focused":   {"Quads": 1.6, "Hamstrings": 1.4, "Calves": 1.5, "Chest": 0.7},
    "cardio_heavy":   {"Cardio": 1.5, "Abs": 1.2, "Quads": 0.8},
    "upper_only":     {"Chest": 1.3, "Shoulder": 1.3, "Biceps": 1.3, "Triceps": 1.3,
                       "Quads": 0.2, "Hamstrings": 0.2, "Calves": 0.2},
    "lower_only":     {"Quads": 1.6, "Hamstrings": 1.5, "Calves": 1.4,
                       "Chest": 0.2, "Shoulder": 0.3, "Biceps": 0.2, "Triceps": 0.2},
    "balanced":       {},  # no bias
    "calisthenics":   {"Chest": 1.2, "Abs": 1.5, "Shoulder": 1.1, "Cardio": 1.3},
    "powerlifter":    {"Quads": 1.5, "Hamstrings": 1.3, "Chest": 1.3, "Shoulder": 0.9, "Cardio": 0.3},
    "beginner":       {g: 0.5 for g in config.EXERCISE_GROUPS},  # 50% of all baselines
}

_SUBTYPES_BY_PERSONA = {
    "obese_sedentary":  ["beginner", "cardio_heavy", "upper_only"],
    "buff_muscular":    ["push_focused", "pull_focused", "balanced", "powerlifter"],
    "skinny_athlete":   ["cardio_heavy", "calisthenics", "balanced"],
    "average_balanced": ["balanced", "push_focused", "pull_focused", "legs_focused"],
    "endurance_focused":["cardio_heavy", "lower_only", "balanced"],
}


# ---------------------------------------------------------------------------
# Per-persona multipliers on each exercise group's baseline (strength vs cardio)
#
# Cardio's group baseline is now small (5 total -- see config.EXERCISES), so
# these multipliers are tuned against that scale directly:
#   - Default/strength-oriented personas land around 2-4 cardio sessions/week
#     (buff_muscular, average_balanced) -- cardio is not their priority.
#   - Personas that genuinely benefit most from cardio -- obese_sedentary
#     (fat-loss priority), skinny_athlete, and endurance_focused -- land
#     around 5-6 sessions/week instead.
# skinny_athlete's own WEIGHT-training multiplier is deliberately kept well
# below buff_muscular's: a lean, endurance-oriented build doesn't call for
# heavy resistance volume to stay consistent with its archetype.
# ---------------------------------------------------------------------------
def _group_multiplier(persona, group, subtype="balanced"):
    is_cardio = (group == "Cardio")
    if persona == "obese_sedentary":
        # Still minimal resistance work, but cardio is the priority lever
        # for fat loss -- targets ~5-6 sessions/week against baseline 5.
        base = random.uniform(0.90, 1.30) if is_cardio else random.uniform(0.05, 0.25)
    elif persona == "buff_muscular":
        base = random.uniform(0.55, 0.85) if is_cardio else random.uniform(1.10, 1.70)
    elif persona == "skinny_athlete":
        # Cardio-first, not weight-training-first: no need for "extreme"
        # resistance volume to match this archetype. Base range is tuned a
        # bit below the 5-6 session target since this persona's subtypes
        # (cardio_heavy, calisthenics) both bias Cardio upward on top of it.
        base = random.uniform(0.75, 1.05) if is_cardio else random.uniform(0.35, 0.65)
    elif persona == "average_balanced":
        base = random.uniform(0.60, 0.90) if is_cardio else random.uniform(0.70, 1.30)
    elif persona == "endurance_focused":
        # Same idea: this persona's cardio_heavy subtype already pushes
        # cardio up, so the base range sits a bit below the 5-6 target.
        base = random.uniform(0.80, 1.05) if is_cardio else random.uniform(0.30, 0.60)
    else:
        base = 1.0

    # Apply sub-type bias
    bias = _SUBTYPE_BIAS.get(subtype, {})
    return base * bias.get(group, 1.0)


def _target_bmi(persona):
    return {
        "obese_sedentary": random.uniform(32, 40),
        "buff_muscular": random.uniform(26, 30),
        "skinny_athlete": random.uniform(19, 22),
        "average_balanced": random.uniform(22, 25),
        "endurance_focused": random.uniform(19, 23),
    }[persona]


def _target_bodyfat(persona, gender):
    base = {
        "obese_sedentary": random.uniform(30, 40),
        "buff_muscular": random.uniform(10, 16),
        "skinny_athlete": random.uniform(8, 14),
        "average_balanced": random.uniform(18, 25),
        "endurance_focused": random.uniform(10, 15),
    }[persona]
    if gender == "female":
        base += random.uniform(6, 9)
    return base


def _activity_level(persona):
    choices = {
        "obese_sedentary": ["sedentary", "light"],
        "buff_muscular": ["moderate", "active"],
        "skinny_athlete": ["active", "very_active"],
        "average_balanced": ["light", "moderate"],
        "endurance_focused": ["active", "very_active"],
    }[persona]
    return random.choice(choices)


def _activity_name_to_id(name):
    for k, v in config.ACTIVITY_LEVELS.items():
        if v == name:
            return k
    return 0


# ---------------------------------------------------------------------------
# Goal assignment — deliberately NOT a 1:1 mirror of persona. Real users at
# any current body state can be pursuing any goal (an obese_sedentary person
# trying to gain_muscle while still cutting, a buff_muscular person just
# trying to maintain, etc). Each persona has a realistic *lean* toward the
# "obvious" goal, but a meaningful share of every persona pursues each of the
# other 3 goals too, so goal ends up a genuinely independent training signal
# rather than a proxy for persona the model could shortcut around.
# ---------------------------------------------------------------------------
_GOAL_AFFINITY = {
    "obese_sedentary":   {"lose_fat": 0.55, "maintain": 0.20, "improve_endurance": 0.15, "gain_muscle": 0.10},
    "buff_muscular":     {"gain_muscle": 0.45, "maintain": 0.30, "improve_endurance": 0.15, "lose_fat": 0.10},
    "skinny_athlete":    {"gain_muscle": 0.35, "improve_endurance": 0.30, "maintain": 0.20, "lose_fat": 0.15},
    "average_balanced":  {"maintain": 0.35, "lose_fat": 0.25, "gain_muscle": 0.20, "improve_endurance": 0.20},
    "endurance_focused": {"improve_endurance": 0.45, "maintain": 0.25, "lose_fat": 0.15, "gain_muscle": 0.15},
}


def _assign_goal(persona):
    affinities = _GOAL_AFFINITY[persona]
    goals, weights = zip(*affinities.items())
    return random.choices(goals, weights=weights, k=1)[0]


def _mifflin_target(weight_kg, height_cm, age, gender, activity_name):
    """Mifflin-St Jeor BMR * activity multiplier."""
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    mult = config.ACTIVITY_MULTIPLIERS[_activity_name_to_id(activity_name)]
    return bmr * mult


def _bmi_band(bmi):
    if bmi < 18.5:
        return 0
    if bmi < 25:
        return 1
    if bmi < 30:
        return 2
    return 3


def _bodyfat_band(bf_pct, gender):
    cuts = config.BODYFAT_CUTOFFS_MALE if gender == "male" else config.BODYFAT_CUTOFFS_FEMALE
    # bands: 0 Essential, 1 Athletic, 2 Fitness, 3 Average, 4 Obese
    if bf_pct < cuts[0]:
        return 0
    if bf_pct < cuts[1]:
        return 1
    if bf_pct < cuts[2]:
        return 2
    if bf_pct < cuts[3]:
        return 3
    return 4


def _calorie_band(current_intake, target):
    if current_intake < target * 0.9:
        return 0
    if current_intake <= target * 1.1:
        return 1
    return 2


def _persona_intake(persona, target):
    if persona == "obese_sedentary":
        return target * random.uniform(1.15, 1.30)
    if persona == "buff_muscular":
        return target * random.uniform(0.95, 1.12)
    if persona in ("skinny_athlete", "endurance_focused"):
        return target * random.uniform(0.85, 1.02)
    return target * random.uniform(0.92, 1.08)  # average_balanced


def _maybe_null(value):
    return None if random.random() < config.NULL_RATE else value


def _group_total_sets(persona, group):
    """
    Generate a true total-sets value for a whole muscle group in one week.
    Baseline = sum of member exercise baselines * persona multiplier.
    """
    group_baseline = config.EXERCISE_GROUP_BASELINES[group]
    mult = _group_multiplier(persona, group)
    val = group_baseline * mult * random.gauss(1.0, 0.15)
    return max(0.0, round(val, 1))


# ---------------------------------------------------------------------------
# Seasonal variation — simulate year-round training fluctuation (e.g. less
# gym in summer months, higher motivation in Jan, lower in Aug).
# ---------------------------------------------------------------------------
_SEASON_MULT = {
    "peak":    1.15,   # Jan new-year, Sep back-to-gym
    "normal":  1.00,
    "low":     0.80,   # Jul-Aug summer drop
    "holiday": 0.70,   # Dec holiday season
}

def _season_mult(week_in_year):
    """Return a training-volume multiplier based on approximate week of year."""
    if 1 <= week_in_year <= 6:         return _SEASON_MULT["peak"]
    elif 7 <= week_in_year <= 32:      return _SEASON_MULT["normal"]
    elif 33 <= week_in_year <= 40:     return _SEASON_MULT["low"]
    elif 36 <= week_in_year <= 40:     return _SEASON_MULT["peak"]   # Sep
    elif 49 <= week_in_year <= 52:     return _SEASON_MULT["holiday"]
    return _SEASON_MULT["normal"]


def _group_total_sets_full(persona, group, subtype="balanced", season_mult=1.0):
    """Generate weekly set total for a group with subtype bias + seasonal noise."""
    group_baseline = config.EXERCISE_GROUP_BASELINES[group]
    mult = _group_multiplier(persona, group, subtype)
    noise = random.gauss(1.0, 0.12)           # ±12% individual weekly noise
    val = group_baseline * mult * noise * season_mult
    return max(0.0, round(val, 1))


# ---------------------------------------------------------------------------
# Edge-case personas injected at fixed rates for training robustness
# ---------------------------------------------------------------------------
_EDGE_CASES = [
    # (persona, gender, age, bmi_override, bf_override)
    ("obese_sedentary", "male",   45, 42.0,  38.0),  # extreme obesity
    ("skinny_athlete",  "female", 22,  17.0,   9.0),  # underweight athlete
    ("buff_muscular",   "male",   30, 29.0,   8.0),   # high BMI, low fat
    ("average_balanced","female", 55, 23.5,  28.0),  # older woman healthy
    ("endurance_focused","male",  28, 20.0,   7.5),  # marathon runner lean
    ("obese_sedentary", "female", 38, 35.5,  42.0),  # obese woman
    ("average_balanced","male",   19, 21.0,  12.0),  # young baseline
    ("buff_muscular",   "female", 26, 24.0,  18.0),  # muscular woman
    ("skinny_athlete",  "male",   33, 18.2,  10.0),  # borderline underweight
    ("endurance_focused","female",40, 21.5,  14.0),  # masters runner
]


def generate():
    random.seed(config.RANDOM_SEED)
    os.makedirs(config.RAW_DIR, exist_ok=True)

    # Column order for the wide CSV
    group_cols = [f"group_{g.lower()}_sets" for g in config.EXERCISE_GROUPS]
    fieldnames = (
        ["user_id", "week_id", "persona", "subtype", "gender", "age", "goal",
         "week_of_year", "season_mult"]
        + group_cols
        + ["height_cm", "weight_kg", "neck_cm", "waist_cm", "hip_cm",
           "activity_level", "current_intake"]
        + ["exercise_adequacy_label", "bmi_band_label", "bodyfat_band_label",
           "calorie_band_label", "archetype_label"]
    )

    rows = []

    # ---- Main synthetic population ----
    for user_id in range(1, config.NUM_SYNTHETIC_USERS + 1):
        gender  = random.choice(["male", "female"])
        persona = random.choice(config.PERSONAS)
        subtype = random.choice(_SUBTYPES_BY_PERSONA[persona])
        age     = max(16, min(70, int(random.gauss(32, 10))))
        goal    = _assign_goal(persona)  # constant for this user across all their weeks
        start_week = random.randint(1, 52)         # random start in year

        n_weeks = random.randint(4, 12)            # more weeks per user
        for week_offset in range(n_weeks):
            week_in_year = ((start_week + week_offset - 1) % 52) + 1
            s_mult = _season_mult(week_in_year)

            # Progressive overload trend: slight volume increase week over week
            progression = 1.0 + week_offset * random.uniform(0.005, 0.015)

            # ---- group-level set totals ----
            true_group_sets = {
                g: _group_total_sets_full(persona, g, subtype, s_mult * progression)
                for g in config.EXERCISE_GROUPS
            }

            # ---- BMI inputs ----
            height_cm = random.gauss(175 if gender == "male" else 162, 8)
            height_m  = height_cm / 100.0
            target_bmi = _target_bmi(persona)
            weight_kg  = target_bmi * (height_m ** 2) + random.gauss(0, 2.0)
            weight_kg  = max(35.0, weight_kg)
            # Slight weight drift week-to-week
            weight_kg += week_offset * random.gauss(-0.1, 0.3)
            weight_kg  = max(35.0, weight_kg)
            true_bmi   = weight_kg / (height_m ** 2)

            # ---- body fat inputs ----
            true_bf = _target_bodyfat(persona, gender)
            waist_cm = 70 + true_bf * random.uniform(1.3, 1.9)
            neck_cm  = (40 if gender == "male" else 34) + random.gauss(0, 2.5)
            neck_cm  = max(25.0, neck_cm)
            hip_cm   = None
            if gender == "female":
                hip_cm = 90 + true_bf * random.uniform(0.5, 1.0)

            # ---- calorie inputs ----
            activity_name  = _activity_level(persona)
            target_cal     = _mifflin_target(weight_kg, height_cm, age, gender, activity_name)
            current_intake = _persona_intake(persona, target_cal)

            # ---- labels ----
            mean_ratio = sum(
                true_group_sets[g] / config.EXERCISE_GROUP_BASELINES[g]
                for g in config.EXERCISE_GROUPS
            ) / len(config.EXERCISE_GROUPS)
            exercise_label  = 0 if mean_ratio < 0.6 else (2 if mean_ratio > 1.3 else 1)
            bmi_label       = _bmi_band(true_bmi)
            bodyfat_label   = _bodyfat_band(true_bf, gender)
            calorie_label   = _calorie_band(current_intake, target_cal)
            archetype_label = config.PERSONA_TO_ARCHETYPE[persona]

            # ---- apply nulling AFTER labels ----
            group_sets_nulled = {g: _maybe_null(v) for g, v in true_group_sets.items()}
            height_out = _maybe_null(round(height_cm, 1))
            weight_out = _maybe_null(round(weight_kg, 1))
            neck_out   = _maybe_null(round(neck_cm, 1))
            waist_out  = _maybe_null(round(waist_cm, 1))
            hip_out    = (_maybe_null(round(hip_cm, 1)) if hip_cm is not None else None)
            intake_out = _maybe_null(round(current_intake, 0))

            row = {
                "user_id": user_id,
                "week_id": week_offset + 1,
                "persona": persona,
                "subtype": subtype,
                "gender": gender,
                "age": age,
                "goal": goal,
                "week_of_year": week_in_year,
                "season_mult": round(s_mult, 2),
                "height_cm":       "" if height_out is None else height_out,
                "weight_kg":       "" if weight_out is None else weight_out,
                "neck_cm":         "" if neck_out is None else neck_out,
                "waist_cm":        "" if waist_out is None else waist_out,
                "hip_cm":          "" if hip_out is None else hip_out,
                "activity_level":  activity_name,
                "current_intake":  "" if intake_out is None else intake_out,
                "exercise_adequacy_label": exercise_label,
                "bmi_band_label":          bmi_label,
                "bodyfat_band_label":      bodyfat_label,
                "calorie_band_label":      calorie_label,
                "archetype_label":         archetype_label,
            }
            for g in config.EXERCISE_GROUPS:
                v = group_sets_nulled[g]
                row[f"group_{g.lower()}_sets"] = "" if v is None else v
            rows.append(row)

    # ---- Edge-case rows (not nulled, fully specified) ----
    edge_uid = config.NUM_SYNTHETIC_USERS + 1
    for (ec_persona, ec_gender, ec_age, ec_bmi, ec_bf) in _EDGE_CASES:
        height_cm = 175.0 if ec_gender == "male" else 163.0
        height_m  = height_cm / 100.0
        weight_kg = ec_bmi * (height_m ** 2)
        waist_cm  = 70 + ec_bf * 1.6
        neck_cm   = 40.0 if ec_gender == "male" else 34.0
        hip_cm    = (90 + ec_bf * 0.75) if ec_gender == "female" else None
        activity_name  = _activity_level(ec_persona)
        target_cal     = _mifflin_target(weight_kg, height_cm, ec_age, ec_gender, activity_name)
        current_intake = _persona_intake(ec_persona, target_cal)
        subtype   = random.choice(_SUBTYPES_BY_PERSONA[ec_persona])
        ec_goal   = _assign_goal(ec_persona)

        true_group_sets = {g: _group_total_sets_full(ec_persona, g, subtype) for g in config.EXERCISE_GROUPS}
        mean_ratio = sum(true_group_sets[g] / config.EXERCISE_GROUP_BASELINES[g] for g in config.EXERCISE_GROUPS) / len(config.EXERCISE_GROUPS)

        row = {
            "user_id": edge_uid,
            "week_id": 1,
            "persona": ec_persona,
            "subtype": subtype,
            "gender": ec_gender,
            "age": ec_age,
            "goal": ec_goal,
            "week_of_year": 1,
            "season_mult": 1.0,
            "height_cm": round(height_cm, 1),
            "weight_kg": round(weight_kg, 1),
            "neck_cm": round(neck_cm, 1),
            "waist_cm": round(waist_cm, 1),
            "hip_cm": round(hip_cm, 1) if hip_cm else "",
            "activity_level": activity_name,
            "current_intake": round(current_intake, 0),
            "exercise_adequacy_label": 0 if mean_ratio < 0.6 else (2 if mean_ratio > 1.3 else 1),
            "bmi_band_label": _bmi_band(ec_bmi),
            "bodyfat_band_label": _bodyfat_band(ec_bf, ec_gender),
            "calorie_band_label": _calorie_band(current_intake, target_cal),
            "archetype_label": config.PERSONA_TO_ARCHETYPE[ec_persona],
        }
        for g in config.EXERCISE_GROUPS:
            row[f"group_{g.lower()}_sets"] = round(true_group_sets[g], 1)
        rows.append(row)
        edge_uid += 1

    with open(config.RAW_LOGS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    n_main  = len(rows) - len(_EDGE_CASES)
    n_edge  = len(_EDGE_CASES)
    n_users = config.NUM_SYNTHETIC_USERS + n_edge
    print(f"Generated {len(rows)} rows  ({n_main} main + {n_edge} edge cases, {n_users} users)")
    return len(rows)


if __name__ == "__main__":
    n = generate()
    print(f"Saved -> {config.RAW_LOGS_PATH}")
