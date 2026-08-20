"""
app/inference.py — load all 5 checkpoints once at import time and expose
predict_* helpers plus form_to_raw_* converters used by the Flask routes.
"""

import os
import sys

import torch
import torch.nn.functional as F

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from model.branches import (  # noqa: E402
    ExerciseEncoder, BMIEncoder, BodyFatEncoder, CalorieEncoder, CHECKPOINT_PATHS,
)
from model.fusion import BodyMapNet  # noqa: E402

BRANCH_ORDER = BodyMapNet.BRANCH_ORDER

# ---------------------------------------------------------------------------
# Load models once at import time.
# ---------------------------------------------------------------------------
_STATS = None
_MODELS = {}
_FUSION = None
_LOADED = False


def _load_all():
    global _STATS, _MODELS, _FUSION, _LOADED
    if _LOADED:
        return
    _STATS = config.load_impute_stats()

    def _load(encoder_cls, path):
        m = encoder_cls()
        ckpt = torch.load(path, map_location="cpu")
        m.load_state_dict(ckpt["model_state_dict"])
        m.eval()
        return m

    _MODELS["exercise"] = _load(ExerciseEncoder, CHECKPOINT_PATHS["exercise"])
    _MODELS["bmi"] = _load(BMIEncoder, CHECKPOINT_PATHS["bmi"])
    _MODELS["bodyfat"] = _load(BodyFatEncoder, CHECKPOINT_PATHS["bodyfat"])
    _MODELS["calories"] = _load(CalorieEncoder, CHECKPOINT_PATHS["calories"])

    _FUSION = BodyMapNet()
    _FUSION.load_state_dict(torch.load(config.FUSION_CKPT, map_location="cpu")["model_state_dict"])
    _FUSION.eval()
    _LOADED = True


# Attempt eager load, but tolerate missing checkpoints (e.g. before training)
# so the module can still be imported for form conversion helpers.
try:
    _load_all()
except (FileNotFoundError, RuntimeError) as exc:  # pragma: no cover
    print(f"[inference] models not loaded yet: {exc}")


# ---------------------------------------------------------------------------
# Branch predictions
# ---------------------------------------------------------------------------
def _softmax_result(logits, vocab):
    probs = F.softmax(logits, dim=1).squeeze(0)
    idx = int(torch.argmax(probs).item())
    return vocab[idx], float(probs[idx].item())


def predict_exercise(raw_exercise_dict, goal=None):
    _load_all()
    vec = config.build_feature_vector_exercise(raw_exercise_dict, _STATS, goal)
    x = torch.tensor([vec], dtype=torch.float32)
    with torch.no_grad():
        logits, embedding = _MODELS["exercise"](x)
    label, conf = _softmax_result(logits, config.TRAINING_ADEQUACY)

    # group_scores: group total sets / group baseline (for the bar chart).
    group_totals = config._compute_group_sets(raw_exercise_dict)
    group_scores = {}
    for group in config.EXERCISE_GROUPS:
        total = group_totals.get(group)
        baseline = config.EXERCISE_GROUP_BASELINES.get(group, 1.0)
        group_scores[group] = (float(total) / baseline) if total is not None else 0.0

    return {"label": label, "confidence": conf, "embedding": embedding,
            "group_scores": group_scores}


def predict_bmi(raw_bmi_dict, goal=None):
    _load_all()
    vec = config.build_feature_vector_bmi(raw_bmi_dict, _STATS, goal)
    x = torch.tensor([vec], dtype=torch.float32)
    with torch.no_grad():
        logits, embedding = _MODELS["bmi"](x)
    label, conf = _softmax_result(logits, config.BMI_BANDS)

    bmi_value = None
    h = raw_bmi_dict.get("height_cm")
    w = raw_bmi_dict.get("weight_kg")
    if h and w and float(h) > 0:
        bmi_value = float(w) / ((float(h) / 100.0) ** 2)

    return {"label": label, "confidence": conf, "embedding": embedding,
            "bmi_value": bmi_value}


def predict_bodyfat(raw_bf_dict, goal=None):
    _load_all()
    vec = config.build_feature_vector_bodyfat(raw_bf_dict, _STATS, goal)
    x = torch.tensor([vec], dtype=torch.float32)
    with torch.no_grad():
        logits, embedding = _MODELS["bodyfat"](x)
    label, conf = _softmax_result(logits, config.BODYFAT_BANDS)

    # U.S. Navy body-fat % estimate, if enough measurements are present.
    import math
    bf_value = None
    neck = raw_bf_dict.get("neck_cm")
    waist = raw_bf_dict.get("waist_cm")
    hip = raw_bf_dict.get("hip_cm")
    is_male = raw_bf_dict.get("gender") == "male"
    height = raw_bf_dict.get("height_cm")
    try:
        if is_male and neck and waist and height:
            bf_value = 495 / (1.0324 - 0.19077 * math.log10(float(waist) - float(neck))
                              + 0.15456 * math.log10(float(height))) - 450
        elif (not is_male) and neck and waist and hip and height:
            bf_value = 495 / (1.29579 - 0.35004 * math.log10(float(waist) + float(hip) - float(neck))
                              + 0.22100 * math.log10(float(height))) - 450
    except (ValueError, ZeroDivisionError):
        bf_value = None

    return {"label": label, "confidence": conf, "embedding": embedding,
            "bodyfat_value": bf_value}


def predict_calories(raw_cal_dict, goal=None):
    _load_all()
    vec = config.build_feature_vector_calories(raw_cal_dict, _STATS, goal)
    x = torch.tensor([vec], dtype=torch.float32)
    with torch.no_grad():
        logits, embedding = _MODELS["calories"](x)
    label, conf = _softmax_result(logits, config.CALORIE_BANDS)
    return {"label": label, "confidence": conf, "embedding": embedding,
            "current_intake": raw_cal_dict.get("current_intake"),
            "target_intake": raw_cal_dict.get("target_intake")}


def predict_fused(available_embeddings, goal=None):
    """
    available_embeddings: {"exercise": tensor_or_None, "bmi": ..., ...}
    goal: the user's body_goal string (e.g. "gain_muscle") -- conditions the
    archetype head so the same body composition can be judged differently
    depending on what the person is training for.
    """
    _load_all()
    present_mask = {b: (available_embeddings.get(b) is not None) for b in BRANCH_ORDER}
    goal_onehot = torch.tensor([config.goal_onehot(goal)], dtype=torch.float32)
    with torch.no_grad():
        logits, embedding_2d, _ = _FUSION(available_embeddings, present_mask, goal_onehot)
    probs = F.softmax(logits, dim=1).squeeze(0)
    idx = int(torch.argmax(probs).item())
    xy = embedding_2d.squeeze(0).tolist()
    return {"archetype": config.ARCHETYPES[idx], "confidence": float(probs[idx].item()),
            "archetype_label": idx, "embedding_2d": [float(xy[0]), float(xy[1])]}


# ---------------------------------------------------------------------------
# Flask form -> raw dict converters
# ---------------------------------------------------------------------------
def _to_float_or_none(value):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def form_to_raw_exercise(form):
    """
    Collect per-exercise sets from the form (field name: ex_<exercise_id>).
    Returns a dict with "<exercise_id>_sets" keys so that config._compute_group_sets
    can aggregate them per muscle group.
    """
    raw = {}
    for ex_id in config.EXERCISE_IDS:
        raw[f"{ex_id}_sets"] = _to_float_or_none(form.get(f"ex_{ex_id}"))
    return raw


def form_to_raw_bmi(form, user):
    return {
        "height_cm": _to_float_or_none(form.get("bmi_height_cm")),
        "weight_kg": _to_float_or_none(form.get("bmi_weight_kg")),
        "age": user["age"],
        "gender": user["gender"],
    }


def form_to_raw_bodyfat(form, user):
    return {
        "neck_cm": _to_float_or_none(form.get("bf_neck_cm")),
        "waist_cm": _to_float_or_none(form.get("bf_waist_cm")),
        "hip_cm": _to_float_or_none(form.get("bf_hip_cm")),
        "height_cm": _to_float_or_none(form.get("bmi_height_cm")),
        "gender": user["gender"],
    }


def form_to_raw_calories(form, user):
    level_name = form.get("cal_activity_level", "moderate")
    level_id = 2
    for k, v in config.ACTIVITY_LEVELS.items():
        if v == level_name:
            level_id = k
            break
    return {
        "activity_level": level_id,
        "current_intake": _to_float_or_none(form.get("cal_current_intake")),
    }
