"""
tests/auto_tester.py — command-line sanity checker for BodyMap Net.

Modes (mutually exclusive top-level):
  --branch {exercise,bmi,bodyfat,calories} --manual
  --branch {exercise,bmi,bodyfat,calories} --random N
  --branch {exercise,bmi,bodyfat,calories} --scenario NAME
  --fusion --present a,b,c --manual | --random N

The fusion mode must work for EVERY non-empty subset of the 4 branches,
proving the missing-modality design degrades gracefully.
"""

import os
import sys
import random
import argparse

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from app import inference  # noqa: E402

BRANCHES = ["exercise", "bmi", "bodyfat", "calories"]

PREDICT = {
    "exercise": inference.predict_exercise,
    "bmi": inference.predict_bmi,
    "bodyfat": inference.predict_bodyfat,
    "calories": inference.predict_calories,
}


# ---------------------------------------------------------------------------
# Raw-field builders
# ---------------------------------------------------------------------------
def _blank_or(value, none_prob=0.0):
    if random.random() < none_prob:
        return None
    return value


def random_raw(branch, none_prob=0.3):
    if branch == "exercise":
        raw = {}
        for ex in config.EXERCISES:
            base = ex["baseline"]
            raw[f"{ex['id']}_sets"] = _blank_or(
                round(random.uniform(0.2, 1.6) * base, 1), none_prob)
        return raw
    if branch == "bmi":
        return {
            "height_cm": _blank_or(round(random.uniform(150, 195), 1), none_prob),
            "weight_kg": _blank_or(round(random.uniform(45, 120), 1), none_prob),
            "age": random.randint(18, 65),
            "gender": random.choice(["male", "female"]),
        }
    if branch == "bodyfat":
        gender = random.choice(["male", "female"])
        return {
            "neck_cm": _blank_or(round(random.uniform(30, 45), 1), none_prob),
            "waist_cm": _blank_or(round(random.uniform(65, 115), 1), none_prob),
            "hip_cm": _blank_or(round(random.uniform(85, 125), 1), none_prob),
            "height_cm": _blank_or(round(random.uniform(150, 195), 1), none_prob),
            "gender": gender,
        }
    if branch == "calories":
        return {
            "activity_level": random.randint(0, 4),
            "current_intake": _blank_or(round(random.uniform(1000, 4000), 0), none_prob),
        }
    raise ValueError(branch)


SCENARIOS = {
    "exercise": {
        "healthy": {f"{e['id']}_sets": e["baseline"] for e in config.EXERCISES},
        "risky": {f"{e['id']}_sets": e["baseline"] * 0.1 for e in config.EXERCISES},
        "overtrained": {f"{e['id']}_sets": e["baseline"] * 2.5 for e in config.EXERCISES},
    },
    "bmi": {
        "healthy": {"height_cm": 178, "weight_kg": 72, "age": 30, "gender": "male"},
        "risky": {"height_cm": 165, "weight_kg": 115, "age": 45, "gender": "male"},
    },
    "bodyfat": {
        "healthy": {"neck_cm": 38, "waist_cm": 80, "hip_cm": 95, "height_cm": 178, "gender": "male"},
        "risky": {"neck_cm": 42, "waist_cm": 118, "hip_cm": 120, "height_cm": 170, "gender": "male"},
    },
    "calories": {
        "healthy": {"activity_level": 2, "current_intake": 2400},
        "risky": {"activity_level": 0, "current_intake": 4200},
    },
}


# ---------------------------------------------------------------------------
# Manual prompting
# ---------------------------------------------------------------------------
def manual_raw(branch):
    print(f"\nEnter raw fields for the {branch} branch (blank = missing):")
    if branch == "exercise":
        raw = {}
        for ex in config.EXERCISES:
            v = input(f"  {ex['name']} ({ex['unit']}) [{ex['group']}]: ").strip()
            raw[f"{ex['id']}_sets"] = float(v) if v else None
        return raw
    if branch == "bmi":
        return {
            "height_cm": _prompt_float("Height (cm)"),
            "weight_kg": _prompt_float("Weight (kg)"),
            "age": int(input("  Age: ").strip() or "30"),
            "gender": input("  Gender (male/female/other): ").strip() or "other",
        }
    if branch == "bodyfat":
        return {
            "neck_cm": _prompt_float("Neck (cm)"),
            "waist_cm": _prompt_float("Waist (cm)"),
            "hip_cm": _prompt_float("Hip (cm)"),
            "height_cm": _prompt_float("Height (cm)"),
            "gender": input("  Gender (male/female/other): ").strip() or "other",
        }
    if branch == "calories":
        return {
            "activity_level": int(input("  Activity level (0-4): ").strip() or "2"),
            "current_intake": _prompt_float("Current daily intake (kcal)"),
        }
    raise ValueError(branch)


def _prompt_float(label):
    v = input(f"  {label}: ").strip()
    return float(v) if v else None


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------
def _print_result(branch, raw, result):
    print(f"\n--- {branch} result ---")
    print(f"  label     : {result['label']}")
    print(f"  confidence: {result['confidence'] * 100:.1f}%")
    extra = {k: v for k, v in result.items()
             if k not in ("label", "confidence", "embedding")}
    for k, v in extra.items():
        if k == "group_scores":
            continue
        print(f"  {k:<12}: {v}")


def _abbrev(raw):
    items = []
    for k, v in raw.items():
        if v is None:
            continue
        items.append(f"{k.split('_')[0]}={v}")
        if len(items) >= 3:
            break
    return ", ".join(items) or "(all missing)"


def _print_table(rows, headers):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


# ---------------------------------------------------------------------------
# Branch mode
# ---------------------------------------------------------------------------
def run_branch(args):
    branch = args.branch
    goal = args.goal
    if args.manual:
        raw = manual_raw(branch)
        result = PREDICT[branch](raw, goal)
        _print_result(branch, raw, result)
    elif args.random is not None:
        rows = []
        for _ in range(args.random):
            raw = random_raw(branch)
            result = PREDICT[branch](raw, goal)
            rows.append([_abbrev(raw), result["label"], f"{result['confidence'] * 100:.1f}%"])
        _print_table(rows, ["inputs", "label", "confidence"])
    elif args.scenario:
        scenarios = SCENARIOS[branch]
        if args.scenario not in scenarios:
            print(f"Unknown scenario '{args.scenario}'. Available: {list(scenarios)}")
            return
        raw = scenarios[args.scenario]
        result = PREDICT[branch](raw, goal)
        print(f"\nScenario '{args.scenario}' for {branch} (goal={goal}):")
        _print_result(branch, raw, result)
    else:
        print("Choose one of --manual, --random N, or --scenario NAME.")


# ---------------------------------------------------------------------------
# Fusion mode
# ---------------------------------------------------------------------------
def run_fusion(args):
    present = [b.strip() for b in args.present.split(",") if b.strip()]
    for b in present:
        if b not in BRANCHES:
            print(f"Unknown branch '{b}'. Valid: {BRANCHES}")
            return
    if not present:
        print("--present must list at least one branch.")
        return

    goal = args.goal

    def one_pass():
        embeddings = {b: None for b in BRANCHES}
        used_raw = {}
        for b in present:
            raw = manual_raw(b) if args.manual else random_raw(b)
            used_raw[b] = raw
            embeddings[b] = PREDICT[b](raw, goal)["embedding"]
        fused = inference.predict_fused(embeddings, goal)
        return fused

    print(f"\nFusion with branches present: {', '.join(present)} (goal={goal})")
    if args.manual:
        fused = one_pass()
        print(f"  archetype : {fused['archetype']}")
        print(f"  confidence: {fused['confidence'] * 100:.1f}%")
        print(f"  2d point  : {fused['embedding_2d']}")
    else:
        n = args.random or 5
        rows = []
        for _ in range(n):
            fused = one_pass()
            rows.append([fused["archetype"], f"{fused['confidence'] * 100:.1f}%",
                         f"({fused['embedding_2d'][0]:.2f}, {fused['embedding_2d'][1]:.2f})"])
        _print_table(rows, ["archetype", "confidence", "2d_point"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description="BodyMap Net CLI sanity checker.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--branch", choices=BRANCHES)
    mode.add_argument("--fusion", action="store_true")

    p.add_argument("--manual", action="store_true")
    p.add_argument("--random", type=int, metavar="N")
    p.add_argument("--scenario", type=str, metavar="NAME")
    p.add_argument("--present", type=str, metavar="a,b,c",
                   help="Comma-separated branches present for fusion.")
    p.add_argument("--goal", type=str, default="maintain",
                   choices=list(config.BODY_GOALS.values()),
                   help="body_goal to condition predictions on (default: maintain).")
    return p


def main():
    args = build_parser().parse_args()
    random.seed(config.RANDOM_SEED)
    if args.fusion:
        if not args.present:
            print("--fusion requires --present a,b,c")
            return
        run_fusion(args)
    else:
        run_branch(args)


if __name__ == "__main__":
    main()
