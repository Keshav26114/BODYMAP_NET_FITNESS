"""
model/evaluate.py — reload every checkpoint and report test-set metrics.

Per branch: accuracy + macro-F1 (implemented manually, no sklearn).
For fusion: accuracy while forcing exactly 1, 2, 3, then 4 branches present,
proving graceful degradation of the missing-token design.
"""

import os
import sys
import itertools

import torch
from torch.utils.data import DataLoader

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from model import dataset as ds  # noqa: E402
from model.branches import (  # noqa: E402
    ExerciseEncoder, BMIEncoder, BodyFatEncoder, CalorieEncoder,
    ENCODER_CLASSES, CHECKPOINT_PATHS,
)
from model.fusion import BodyMapNet  # noqa: E402

BRANCH_ORDER = BodyMapNet.BRANCH_ORDER


def macro_f1(y_true, y_pred, num_classes):
    """Manual macro-F1: per-class precision/recall/F1 averaged."""
    f1s = []
    for c in range(num_classes):
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def eval_branch(name, EncoderClass, DatasetClass, prefix, num_classes, stats):
    model = EncoderClass()
    ckpt = torch.load(CHECKPOINT_PATHS[name], map_location="cpu")
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    rows = ds.load_split_rows(prefix, "test")
    loader = DataLoader(DatasetClass(rows, stats), batch_size=config.BATCH_SIZE, shuffle=False)

    y_true, y_pred = [], []
    with torch.no_grad():
        for x, y in loader:
            logits, _ = model(x)
            preds = logits.argmax(dim=1)
            y_true += y.tolist()
            y_pred += preds.tolist()

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(len(y_true), 1)
    f1 = macro_f1(y_true, y_pred, num_classes)
    print(f"  {name:9s} | test_acc {acc:.4f} | macro_F1 {f1:.4f}")


def eval_fusion(stats):
    encoders = {}
    for branch, EncoderClass in ENCODER_CLASSES.items():
        m = EncoderClass()
        m.load_state_dict(torch.load(CHECKPOINT_PATHS[branch], map_location="cpu")["model_state_dict"])
        m.eval()
        encoders[branch] = m

    fusion = BodyMapNet()
    fusion.load_state_dict(torch.load(config.FUSION_CKPT, map_location="cpu")["model_state_dict"])
    fusion.eval()

    rows = ds.read_raw_rows(os.path.join(config.PROCESSED_DIR, "fusion_test.csv"))
    loader = DataLoader(ds.FusionDataset(rows, stats), batch_size=config.BATCH_SIZE, shuffle=False)

    # Precompute all embeddings + labels once.
    all_emb = {b: [] for b in BRANCH_ORDER}
    all_labels = []
    all_goal_onehot = []
    with torch.no_grad():
        for batch in loader:
            all_labels += batch["archetype_label"].tolist()
            all_goal_onehot.append(batch["goal_onehot"])
            for b in BRANCH_ORDER:
                _, emb = encoders[b](batch[b])
                all_emb[b].append(emb)
    emb_full = {b: torch.cat(all_emb[b], dim=0) for b in BRANCH_ORDER}
    labels = torch.tensor(all_labels)
    goal_onehot_full = torch.cat(all_goal_onehot, dim=0)

    print("  fusion graceful-degradation (accuracy by # branches present):")
    for k in range(1, 5):
        accs = []
        for present in itertools.combinations(BRANCH_ORDER, k):
            present_set = set(present)
            mask = {b: (b in present_set) for b in BRANCH_ORDER}
            with torch.no_grad():
                logits, _, _ = fusion(emb_full, mask, goal_onehot_full)
                preds = logits.argmax(dim=1)
            accs.append((preds == labels).float().mean().item())
        print(f"    {k} present | mean_acc {sum(accs) / len(accs):.4f} "
              f"(over {len(accs)} branch combos)")


def main():
    stats = config.load_impute_stats()
    print("Branch test metrics:")
    eval_branch("exercise", ExerciseEncoder, ds.ExerciseDataset, "exercise", 3, stats)
    eval_branch("bmi", BMIEncoder, ds.BMIDataset, "bmi", 4, stats)
    eval_branch("bodyfat", BodyFatEncoder, ds.BodyFatDataset, "bodyfat", 5, stats)
    eval_branch("calories", CalorieEncoder, ds.CalorieDataset, "calorie", 3, stats)
    print()
    eval_fusion(stats)


if __name__ == "__main__":
    main()
