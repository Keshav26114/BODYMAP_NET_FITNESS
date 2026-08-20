"""
model/branches.py — the four independent branch encoders.

Every encoder shares one shape: input_dim -> hidden -> EMBED_DIM embedding,
with a small classification head hanging off the embedding. forward() returns
(logits, embedding) so the fusion model can reuse the embedding later.
"""

import os
import sys

import torch
import torch.nn as nn

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402


class _BaseEncoder(nn.Module):
    """Shared: input_dim -> hidden -> EMBED_DIM embedding + classification head."""

    def __init__(self, input_dim, hidden_dim, num_classes, embed_dim=config.EMBED_DIM):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, embed_dim),
            nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(embed_dim, 16),
            nn.ReLU(),
            nn.Linear(16, num_classes),
        )

    def forward(self, x):
        embedding = self.encoder(x)
        logits = self.head(embedding)
        return logits, embedding


class ExerciseEncoder(_BaseEncoder):
    # input_dim = 9 groups × 2 (value + missing_flag) + 4 (goal one-hot) = 22
    def __init__(self):
        super().__init__(input_dim=9 * 2 + len(config.BODY_GOALS), hidden_dim=32, num_classes=3)


class BMIEncoder(_BaseEncoder):
    # input_dim = 6 body-measurement features + 4 (goal one-hot) = 10
    def __init__(self):
        super().__init__(input_dim=6 + len(config.BODY_GOALS), hidden_dim=24, num_classes=4)


class BodyFatEncoder(_BaseEncoder):
    # input_dim = 7 body-measurement features + 4 (goal one-hot) = 11
    def __init__(self):
        super().__init__(input_dim=7 + len(config.BODY_GOALS), hidden_dim=24, num_classes=5)


class CalorieEncoder(_BaseEncoder):
    # input_dim = 7 intake/activity features + 4 (goal one-hot) = 11
    def __init__(self):
        super().__init__(input_dim=7 + len(config.BODY_GOALS), hidden_dim=24, num_classes=3)


# Convenience registry keyed by fusion branch name.
ENCODER_CLASSES = {
    "exercise": ExerciseEncoder,
    "bmi": BMIEncoder,
    "bodyfat": BodyFatEncoder,
    "calories": CalorieEncoder,
}

CHECKPOINT_PATHS = {
    "exercise": config.EXERCISE_CKPT,
    "bmi": config.BMI_CKPT,
    "bodyfat": config.BODYFAT_CKPT,
    "calories": config.CALORIE_CKPT,
}
