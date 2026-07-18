"""
model/fusion.py — BodyMapNet, the missing-modality-tolerant fusion model.
"""

import os
import sys

import torch
import torch.nn as nn

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402


class BodyMapNet(nn.Module):
    """
    Fuses up to 4 branch embeddings (each EMBED_DIM long) into one Body
    Archetype prediction, tolerating any subset of the 4 branches being
    present.

    HOW MISSING BRANCHES ARE HANDLED:
    For each of the 4 branches, this model owns one learned "missing branch"
    vector (an nn.Parameter of length EMBED_DIM). If a branch's real embedding
    is not available for a given user (they didn't run that test), substitute
    that branch's learned missing-vector instead of a zero vector. This lets
    the network represent "this test was not run" as a meaningful, trainable
    signal rather than an arbitrary zero.
    """

    BRANCH_ORDER = ["exercise", "bmi", "bodyfat", "calories"]

    def __init__(self, embed_dim=config.EMBED_DIM, num_heads=config.NUM_ATTENTION_HEADS,
                 num_archetypes=5, goal_dim=len(config.BODY_GOALS)):
        super().__init__()
        self.embed_dim = embed_dim
        self.goal_dim = goal_dim
        self.missing_tokens = nn.ParameterDict({
            branch: nn.Parameter(torch.randn(embed_dim) * 0.02)
            for branch in self.BRANCH_ORDER
        })
        self.attention = nn.MultiheadAttention(
            embed_dim=embed_dim, num_heads=num_heads, batch_first=True
        )
        # Archetype head is goal-conditioned: it answers "given this body
        # composition AND what this person is training for, does it match
        # their goal?" rather than a goal-blind body-type guess.
        self.archetype_head = nn.Sequential(
            nn.Linear(embed_dim + goal_dim, 32), nn.ReLU(), nn.Linear(32, num_archetypes),
        )
        # The 2D map stays goal-agnostic on purpose -- it's a visualisation
        # of body-composition space, not of goal-fit, so it doesn't shift
        # around under the same body just because the stated goal changes.
        self.projection_2d_head = nn.Linear(embed_dim, 2)

    def forward(self, branch_embeddings: dict, present_mask: dict, goal_onehot=None):
        """
        branch_embeddings: {branch_name: tensor (batch, embed_dim) or None}
        present_mask: {branch_name: bool} — True to use the embedding as-is,
            False to replace it with the learned missing token.
        goal_onehot: tensor (batch, goal_dim), or None to condition on "no
            goal information" (an all-zero vector).
        Returns: (archetype_logits, embedding_2d, pooled_fusion_embedding)
        """
        batch_size = next(
            t.shape[0] for t in branch_embeddings.values() if t is not None
        )
        tokens = []
        for branch in self.BRANCH_ORDER:
            if present_mask.get(branch, False) and branch_embeddings.get(branch) is not None:
                tokens.append(branch_embeddings[branch])
            else:
                tokens.append(
                    self.missing_tokens[branch].unsqueeze(0).expand(batch_size, -1)
                )
        stacked = torch.stack(tokens, dim=1)                     # (batch, 4, embed_dim)
        attended, _ = self.attention(stacked, stacked, stacked)  # self-attention
        pooled = attended.mean(dim=1)                            # (batch, embed_dim)

        if goal_onehot is None:
            goal_onehot = torch.zeros(batch_size, self.goal_dim, dtype=pooled.dtype)
        archetype_logits = self.archetype_head(torch.cat([pooled, goal_onehot], dim=1))
        embedding_2d = self.projection_2d_head(pooled)
        return archetype_logits, embedding_2d, pooled
