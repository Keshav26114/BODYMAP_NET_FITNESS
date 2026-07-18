"""
model/train_fusion.py — train BodyMapNet on top of the frozen, trained branch
encoders, using modality dropout so it copes with any subset of tests.
"""

import os
import sys
import math
import random

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from model import dataset as ds  # noqa: E402
from model.branches import ENCODER_CLASSES, CHECKPOINT_PATHS  # noqa: E402
from model.fusion import BodyMapNet  # noqa: E402

BRANCH_ORDER = BodyMapNet.BRANCH_ORDER


def _target_2d_points(num_archetypes=5, radius=3.0):
    """5 fixed, well-separated 2D targets on a circle (one per archetype)."""
    points = {}
    for label in range(num_archetypes):
        angle = math.radians(label * 72.0)
        points[label] = (radius * math.cos(angle), radius * math.sin(angle))
    return points


def load_frozen_branches():
    encoders = {}
    for branch, EncoderClass in ENCODER_CLASSES.items():
        model = EncoderClass()
        ckpt = torch.load(CHECKPOINT_PATHS[branch], map_location="cpu")
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        model.requires_grad_(False)
        encoders[branch] = model
    return encoders


def _embed_batch(encoders, batch):
    """Run each frozen encoder to get (batch, embed_dim) embeddings per branch."""
    embeddings = {}
    for branch in BRANCH_ORDER:
        _, emb = encoders[branch](batch[branch])
        embeddings[branch] = emb
    return embeddings


def _sample_present_mask(rng):
    """
    Per-branch 50% keep. Guarantee >= 1 branch present (batch-level mask; if all
    dropped, force one back on at random).
    """
    mask = {b: (rng.random() >= 0.5) for b in BRANCH_ORDER}
    if not any(mask.values()):
        mask[rng.choice(BRANCH_ORDER)] = True
    return mask


def _run_epoch(model, encoders, loader, loss_fn, mse_fn, targets_2d, rng, optimizer=None):
    train_mode = optimizer is not None
    model.train(train_mode)
    total_loss, correct, count = 0.0, 0, 0
    torch.set_grad_enabled(train_mode)
    for batch in loader:
        labels = batch["archetype_label"]
        goal_onehot = batch["goal_onehot"]
        embeddings = _embed_batch(encoders, batch)
        present_mask = _sample_present_mask(rng)

        archetype_logits, embedding_2d, _ = model(embeddings, present_mask, goal_onehot)

        target_pts = torch.tensor(
            [targets_2d[int(l)] for l in labels], dtype=torch.float32
        )
        loss = loss_fn(archetype_logits, labels) + 0.1 * mse_fn(embedding_2d, target_pts)

        if train_mode:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        total_loss += loss.item() * labels.size(0)
        correct += (archetype_logits.argmax(dim=1) == labels).sum().item()
        count += labels.size(0)
    torch.set_grad_enabled(True)
    return total_loss / max(count, 1), correct / max(count, 1)


def train_fusion():
    stats = config.load_impute_stats()
    encoders = load_frozen_branches()

    train_rows = ds.read_raw_rows(os.path.join(config.PROCESSED_DIR, "fusion_train.csv"))
    val_rows = ds.read_raw_rows(os.path.join(config.PROCESSED_DIR, "fusion_val.csv"))
    train_loader = DataLoader(ds.FusionDataset(train_rows, stats),
                              batch_size=config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(ds.FusionDataset(val_rows, stats),
                            batch_size=config.BATCH_SIZE, shuffle=False)

    torch.manual_seed(config.RANDOM_SEED)
    model = BodyMapNet()
    loss_fn = nn.CrossEntropyLoss()
    mse_fn = nn.MSELoss()
    targets_2d = _target_2d_points()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.LEARNING_RATE,
                                 weight_decay=config.WEIGHT_DECAY)

    best_val = float("inf")
    patience = 0
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    print("\n=== Training fusion model (BodyMapNet) ===")

    for epoch in range(config.MAX_EPOCHS):
        train_rng = random.Random(config.RANDOM_SEED + epoch)
        train_loss, _ = _run_epoch(model, encoders, train_loader, loss_fn, mse_fn,
                                   targets_2d, train_rng, optimizer)
        # Validation uses modality dropout too, with a fixed seed per epoch so it
        # reflects real partial-data usage rather than only the 4/4-present case.
        val_rng = random.Random(config.RANDOM_SEED)
        val_loss, val_acc = _run_epoch(model, encoders, val_loader, loss_fn, mse_fn,
                                       targets_2d, val_rng, optimizer=None)
        print(f"epoch {epoch:03d} | train_loss {train_loss:.4f} | "
              f"val_loss {val_loss:.4f} | val_acc {val_acc:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            patience = 0
            torch.save({"model_state_dict": model.state_dict(),
                        "epoch": epoch, "val_loss": val_loss}, config.FUSION_CKPT)
        else:
            patience += 1
            if patience >= config.EARLY_STOPPING_PATIENCE:
                print(f"Early stopping at epoch {epoch}.")
                break

    print(f"Best val_loss for fusion: {best_val:.4f}, checkpoint saved to {config.FUSION_CKPT}")


if __name__ == "__main__":
    train_fusion()
