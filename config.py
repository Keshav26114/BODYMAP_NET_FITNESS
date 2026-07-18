"""
config.py — single source of truth for BodyMap Net.

Every other module imports paths, catalogs, vocabularies, thresholds,
hyperparameters and feature-vector builders from here. Nothing else should
hard-code an exercise name, threshold, path or hyperparameter.
"""

import os
import json
import re

# ---------------------------------------------------------------------------
# 4.1  PATHS
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Used to sign Flask session cookies (login state). Override with a real
# secret via the BODYMAP_SECRET_KEY env var in any real deployment.
SECRET_KEY = os.environ.get("BODYMAP_SECRET_KEY", "bodymap-dev-secret-please-change")

DB_PATH = os.path.join(BASE_DIR, "db", "bodymap.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
RAW_LOGS_PATH = os.path.join(RAW_DIR, "fused_logs.csv")
IMPUTE_STATS_PATH = os.path.join(PROCESSED_DIR, "impute_stats.json")

CHECKPOINT_DIR = os.path.join(BASE_DIR, "model", "checkpoints")
EXERCISE_CKPT = os.path.join(CHECKPOINT_DIR, "exercise_branch.pt")
BMI_CKPT = os.path.join(CHECKPOINT_DIR, "bmi_branch.pt")
BODYFAT_CKPT = os.path.join(CHECKPOINT_DIR, "bodyfat_branch.pt")
CALORIE_CKPT = os.path.join(CHECKPOINT_DIR, "calorie_branch.pt")
FUSION_CKPT = os.path.join(CHECKPOINT_DIR, "fusion_model.pt")

# ---------------------------------------------------------------------------
# 4.2  EXERCISE CATALOG (44 exercises, 9 groups)
#
# "baseline" is the healthy WEEKLY target for that exercise, in "unit".
#
# For the 8 resistance-training groups (Shoulder, Chest, Triceps, Biceps,
# Abs, Quads, Hamstrings, Calves) baselines are calibrated so each GROUP's
# total sets/week lands in a realistic 12-36 range, in line with common
# strength-training guidance (~10-20 working sets/muscle/week to maintain
# or grow, up to ~25-36 for advanced/high-frequency training). Anything the
# user logs well above that per week is a genuine overtraining signal, and
# this is exactly the range the front-end real-time indicator (validators.js)
# is tuned against.
#
# Cardio is deliberately kept on the SAME small "sessions/week" scale as the
# other 8 groups (baseline 1 per activity, ~5 total) rather than raw
# minutes. A previous version used minute-based baselines (~150-300
# min/week, summing to 200) that the UI still labelled and totalled as
# generic "sets" -- so a perfectly normal cardio week could display as e.g.
# "202 sets" and read as an impossible number. Small whole-session counts
# keep Cardio comparable to every other group (and to the front-end's
# generic "sets" counter and step=1 inputs) while still being usable in the
# same 9-group average behind the Under/Balanced/Over-training call.
# ---------------------------------------------------------------------------
EXERCISES = [
    {"id": "overhead_press", "name": "Overhead Press", "group": "Shoulder", "unit": "sets", "baseline": 3},
    {"id": "lateral_raise", "name": "Lateral Raise", "group": "Shoulder", "unit": "sets", "baseline": 4},
    {"id": "rear_delt_fly", "name": "Rear Delt Fly", "group": "Shoulder", "unit": "sets", "baseline": 4},
    {"id": "arnold_press", "name": "Arnold Press", "group": "Shoulder", "unit": "sets", "baseline": 3},
    {"id": "front_raise", "name": "Front Raise", "group": "Shoulder", "unit": "sets", "baseline": 4},

    {"id": "bench_press", "name": "Bench Press", "group": "Chest", "unit": "sets", "baseline": 4},
    {"id": "incline_db_press", "name": "Incline Dumbbell Press", "group": "Chest", "unit": "sets", "baseline": 4},
    {"id": "chest_fly", "name": "Chest Fly", "group": "Chest", "unit": "sets", "baseline": 4},
    {"id": "pushups", "name": "Push-Ups", "group": "Chest", "unit": "sets", "baseline": 6},
    {"id": "cable_crossover", "name": "Cable Crossover", "group": "Chest", "unit": "sets", "baseline": 4},

    {"id": "tricep_pushdown", "name": "Tricep Pushdown", "group": "Triceps", "unit": "sets", "baseline": 3},
    {"id": "skull_crushers", "name": "Skull Crushers", "group": "Triceps", "unit": "sets", "baseline": 3},
    {"id": "overhead_tricep_ext", "name": "Overhead Tricep Extension", "group": "Triceps", "unit": "sets", "baseline": 3},
    {"id": "close_grip_bench", "name": "Close-Grip Bench Press", "group": "Triceps", "unit": "sets", "baseline": 3},
    {"id": "dips", "name": "Dips", "group": "Triceps", "unit": "sets", "baseline": 3},

    {"id": "barbell_curl", "name": "Barbell Curl", "group": "Biceps", "unit": "sets", "baseline": 3},
    {"id": "hammer_curl", "name": "Hammer Curl", "group": "Biceps", "unit": "sets", "baseline": 3},
    {"id": "concentration_curl", "name": "Concentration Curl", "group": "Biceps", "unit": "sets", "baseline": 3},
    {"id": "preacher_curl", "name": "Preacher Curl", "group": "Biceps", "unit": "sets", "baseline": 3},
    {"id": "cable_curl", "name": "Cable Curl", "group": "Biceps", "unit": "sets", "baseline": 3},

    {"id": "crunches", "name": "Crunches", "group": "Abs", "unit": "sets", "baseline": 3},
    {"id": "plank", "name": "Plank", "group": "Abs", "unit": "sets", "baseline": 10},
    {"id": "hanging_leg_raise", "name": "Hanging Leg Raise", "group": "Abs", "unit": "sets", "baseline": 2},
    {"id": "cable_crunch", "name": "Cable Crunch", "group": "Abs", "unit": "sets", "baseline": 2},
    {"id": "russian_twist", "name": "Russian Twist", "group": "Abs", "unit": "sets", "baseline": 3},

    {"id": "squat", "name": "Squat", "group": "Quads", "unit": "sets", "baseline": 5},
    {"id": "leg_press", "name": "Leg Press", "group": "Quads", "unit": "sets", "baseline": 7},
    {"id": "leg_extension", "name": "Leg Extension", "group": "Quads", "unit": "sets", "baseline": 5},
    {"id": "walking_lunges", "name": "Walking Lunges", "group": "Quads", "unit": "sets", "baseline": 4},
    {"id": "bulgarian_split_squat", "name": "Bulgarian Split Squat", "group": "Quads", "unit": "sets", "baseline": 3},

    {"id": "leg_curl", "name": "Leg Curl", "group": "Hamstrings", "unit": "sets", "baseline": 5},
    {"id": "romanian_deadlift", "name": "Romanian Deadlift", "group": "Hamstrings", "unit": "sets", "baseline": 3},
    {"id": "good_morning", "name": "Good Morning", "group": "Hamstrings", "unit": "sets", "baseline": 3},
    {"id": "glute_ham_raise", "name": "Glute Ham Raise", "group": "Hamstrings", "unit": "sets", "baseline": 2},
    {"id": "stiff_leg_deadlift", "name": "Stiff-Leg Deadlift", "group": "Hamstrings", "unit": "sets", "baseline": 3},

    {"id": "standing_calf_raise", "name": "Standing Calf Raise", "group": "Calves", "unit": "sets", "baseline": 6},
    {"id": "seated_calf_raise", "name": "Seated Calf Raise", "group": "Calves", "unit": "sets", "baseline": 5},
    {"id": "leg_press_calf_push", "name": "Leg Press Calf Push", "group": "Calves", "unit": "sets", "baseline": 4},
    {"id": "jump_rope", "name": "Jump Rope", "group": "Calves", "unit": "sets", "baseline": 1},

    {"id": "running", "name": "Running", "group": "Cardio", "unit": "sessions", "baseline": 1},
    {"id": "cycling", "name": "Cycling", "group": "Cardio", "unit": "sessions", "baseline": 1},
    {"id": "rowing_machine", "name": "Rowing Machine", "group": "Cardio", "unit": "sessions", "baseline": 1},
    {"id": "stair_climber", "name": "Stair Climber", "group": "Cardio", "unit": "sessions", "baseline": 1},
    {"id": "swimming", "name": "Swimming", "group": "Cardio", "unit": "sessions", "baseline": 1},
]

# Order matters — it fixes the neural network's input layout.
EXERCISE_IDS = [e["id"] for e in EXERCISES]

# 9 group names, in the order first seen above.
EXERCISE_GROUPS = []
for _e in EXERCISES:
    if _e["group"] not in EXERCISE_GROUPS:
        EXERCISE_GROUPS.append(_e["group"])

# id -> catalog entry, for quick lookup.
EXERCISE_BY_ID = {e["id"]: e for e in EXERCISES}

# ---------------------------------------------------------------------------
# 4.3  LABEL VOCABULARIES
# ---------------------------------------------------------------------------
TRAINING_ADEQUACY = {0: "Under-training", 1: "Balanced", 2: "Over-training"}
BMI_BANDS = {0: "Underweight", 1: "Normal", 2: "Overweight", 3: "Obese"}
BODYFAT_BANDS = {0: "Essential", 1: "Athletic", 2: "Fitness", 3: "Average", 4: "Obese"}
CALORIE_BANDS = {0: "Under-eating", 1: "On-target", 2: "Over-eating"}
ARCHETYPES = {0: "Obesity Risk", 1: "Buff / Muscular", 2: "Skinny Athlete",
              3: "Average / Balanced", 4: "Endurance-Focused"}
BODY_GOALS = {0: "lose_fat", 1: "gain_muscle", 2: "maintain", 3: "improve_endurance"}
GOAL_IDS = {v: k for k, v in BODY_GOALS.items()}  # name -> id, inverse of BODY_GOALS
ACTIVITY_LEVELS = {0: "sedentary", 1: "light", 2: "moderate", 3: "active", 4: "very_active"}
ACTIVITY_MULTIPLIERS = {0: 1.2, 1: 1.375, 2: 1.55, 3: 1.725, 4: 1.9}  # Mifflin-St Jeor

# Persona name -> archetype label id (keeps fusion ground truth consistent).
PERSONAS = ["obese_sedentary", "buff_muscular", "skinny_athlete",
            "average_balanced", "endurance_focused"]
PERSONA_TO_ARCHETYPE = {
    "obese_sedentary": 0,
    "buff_muscular": 1,
    "skinny_athlete": 2,
    "average_balanced": 3,
    "endurance_focused": 4,
}

# Body-fat % cutoffs (ACE-style). Upper bound of each band, exclusive of next.
# Bands: 0 Essential, 1 Athletic, 2 Fitness, 3 Average, 4 Obese
BODYFAT_CUTOFFS_MALE = [6, 14, 18, 25]      # <6 Essential .. >=25 Obese
BODYFAT_CUTOFFS_FEMALE = [14, 21, 25, 32]   # <14 Essential .. >=32 Obese

# ---------------------------------------------------------------------------
# 4.4  MODEL HYPERPARAMETERS
# ---------------------------------------------------------------------------
EMBED_DIM = 16
NUM_ATTENTION_HEADS = 4
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-5
BATCH_SIZE = 32
MAX_EPOCHS = 150
EARLY_STOPPING_PATIENCE = 12
NULL_RATE = 0.15
RANDOM_SEED = 42
NUM_SYNTHETIC_USERS = 600

# ---------------------------------------------------------------------------
# 4.11  SHARED HELPERS  (defined before feature builders that use them)
# ---------------------------------------------------------------------------
def _zscore(value, mean, std):
    """Standard z-score with a numerically safe denominator."""
    return (value - mean) / max(std, 1e-8)


def goal_onehot(goal):
    """4-dim one-hot of body_goal, in BODY_GOALS id order. Unknown/None goal
    falls back to 'maintain' rather than an all-zero vector, so every branch
    model always sees a valid, fully-specified goal context."""
    vec = [0.0] * len(BODY_GOALS)
    gid = GOAL_IDS.get(goal, GOAL_IDS["maintain"])
    vec[gid] = 1.0
    return vec


def load_impute_stats():
    """Read impute_stats.json -> dict with a 'numeric' key."""
    with open(IMPUTE_STATS_PATH, "r") as f:
        return json.load(f)


def save_impute_stats(stats):
    """Write the impute stats dict to impute_stats.json."""
    os.makedirs(os.path.dirname(IMPUTE_STATS_PATH), exist_ok=True)
    with open(IMPUTE_STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)


def _norm_field(raw_value, field_name, stats):
    """
    Return (normalized_value, missing_flag) for a single nullable numeric
    field, imputing missing values with that field's train-set mean and
    z-scoring with the same field's mean/std.
    """
    numeric = stats["numeric"]
    mean = numeric[field_name]["mean"]
    std = numeric[field_name]["std"]
    if raw_value is None:
        return _zscore(mean, mean, std), 1.0  # imputed -> normalized 0.0
    return _zscore(float(raw_value), mean, std), 0.0

# ---------------------------------------------------------------------------
# 4.7  EXERCISE FEATURE VECTOR  (length 18 = 9 groups × 2)
#
# The UI collects SETS per exercise.  For each of the 9 muscle groups the
# total sets = sum of all exercises that belong to that group.
# Missing = the user left every exercise in the group blank.
# Feature vector: [group_total_norm, missing_flag] × 9  -> length 18.
# ---------------------------------------------------------------------------

# Per-group baseline total sets (sum of member exercise baselines from
# EXERCISES list above). Re-derived at import time so it stays in sync.
EXERCISE_GROUP_BASELINES = {}
for _e in EXERCISES:
    EXERCISE_GROUP_BASELINES[_e["group"]] = (
        EXERCISE_GROUP_BASELINES.get(_e["group"], 0) + _e["baseline"]
    )

# Stat field names for exercise are now per-group.
EXERCISE_GROUP_STAT_FIELDS = [f"group_{g.lower()}_sets" for g in EXERCISE_GROUPS]


def _compute_group_sets(raw_sets_dict):
    """
    Accepts two input styles:
      1. Per-exercise keys: "<exercise_id>_sets" -> float|None
         (used when the user fills in individual exercises on the web form)
      2. Pre-aggregated group keys: "group_<group_lower>_sets" -> float|None
         (used in processed CSV rows from the data generator)
    Returns dict: group_name -> total_sets (float) or None if no data.
    A group is present if at least one of its exercises has a non-None value,
    OR if its pre-aggregated group key has a non-None value.
    """
    group_totals = {}
    group_present = {}
    for ex in EXERCISES:
        g = ex["group"]
        val = raw_sets_dict.get(f"{ex['id']}_sets")
        if val is not None:
            group_totals[g] = group_totals.get(g, 0.0) + float(val)
            group_present[g] = True
        else:
            if g not in group_present:
                group_present[g] = False
    # Override with pre-aggregated keys when present (training data path).
    for g in EXERCISE_GROUPS:
        agg_key = f"group_{g.lower()}_sets"
        agg_val = raw_sets_dict.get(agg_key)
        if agg_val is not None:
            group_totals[g] = float(agg_val)
            group_present[g] = True
    result = {}
    for g in EXERCISE_GROUPS:
        if group_present.get(g, False):
            result[g] = group_totals.get(g, 0.0)
        else:
            result[g] = None
    return result


def build_feature_vector_exercise(raw, stats, goal=None):
    """
    `raw` maps "<exercise_id>_sets" -> float|None.
    For each of the 9 groups compute total sets, then [norm, missing_flag].
    Appends a 4-dim goal one-hot so the model can learn goal-specific
    volume expectations (e.g. what's "enough" differs for gain_muscle vs
    maintain). Returns a vector of length 18 + 4 = 22.
    """
    group_totals = _compute_group_sets(raw)
    vec = []
    for g in EXERCISE_GROUPS:
        field = f"group_{g.lower()}_sets"
        value = group_totals.get(g)
        norm, flag = _norm_field(value, field, stats)
        vec.extend([norm, flag])
    return vec + goal_onehot(goal)  # length 22

# ---------------------------------------------------------------------------
# 4.8  BMI FEATURE VECTOR  (length 6 + 4 goal = 10)
# ---------------------------------------------------------------------------
def build_feature_vector_bmi(raw, stats, goal=None):
    """
    Inputs: height_cm, weight_kg (nullable), age (always), gender (-> is_male).
    Output: [height_norm, height_missing, weight_norm, weight_missing,
             age_norm, is_male] + goal_onehot(4)  -> length 10.
    """
    height_norm, height_flag = _norm_field(raw.get("height_cm"), "height_cm", stats)
    weight_norm, weight_flag = _norm_field(raw.get("weight_kg"), "weight_kg", stats)
    age_norm, _ = _norm_field(raw.get("age"), "age", stats)
    is_male = 1.0 if raw.get("gender") == "male" else 0.0
    return [height_norm, height_flag, weight_norm, weight_flag, age_norm, is_male] + goal_onehot(goal)

# ---------------------------------------------------------------------------
# 4.9  BODY FAT FEATURE VECTOR  (length 7 + 4 goal = 11)
# ---------------------------------------------------------------------------
def build_feature_vector_bodyfat(raw, stats, goal=None):
    """
    Inputs: neck_cm, waist_cm, hip_cm (all nullable), is_male flag.
    Output: [neck_norm, neck_flag, waist_norm, waist_flag,
             hip_norm, hip_flag, is_male] + goal_onehot(4)  -> length 11.
    """
    neck_norm, neck_flag = _norm_field(raw.get("neck_cm"), "neck_cm", stats)
    waist_norm, waist_flag = _norm_field(raw.get("waist_cm"), "waist_cm", stats)
    hip_norm, hip_flag = _norm_field(raw.get("hip_cm"), "hip_cm", stats)
    is_male = 1.0 if raw.get("gender") == "male" else 0.0
    return [neck_norm, neck_flag, waist_norm, waist_flag, hip_norm, hip_flag, is_male] + goal_onehot(goal)

# ---------------------------------------------------------------------------
# 4.10  CALORIE FEATURE VECTOR  (length 7 + 4 goal = 11)
# ---------------------------------------------------------------------------
def build_feature_vector_calories(raw, stats, goal=None):
    """
    Inputs: activity_level (0-4 int, always present -> one-hot of 5),
            current_intake (nullable).
    Output: [onehot_0..4 (5), intake_norm, intake_missing] + goal_onehot(4)
            -> length 11.
    """
    onehot = [0.0] * 5
    level = raw.get("activity_level")
    if level is not None:
        level = int(level)
        if 0 <= level <= 4:
            onehot[level] = 1.0
    intake_norm, intake_flag = _norm_field(raw.get("current_intake"), "current_intake", stats)
    return onehot + [intake_norm, intake_flag] + goal_onehot(goal)

# ---------------------------------------------------------------------------
# FIELDS THAT NEED IMPUTE STATS  (every nullable numeric field, one place)
# Exercise branch now uses per-group totals (9 stat fields), not per-exercise volumes.
NULLABLE_NUMERIC_FIELDS = (
    EXERCISE_GROUP_STAT_FIELDS
    + ["height_cm", "weight_kg", "neck_cm", "waist_cm", "hip_cm", "current_intake"]
)

# `age` is always present but is still z-scored, so it needs stats too.
STATS_FIELDS = NULLABLE_NUMERIC_FIELDS + ["age"]

# ---------------------------------------------------------------------------
# PASSWORD POLICY
#
# Applied to every place a NEW password is set: user creation, admin
# creation, self password-change, and admin password-reset. Login itself
# never re-validates against this (an old account could predate the
# policy), only the act of *setting* a password does.
# ---------------------------------------------------------------------------
PASSWORD_MIN_LENGTH = 8
PASSWORD_SPECIAL_CHARS_HINT = "!@#$%^&*(),.?\":{}|<>_-+=~`[]/\\;'"
_PASSWORD_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")
_PASSWORD_UPPER_RE = re.compile(r"[A-Z]")
_PASSWORD_LOWER_RE = re.compile(r"[a-z]")


def validate_password_policy(password):
    """
    Returns (True, None) if `password` meets the site's password policy,
    else (False, "<reason a human can read>"). Policy: at least
    PASSWORD_MIN_LENGTH characters, at least one uppercase letter, at least
    one lowercase letter, and at least one special (non-alphanumeric)
    symbol. Checked server-side on every route that sets a new password --
    the live checklist in the browser (password_strength.js) is a
    convenience, not the actual enforcement.
    """
    password = password or ""
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
    if not _PASSWORD_UPPER_RE.search(password):
        return False, "Password must include at least one uppercase letter."
    if not _PASSWORD_LOWER_RE.search(password):
        return False, "Password must include at least one lowercase letter."
    if not _PASSWORD_SPECIAL_RE.search(password):
        return False, "Password must include at least one special symbol (e.g. ! @ # $ %)."
    return True, None
