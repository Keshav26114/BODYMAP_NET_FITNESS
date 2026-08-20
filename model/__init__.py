"""
model/ — PyTorch model definitions and the training/evaluation pipeline.

branches.py      The 4 small per-test encoders (Exercise, BMI, Body Fat, Calories).
fusion.py        BodyMapNet: fuses whichever branch embeddings are present into
                 one behaviour-profile prediction, conditioned on the user's goal.
dataset.py       Turns data/raw/fused_logs.csv into split, branch-specific CSVs
                 and PyTorch Dataset classes.
train_branches.py  Trains the 4 branch encoders independently.
train_fusion.py    Trains BodyMapNet on top of the frozen, trained branches.
evaluate.py         Reports test-set accuracy and fusion graceful-degradation.
"""
