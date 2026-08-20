"""
model/dataset.py

1. Read data/raw/fused_logs.csv into row-dicts (empty strings -> None).
2. Stratified 70/15/15 split by archetype_label; write full-column
   fusion_{train,val,test}.csv.
3. Write branch-specific column-subset CSVs for convenience.
4. Compute impute_stats.json from the TRAIN split only.

Plus PyTorch Dataset classes for each branch and the fusion model.
"""

import os
import sys
import csv
import random
import statistics

import torch
from torch.utils.data import Dataset

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402

# Columns that are numeric (empty string -> None, else float).
_NUMERIC_COLS = set(config.NULLABLE_NUMERIC_FIELDS) | {"age"}
_INT_LABEL_COLS = {
    "exercise_adequacy_label", "bmi_band_label", "bodyfat_band_label",
    "calorie_band_label", "archetype_label", "user_id", "week_id",
}


# ---------------------------------------------------------------------------
# 1. READ
# ---------------------------------------------------------------------------
def read_raw_rows(path=None):
    path = path or config.RAW_LOGS_PATH
    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {}
            for k, v in raw.items():
                if v == "" or v is None:
                    row[k] = None
                elif k in _INT_LABEL_COLS:
                    row[k] = int(v)
                elif k in _NUMERIC_COLS:
                    row[k] = float(v)
                else:
                    row[k] = v  # persona, gender, activity_level
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 2. STRATIFIED SPLIT
# ---------------------------------------------------------------------------
def stratified_split(rows, train=0.70, val=0.15, seed=config.RANDOM_SEED):
    by_label = {}
    for r in rows:
        by_label.setdefault(r["archetype_label"], []).append(r)

    rng = random.Random(seed)
    train_rows, val_rows, test_rows = [], [], []
    for label, group in by_label.items():
        group = list(group)
        rng.shuffle(group)
        n = len(group)
        n_train = int(n * train)
        n_val = int(n * val)
        train_rows += group[:n_train]
        val_rows += group[n_train:n_train + n_val]
        test_rows += group[n_train + n_val:]

    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    rng.shuffle(test_rows)
    return train_rows, val_rows, test_rows


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------
def _write_csv(path, rows, columns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def _exercise_columns():
    return (["user_id", "week_id", "goal"]
            + [f"group_{g.lower()}_sets" for g in config.EXERCISE_GROUPS]
            + ["exercise_adequacy_label"])


def _bmi_columns():
    return ["user_id", "week_id", "goal", "height_cm", "weight_kg", "age", "gender", "bmi_band_label"]


def _bodyfat_columns():
    return ["user_id", "week_id", "goal", "neck_cm", "waist_cm", "hip_cm", "gender", "bodyfat_band_label"]


def _calorie_columns():
    return ["user_id", "week_id", "goal", "activity_level", "current_intake", "calorie_band_label"]


# ---------------------------------------------------------------------------
# 4. IMPUTE STATS (train split only)
# ---------------------------------------------------------------------------
def compute_impute_stats(train_rows):
    numeric = {}
    for field in config.STATS_FIELDS:
        values = [r[field] for r in train_rows if r.get(field) is not None]
        if not values:
            numeric[field] = {"mean": 0.0, "std": 1.0}
            continue
        mean = statistics.mean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 1.0
        numeric[field] = {"mean": float(mean), "std": float(std)}
    return {"numeric": numeric}


def build_all():
    rows = read_raw_rows()
    train_rows, val_rows, test_rows = stratified_split(rows)

    all_cols = list(rows[0].keys())
    splits = {"train": train_rows, "val": val_rows, "test": test_rows}
    for name, split_rows in splits.items():
        _write_csv(os.path.join(config.PROCESSED_DIR, f"fusion_{name}.csv"), split_rows, all_cols)
        _write_csv(os.path.join(config.PROCESSED_DIR, f"exercise_{name}.csv"), split_rows, _exercise_columns())
        _write_csv(os.path.join(config.PROCESSED_DIR, f"bmi_{name}.csv"), split_rows, _bmi_columns())
        _write_csv(os.path.join(config.PROCESSED_DIR, f"bodyfat_{name}.csv"), split_rows, _bodyfat_columns())
        _write_csv(os.path.join(config.PROCESSED_DIR, f"calorie_{name}.csv"), split_rows, _calorie_columns())

    stats = compute_impute_stats(train_rows)
    config.save_impute_stats(stats)
    return len(train_rows), len(val_rows), len(test_rows)


# ---------------------------------------------------------------------------
# Helpers to turn a CSV row-dict into the raw dict each feature builder wants
# ---------------------------------------------------------------------------
def _activity_name_to_id(name):
    for k, v in config.ACTIVITY_LEVELS.items():
        if v == name:
            return k
    return 0


def row_to_exercise_raw(row):
    # Pass the pre-aggregated group keys directly; _compute_group_sets in
    # config.py recognises "group_<group_lower>_sets" and uses them as-is.
    return {f"group_{g.lower()}_sets": row.get(f"group_{g.lower()}_sets")
            for g in config.EXERCISE_GROUPS}


def row_to_bmi_raw(row):
    return {"height_cm": row.get("height_cm"), "weight_kg": row.get("weight_kg"),
            "age": row.get("age"), "gender": row.get("gender")}


def row_to_bodyfat_raw(row):
    return {"neck_cm": row.get("neck_cm"), "waist_cm": row.get("waist_cm"),
            "hip_cm": row.get("hip_cm"), "gender": row.get("gender")}


def row_to_calorie_raw(row):
    return {"activity_level": _activity_name_to_id(row.get("activity_level")),
            "current_intake": row.get("current_intake")}


# ---------------------------------------------------------------------------
# Dataset classes
# ---------------------------------------------------------------------------
class _BranchDataset(Dataset):
    def __init__(self, rows, stats, builder, raw_fn, label_col):
        self.rows = rows
        self.stats = stats
        self.builder = builder
        self.raw_fn = raw_fn
        self.label_col = label_col

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows[idx]
        raw = self.raw_fn(row)
        x = torch.tensor(self.builder(raw, self.stats, row.get("goal")), dtype=torch.float32)
        y = torch.tensor(int(row[self.label_col]), dtype=torch.long)
        return x, y


class ExerciseDataset(_BranchDataset):
    def __init__(self, rows, stats):
        super().__init__(rows, stats, config.build_feature_vector_exercise,
                         row_to_exercise_raw, "exercise_adequacy_label")


class BMIDataset(_BranchDataset):
    def __init__(self, rows, stats):
        super().__init__(rows, stats, config.build_feature_vector_bmi,
                         row_to_bmi_raw, "bmi_band_label")


class BodyFatDataset(_BranchDataset):
    def __init__(self, rows, stats):
        super().__init__(rows, stats, config.build_feature_vector_bodyfat,
                         row_to_bodyfat_raw, "bodyfat_band_label")


class CalorieDataset(_BranchDataset):
    def __init__(self, rows, stats):
        super().__init__(rows, stats, config.build_feature_vector_calories,
                         row_to_calorie_raw, "calorie_band_label")


class FusionDataset(Dataset):
    """
    Returns a dict of the 4 raw feature vectors (already run through the
    build_feature_vector_* functions) plus the archetype_label. train_fusion.py
    encodes each with the frozen branch encoders and applies modality dropout.
    """

    def __init__(self, rows, stats):
        self.rows = rows
        self.stats = stats

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows[idx]
        s = self.stats
        goal = row.get("goal")
        return {
            "exercise": torch.tensor(
                config.build_feature_vector_exercise(row_to_exercise_raw(row), s, goal),
                dtype=torch.float32),
            "bmi": torch.tensor(
                config.build_feature_vector_bmi(row_to_bmi_raw(row), s, goal),
                dtype=torch.float32),
            "bodyfat": torch.tensor(
                config.build_feature_vector_bodyfat(row_to_bodyfat_raw(row), s, goal),
                dtype=torch.float32),
            "calories": torch.tensor(
                config.build_feature_vector_calories(row_to_calorie_raw(row), s, goal),
                dtype=torch.float32),
            "goal_onehot": torch.tensor(config.goal_onehot(goal), dtype=torch.float32),
            "archetype_label": torch.tensor(int(row["archetype_label"]), dtype=torch.long),
        }


def load_split_rows(branch, split):
    """Read a processed split CSV back into typed row-dicts."""
    path = os.path.join(config.PROCESSED_DIR, f"{branch}_{split}.csv")
    return read_raw_rows(path)


if __name__ == "__main__":
    n_train, n_val, n_test = build_all()
    print(f"Split complete -> train={n_train}, val={n_val}, test={n_test}")
    print(f"Impute stats written to {config.IMPUTE_STATS_PATH}")
