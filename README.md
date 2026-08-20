# BodyMap Net — Multi-Test Body Composition & Behaviour-Profile Predictor

BodyMap Net is a fully self-contained Flask website. A person registers with
a name, age, gender, and fitness goal and gets back a short unique ID (their
password-protected account key). On the Test page they tick any combination
of four independent tests — Exercise volume, BMI, Body Fat, and Ideal
Calorie — and optionally a fifth **Behaviour Profile (AI)** option that fuses
whichever tests they completed into one overall prediction.

Every one of the five models is conditioned on the user's stated **goal**
(lose fat / gain muscle / maintain / improve endurance), so the same
measurements can genuinely read differently depending on what someone is
training for — a calorie deficit is praised if you're cutting and flagged if
you're bulking, and the Behaviour Profile itself can classify the same body
composition differently depending on your goal. A shared rulebook
(`app/outcomes.py`) decides "is this result good or bad news for *this*
goal", and that same rulebook drives the goal-verdict banner, the tips
panel, and the weekly streaks — so they never contradict each other.

Inputs color themselves green / yellow / red in real time as you type,
results are rendered as server-side Matplotlib charts, and every run is
stored in SQLite (keyed by calendar week) so it can be revisited, printed to
PDF, or reviewed from a per-user History page complete with consecutive-week
streaks. Everything runs locally with no external services, CDNs, or network
calls.

> This is a demonstration project, not a medical or security-grade system.
> The unique ID is a claim-check for your own data, not a secret login.

---

## Contents

- [Tech stack](#tech-stack-hard-constraints)
- [Setup](#setup)
- [Build & run order](#build--run-order)
- [Using the app](#using-the-app)
- [Architecture](#architecture)
  - [The five models](#the-five-models)
  - [Goal-conditioning](#goal-conditioning)
  - [Missing-modality fusion](#missing-modality-fusion-behaviour-profile)
  - [The consistency layer: outcomes.py](#the-consistency-layer-outcomespy)
  - [Weekly storage & streaks](#weekly-storage--streaks)
- [Dev tools](#dev-tools)
- [File manifest](#file-manifest)
- [Publishing to GitHub](#publishing-to-github)

---

## Tech stack (hard constraints)

- **ML:** PyTorch only
- **Web:** Flask only
- **Charts:** Matplotlib only, rendered server-side, embedded as base64 PNG
- **Database:** SQLite via the standard-library `sqlite3` module (no ORM)
- **PDF:** the browser's native `window.print()` + a dedicated print stylesheet
- **Front end:** plain HTML + CSS + vanilla JS, no build step, no framework

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Requires Python 3.9+. No GPU needed — all 5 models are small enough to train
on CPU in well under a minute total.

## Build & run order

The repo ships **without** the trained checkpoints, generated datasets, or
the SQLite database (see `.gitignore`) — they're build artifacts, not
source. Rebuild everything from scratch with:

```bash
# 1. Generate the synthetic training population (~610 users x ~8 weeks each)
python data/data_generator.py

# 2. Split into train/val/test, build per-branch CSVs, compute impute_stats.json
python model/dataset.py

# 3. Train each of the 4 standalone branch encoders (Exercise, BMI, Body Fat, Calories)
python model/train_branches.py

# 4. Train the fusion (Behaviour Profile) model on top of the frozen, trained branches
python model/train_fusion.py

# 5. Confirm all 5 models behave sensibly, including graceful degradation
python model/evaluate.py

# 6. (optional) Sanity-check the models directly from the CLI before trusting the web UI
python tests/auto_tester.py --branch bmi --scenario healthy
python tests/auto_tester.py --fusion --present exercise --random 5 --goal gain_muscle
python tests/auto_tester.py --fusion --present exercise,bmi,bodyfat,calories --random 5

# 7. (optional) Seed 10 demo accounts with several realistic weeks of history each,
#    so History/streaks/the goal-verdict banner all have real data to show off
python tests/super_demo.py

# 8. Run the web app
python app/app.py
# open http://localhost:5000
```

Run every command from this folder (the project root) so `config`, `db`,
`model`, and `app` resolve as top-level packages. The database is
auto-created on first use — no separate init step needed.

Default admin login: password `BodyMap#2025` (see `_DEFAULT_ADMIN_PASSWORD`
in `db/database.py` if you want to change it before first run — change it
after first login either way, and note that creating a *further* admin
account requires an existing admin's password, so this one is the seed for
all admin access).

## Using the app

1. **Register** on the Test page (or log in with an existing ID + password).
2. Tick any combination of the 4 tests, plus **Behaviour Profile (AI)** if
   you want the fused prediction. Every field is optional and validates
   live as you type.
3. Submit — you land on the **Result** page: a chart + label per test you
   ran, a goal-verdict banner ("is this week good news for your goal?"),
   personalized tips, and (if you have 2+ logged weeks) your current
   streaks.
4. **History** shows every past submission for an account, plus the same
   streaks. Admins can look up any account from here or from Settings.
5. **Settings** covers appearance (shared/global), your profile + password,
   and — for admins — creating accounts and resetting/deleting any account
   (both require that account's current password as a safety check).

Every page has a collapsed "How this works" / "Model components" / "How it
saves" / "What each setting does" section if you want the details without
cluttering the main view.

**Passwords** (user accounts, and admin accounts) must be at least 8
characters and include an uppercase letter, a lowercase letter, and a
special symbol — enforced server-side on every route that sets a password,
with a live checklist under the field as you type. **Creating a new admin
account requires an existing admin's password** — without that, anyone who
found the "Create a new admin account" form could grant themselves admin
access, which the login page no longer allows.

## Architecture

### The five models

| Model | Input | Output |
|---|---|---|
| Exercise | weekly sets/sessions per muscle group (9 groups, 44 exercises) | Under-training / Balanced / Over-training |
| BMI | height, weight, age, gender | Underweight / Normal / Overweight / Obese |
| Body Fat | neck, waist, (hip), gender | Essential / Athletic / Fitness / Average / Obese |
| Ideal Calories | activity level, current intake | Under-eating / On-target / Over-eating |
| **Behaviour Profile (fusion)** | whichever of the above 4 embeddings are available | Obesity Risk / Buff-Muscular / Skinny Athlete / Average-Balanced / Endurance-Focused |

The 4 individual bands are objective, goal-independent physical thresholds —
Overweight is Overweight no matter what you're training for. It's the
Behaviour Profile (and everything built on top of it — tips, the goal
verdict, streaks) that judges results *relative to your goal*.

Exercise volume is tracked per muscle group against a realistic weekly
baseline (12–36 sets/group for the 8 resistance groups; a much smaller
2–6 *sessions*/week for Cardio, which is scored on the same small scale as
every other group rather than raw minutes).

### Goal-conditioning

Every one of the 5 models takes the user's goal as an input feature — a
one-hot vector concatenated onto that model's other inputs (see
`config.py`'s `goal_onehot()` and each `build_feature_vector_*` function).
This isn't cosmetic: `data/data_generator.py`'s synthetic population assigns
each fake user a goal *independent of* their body persona (an
`obese_sedentary` synthetic user might have goal=maintain, a
`buff_muscular` one might have goal=lose_fat), which is what forces the
models to actually learn goal as its own signal instead of a shortcut for
body type. The fusion model's archetype head is conditioned on goal directly
(concatenated in right before the final classification layer); its 2D map
projection deliberately stays goal-agnostic, since that's meant to be a
stable visualization of body-composition space, not of goal-fit.

Per-persona training priorities are also tuned to make sense: a
`skinny_athlete` persona's synthetic data has meaningfully lower
weight-training volume and higher cardio than `buff_muscular`, and
`obese_sedentary` / `skinny_athlete` / `endurance_focused` personas all
target elevated cardio (~5-6 sessions/week) versus a ~2-4 default for
everyone else.

### Missing-modality fusion (Behaviour Profile)

A user may run any non-empty subset of the four tests, so the fusion model
must produce a sensible answer whether it sees 1, 2, 3, or all 4 test
results. Each branch is a small encoder that turns its raw inputs into a
16-dimensional embedding. The fusion model, `BodyMapNet`
(`model/fusion.py`), owns one learned "missing branch" vector per branch:
when a test wasn't run, that branch's real embedding is replaced by its
trainable missing token instead of a zero vector, so "this test was not
taken" becomes a meaningful signal the network can reason about. A
self-attention block mixes the four tokens, the user's goal one-hot is
concatenated in, and a classification head predicts the archetype. During
training we apply **modality dropout** — randomly hiding branches even when
we have their values — which forces the network to cope gracefully with
partial data (verified in `model/evaluate.py`'s graceful-degradation report:
accuracy rises smoothly from 1 branch present to all 4). A small auxiliary
loss pulls each sample's 2D projection toward a fixed per-archetype target
arranged on a circle, producing the well-separated scatter plot shown on the
Result page.

### The consistency layer: outcomes.py

`app/outcomes.py` is the single rulebook for "is this label good, bad, or
neutral news, given the user's goal?" — one function per metric
(`exercise_outcome`, `bmi_outcome`, `bodyfat_outcome`, `calorie_outcome`,
`archetype_outcome`), each returning `"good"` / `"bad"` / `"neutral"`. Three
different features all call into these same functions instead of keeping
their own opinion:

- `insights.generate_goal_verdict()` — the banner at the top of the result page.
- `insights.generate_insights()` — the tips panel's color-coding.
- `streaks.compute_weekly_streaks()` — whether a week counts toward a
  positive or negative streak (a `"neutral"` outcome breaks a streak in
  progress, the same as missing data would, but never itself starts one).

This exists because those three features used to disagree — e.g. a
deliberate calorie deficit while trying to lose fat was once praised in the
tips panel, ignored by the goal verdict, and counted as a *negative* streak,
all for the same data. Centralizing the judgment call makes that class of
bug structurally impossible.

### Weekly storage & streaks

Every submission is stored against a calendar week (Monday-Sunday), not a
single timestamp — resubmitting in the same week overwrites that week's
entry rather than creating a duplicate. `app/streaks.py` walks a user's
distinct logged weeks, most-recent first, and for each metric counts how
many *consecutive* weeks in a row it stayed in the same direction (via
`outcomes.py`, see above); a skipped week or a flipped result breaks the
streak. Only streaks of 2+ weeks are surfaced. Per-muscle-group "missed for
N weeks in a row" streaks are tracked separately (negative-only).

## Dev tools

- `tests/auto_tester.py` — CLI for exercising the 5 models directly without
  the web UI: manual/random/scenario inputs per branch, or the fusion model
  with a chosen subset of branches present, optionally conditioned on
  `--goal`.
- `tests/super_demo.py` — seeds 10 demo accounts (different
  names/goals/passwords) with several realistic weeks of history each
  through the real trained models, deliberately shaped to exercise every
  streak scenario (clean positive runs, negative runs, a missed-week gap
  that resets a streak, an alternating account that never builds one, and
  per-muscle-group misses). Prints every account's computed streaks and
  latest goal verdict so you can sanity-check the logic before opening a
  browser. Safe to re-run — it replaces the same 10 named accounts each
  time.

## File manifest

See [`FILES.txt`](FILES.txt) for a one-line description of every file in
this repo.

## Publishing to GitHub

See [`GITHUB_GUIDE.md`](GITHUB_GUIDE.md) for a step-by-step walkthrough —
creating the repo, the first commit, pushing, and what to double-check so
generated artifacts (the database, trained checkpoints, processed CSVs)
don't end up committed.
