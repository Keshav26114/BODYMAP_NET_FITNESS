"""
model/train_branches.py — train each of the 4 branch encoders with the same
parameterized loop (early stopping on val loss, checkpoint best model).
"""

import os
import sys

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from model import dataset as ds  # noqa: E402
from model.branches import (  # noqa: E402
    ExerciseEncoder, BMIEncoder, BodyFatEncoder, CalorieEncoder,
)

# branch key -> (Encoder class, Dataset class, split-file prefix, checkpoint path)
BRANCHES = {
    "exercise": (ExerciseEncoder, ds.ExerciseDataset, "exercise", config.EXERCISE_CKPT),
    "bmi": (BMIEncoder, ds.BMIDataset, "bmi", config.BMI_CKPT),
    "bodyfat": (BodyFatEncoder, ds.BodyFatDataset, "bodyfat", config.BODYFAT_CKPT),
    "calories": (CalorieEncoder, ds.CalorieDataset, "calorie", config.CALORIE_CKPT),
}


def _run_epoch(model, loader, loss_fn, optimizer=None):
    train_mode = optimizer is not None
    model.train(train_mode)
    total_loss, correct, count = 0.0, 0, 0
    torch.set_grad_enabled(train_mode)
    for x, y in loader:
        logits, _ = model(x)
        loss = loss_fn(logits, y)
        if train_mode:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        total_loss += loss.item() * x.size(0)
        correct += (logits.argmax(dim=1) == y).sum().item()
        count += x.size(0)
    torch.set_grad_enabled(True)
    return total_loss / max(count, 1), correct / max(count, 1)


def train_branch(branch_key):
    EncoderClass, DatasetClass, prefix, ckpt_path = BRANCHES[branch_key]
    stats = config.load_impute_stats()

    train_rows = ds.load_split_rows(prefix, "train")
    val_rows = ds.load_split_rows(prefix, "val")
    train_loader = DataLoader(DatasetClass(train_rows, stats),
                              batch_size=config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(DatasetClass(val_rows, stats),
                            batch_size=config.BATCH_SIZE, shuffle=False)

    torch.manual_seed(config.RANDOM_SEED)
    model = EncoderClass()
    loss_fn = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.LEARNING_RATE,
                                 weight_decay=config.WEIGHT_DECAY)

    best_val = float("inf")
    patience = 0
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    print(f"\n=== Training branch: {branch_key} ===")

    for epoch in range(config.MAX_EPOCHS):
        train_loss, _ = _run_epoch(model, train_loader, loss_fn, optimizer)
        val_loss, val_acc = _run_epoch(model, val_loader, loss_fn, optimizer=None)
        print(f"epoch {epoch:03d} | train_loss {train_loss:.4f} | "
              f"val_loss {val_loss:.4f} | val_acc {val_acc:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            patience = 0
            torch.save({"model_state_dict": model.state_dict(),
                        "epoch": epoch, "val_loss": val_loss}, ckpt_path)
        else:
            patience += 1
            if patience >= config.EARLY_STOPPING_PATIENCE:
                print(f"Early stopping at epoch {epoch}.")
                break

    print(f"Best val_loss for {branch_key}: {best_val:.4f}, checkpoint saved to {ckpt_path}")


if __name__ == "__main__":
    for key in ["exercise", "bmi", "bodyfat", "calories"]:
        train_branch(key)
