"""
tests/super_demo.py — one-file "super tester" for BodyMap Net.

Creates 10 demo accounts (different names / goals / passwords) and backfills
each of them with several WEEKS of realistic test submissions, run through
the real inference models, so the app's weekly-streak and goal-verdict
features have real data to show off:

    python tests/super_demo.py

Then start the app (python manage.py runserver, or app/app.py) and log in
as any of the printed accounts, or as the admin (password: BodyMap#2025, or
whatever you changed it to) and look
them up from Test / History / Settings.

Each account is deliberately shaped to exercise a different scenario:

  1. Marcus Chen    — gain_muscle        — everything good, 5-week streak
  2. Priya Sharma    — lose_fat           — everything good, 5-week streak
  3. Jamal Carter    — improve_endurance  — everything good, 5-week streak
  4. Elena Petrova   — maintain           — everything good, 5-week streak
  5. Tom Walsh       — gain_muscle        — never trains Chest + under-eats
  6. Aisha Bello      — lose_fat           — overtrains + overeats
  7. Diego Ramirez    — maintain           — BMI drifts into "Obese" 4 weeks
  8. Sara Kim         — improve_endurance  — alternates good/bad -> no streak
  9. Liam O'Brien     — gain_muscle        — 3 good weeks, a GAP week, 1 more
 10. Nadia Hassan      — lose_fat           — rocky start, then 2 good weeks

Re-running this script is safe: any pre-existing demo accounts (matched by
name) are deleted and recreated from scratch, so streaks are always
computed fresh from what this run inserted.

All three places that judge "is this good or bad news" — the goal-verdict
banner, the tips/recommendations panel, and these weekly streaks — share
one rulebook (app/outcomes.py), so they never contradict each other for
the same result + goal.

The archetype/fusion model itself is now also goal-conditioned (it sees
body_goal as an input, not just a post-hoc label), so the same body
composition can genuinely be judged differently depending on what someone
is training for. That conditioning shifts confidence and can flip
borderline calls, but it can't invent muscle mass that isn't there in the
inputs — a body that reads as "Skinny Athlete" on the physical evidence
won't be relabeled "Buff / Muscular" just because the goal is gain_muscle.
That's why Marcus's preset below is deliberately built to a body
composition that genuinely matches "Buff / Muscular" (higher weight,
athletic body fat, solid training volume) rather than a generic "healthy"
body — so his account demonstrates the fully-aligned case end to end.
Priya/Jamal/Elena keep the generic "healthy" preset instead, which reads
as "Skinny Athlete" — neutral, not the anti-archetype, for their goals —
so they show clean positive streaks everywhere except no goal-archetype
streak at all (neutral doesn't start one).
"""

import os
import sys
import random
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from db import database as db  # noqa: E402
from app import inference  # noqa: E402
from app import insights  # noqa: E402
from app import streaks  # noqa: E402
from app.app import _compute_calorie_target  # noqa: E402  (reuse the real TDEE math)

random.seed(getattr(config, "RANDOM_SEED", 7))

# ---------------------------------------------------------------------------
# Raw-input builders (mirrors tests/auto_tester.py's SCENARIOS, extended with
# a "zero out these groups" option so we can simulate a permanently-skipped
# muscle group).
# ---------------------------------------------------------------------------
_EXERCISE_MULT = {"healthy": 1.0, "risky": 0.1, "overtrained": 2.5}


def exercise_raw(scenario="healthy", zero_groups=None):
    """Sets are always whole numbers -- the test page's exercise inputs are
    step="1" (integer only), so a jittered decimal like 17.9 would be
    invalid to reuse via the "autofill from a previous week" feature."""
    zero_groups = set(zero_groups or [])
    mult = _EXERCISE_MULT[scenario]
    raw = {}
    for ex in config.EXERCISES:
        if ex["group"] in zero_groups:
            raw[f"{ex['id']}_sets"] = 0
        else:
            jitter = random.uniform(0.92, 1.08)  # so weeks aren't bit-identical
            raw[f"{ex['id']}_sets"] = max(0, round(ex["baseline"] * mult * jitter))
    return raw


def bmi_raw(height_cm, weight_kg, age, gender):
    return {
        "height_cm": round(height_cm + random.uniform(-0.3, 0.3), 1),
        "weight_kg": round(weight_kg + random.uniform(-0.6, 0.6), 1),
        "age": age,
        "gender": gender,
    }


def bodyfat_raw(neck_cm, waist_cm, hip_cm, height_cm, gender):
    return {
        "neck_cm": round(neck_cm + random.uniform(-0.2, 0.2), 1),
        "waist_cm": round(waist_cm + random.uniform(-0.5, 0.5), 1),
        "hip_cm": round(hip_cm + random.uniform(-0.5, 0.5), 1),
        "height_cm": round(height_cm + random.uniform(-0.3, 0.3), 1),
        "gender": gender,
    }


def calories_raw(activity_level_id, current_intake):
    """current_intake is whole kcal -- the test page's field is step="1"."""
    return {
        "activity_level": activity_level_id,
        "current_intake": int(round(current_intake + random.uniform(-40, 40))),
    }


# ---------------------------------------------------------------------------
# Body presets per gender, used as the "healthy" / "risky" anchor points.
# ---------------------------------------------------------------------------
BODY = {
    "male_healthy":   dict(height_cm=178, weight_kg=74, neck_cm=38, waist_cm=81, hip_cm=97),
    "female_healthy": dict(height_cm=165, weight_kg=59, neck_cm=32, waist_cm=68, hip_cm=95),
    "male_muscular":  dict(height_cm=178, weight_kg=88, neck_cm=42, waist_cm=82, hip_cm=99),
    "male_obese":     dict(height_cm=173, weight_kg=104, neck_cm=44, waist_cm=118, hip_cm=118),
    "female_obese":   dict(height_cm=162, weight_kg=88, neck_cm=38, waist_cm=100, hip_cm=118),
}


def _submit_week(unique_id, user, week_start, week_end, *,
                  exercise=None, bmi=None, bodyfat=None, calories=None,
                  checkin_date=None):
    """
    Run whichever branches are provided (each a raw-dict or None to skip)
    through the real inference models, fuse them, and insert one test_runs
    row for this week — the same shape app.py's /test/submit route builds.
    """
    tests_included = []
    embeddings = {"exercise": None, "bmi": None, "bodyfat": None, "calories": None}
    exercise_result = bmi_result = bodyfat_result = calorie_result = None
    exercise_inputs = None
    bmi_h = bmi_w = bf_neck = bf_waist = bf_hip = None
    cal_activity = cal_intake = None

    if exercise is not None:
        tests_included.append("exercise")
        res = inference.predict_exercise(exercise, user["body_goal"])
        embeddings["exercise"] = res["embedding"]
        group_totals = {g: t for g, t in config._compute_group_sets(exercise).items() if t is not None}
        exercise_inputs = {"per_exercise": {}, "group_totals": group_totals, "raw": exercise}
        exercise_result = {"label": res["label"], "confidence": res["confidence"],
                           "group_scores": res["group_scores"]}

    if bmi is not None:
        tests_included.append("bmi")
        res = inference.predict_bmi(bmi, user["body_goal"])
        embeddings["bmi"] = res["embedding"]
        bmi_h, bmi_w = bmi["height_cm"], bmi["weight_kg"]
        bmi_result = {"label": res["label"], "confidence": res["confidence"],
                      "bmi_value": res["bmi_value"], "height_cm": bmi_h, "weight_kg": bmi_w}

    if bodyfat is not None:
        tests_included.append("bodyfat")
        res = inference.predict_bodyfat(bodyfat, user["body_goal"])
        embeddings["bodyfat"] = res["embedding"]
        bf_neck, bf_waist, bf_hip = bodyfat["neck_cm"], bodyfat["waist_cm"], bodyfat["hip_cm"]
        bodyfat_result = {"label": res["label"], "confidence": res["confidence"],
                          "bodyfat_value": res["bodyfat_value"],
                          "neck_cm": bf_neck, "waist_cm": bf_waist, "hip_cm": bf_hip}

    if calories is not None:
        tests_included.append("calories")
        cal_activity = config.ACTIVITY_LEVELS.get(calories["activity_level"])
        cal_intake = calories["current_intake"]
        target = _compute_calorie_target(user, bmi_h, bmi_w, calories["activity_level"])
        res = inference.predict_calories(calories, user["body_goal"])
        embeddings["calories"] = res["embedding"]
        calorie_result = {"label": res["label"], "confidence": res["confidence"],
                          "current_intake": cal_intake, "target_intake": round(target, 0),
                          "activity_level": cal_activity}

    fused_result = None
    if any(v is not None for v in embeddings.values()):
        fused = inference.predict_fused(embeddings, user["body_goal"])
        fused_result = {"archetype": fused["archetype"], "confidence": fused["confidence"],
                        "archetype_label": fused["archetype_label"],
                        "embedding_2d": fused["embedding_2d"]}

    run_id = db.insert_test_run(
        unique_id=unique_id,
        tests_included=",".join(tests_included),
        used_inference=True,
        week_start=week_start, week_end=week_end,
        exercise_inputs=exercise_inputs,
        bmi_height_cm=bmi_h, bmi_weight_kg=bmi_w,
        bf_neck_cm=bf_neck, bf_waist_cm=bf_waist, bf_hip_cm=bf_hip,
        cal_activity_level=cal_activity, cal_current_intake=cal_intake,
        exercise_result=exercise_result, bmi_result=bmi_result,
        bodyfat_result=bodyfat_result, calorie_result=calorie_result,
        fused_result=fused_result,
    )
    db.checkin_streak(unique_id, checkin_date or week_end)
    return run_id


# ---------------------------------------------------------------------------
# One entry per account: (name, age, gender, goal, password, week_builder)
# week_builder(week_start, week_end, week_index) -> submits that week or
# returns None to leave a gap (no run at all for that calendar week).
# ---------------------------------------------------------------------------
def _make_consistent_builder(gender, goal, exercise_scenario="healthy",
                             calorie_activity=2, calorie_intake=2400, bmi_key=None):
    body = BODY[bmi_key or f"{gender}_healthy"]

    def builder(unique_id, user, week_start, week_end, week_index):
        return _submit_week(
            unique_id, user, week_start, week_end,
            exercise=exercise_raw(exercise_scenario),
            bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], gender),
            bodyfat=bodyfat_raw(body["neck_cm"], body["waist_cm"], body["hip_cm"], body["height_cm"], gender),
            calories=calories_raw(calorie_activity, calorie_intake),
        )
    return builder


def _tom_builder(unique_id, user, week_start, week_end, week_index):
    body = BODY["male_healthy"]
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("healthy", zero_groups=["Chest"]),  # never trains chest
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "male"),
        calories=calories_raw(3, 1500),  # active but badly under-eating for a bulk
    )


def _aisha_builder(unique_id, user, week_start, week_end, week_index):
    body = BODY["female_healthy"]
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("overtrained"),
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "female"),
        calories=calories_raw(0, 3600),  # sedentary but eating like an athlete
    )


def _diego_builder(unique_id, user, week_start, week_end, week_index):
    body = BODY["male_obese"]
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("risky"),
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "male"),
        calories=calories_raw(0, 2900),
    )


def _sara_builder(unique_id, user, week_start, week_end, week_index):
    body = BODY["female_healthy"]
    good = week_index % 2 == 0  # alternates every week -> never 2-in-a-row
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("healthy" if good else "overtrained"),
        calories=calories_raw(2 if good else 0, 2200 if good else 3800),
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "female"),
    )


def _liam_builder(unique_id, user, week_start, week_end, week_index):
    if week_index == 3:  # 5 weeks total (0..4) — skip the 4th one, a gap
        return None
    body = BODY["male_healthy"]
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("healthy"),
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "male"),
        calories=calories_raw(3, 2900),
    )


def _nadia_builder(unique_id, user, week_start, week_end, week_index):
    body = BODY["female_healthy"]
    good = week_index >= 2  # weeks 0-1 rocky, weeks 2-3 good (freshly building streak)
    return _submit_week(
        unique_id, user, week_start, week_end,
        exercise=exercise_raw("healthy" if good else "risky"),
        calories=calories_raw(2 if good else 0, 2000 if good else 3200),
        bmi=bmi_raw(body["height_cm"], body["weight_kg"], user["age"], "female"),
    )


ACCOUNTS = [
    dict(name="Marcus Chen", age=27, gender="male", goal="gain_muscle", password="Marcus2026!",
        weeks=5, builder=_make_consistent_builder("male", "gain_muscle", "healthy", 3, 3000,
                                                  bmi_key="male_muscular")),
    dict(name="Priya Sharma", age=24, gender="female", goal="lose_fat", password="Priya2026!",
        weeks=5, builder=_make_consistent_builder("female", "lose_fat", "healthy", 2, 1900)),
    dict(name="Jamal Carter", age=31, gender="male", goal="improve_endurance", password="Jamal2026!",
        weeks=5, builder=_make_consistent_builder("male", "improve_endurance", "healthy", 3, 2600)),
    dict(name="Elena Petrova", age=29, gender="female", goal="maintain", password="Elena2026!",
        weeks=5, builder=_make_consistent_builder("female", "maintain", "healthy", 2, 2100)),
    dict(name="Tom Walsh", age=35, gender="male", goal="gain_muscle", password="Tom2026!",
        weeks=4, builder=_tom_builder),
    dict(name="Aisha Bello", age=26, gender="female", goal="lose_fat", password="Aisha2026!",
        weeks=4, builder=_aisha_builder),
    dict(name="Diego Ramirez", age=40, gender="male", goal="maintain", password="Diego2026!",
        weeks=4, builder=_diego_builder),
    dict(name="Sara Kim", age=23, gender="female", goal="improve_endurance", password="Sara2026!",
        weeks=6, builder=_sara_builder),
    dict(name="Liam O'Brien", age=33, gender="male", goal="gain_muscle", password="Liam2026!",
        weeks=5, builder=_liam_builder),
    dict(name="Nadia Hassan", age=28, gender="female", goal="lose_fat", password="Nadia2026!",
        weeks=4, builder=_nadia_builder),
]


def _this_monday():
    today = datetime.now().date()
    return today - timedelta(days=today.weekday())


def _wipe_existing_demo_accounts():
    """Re-running the script shouldn't pile up duplicate demo accounts."""
    existing = {u["name"]: u["unique_id"] for u in db.list_users()}
    for acct in ACCOUNTS:
        uid = existing.get(acct["name"])
        if uid:
            db.delete_user(uid)


def _print_header(text):
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def main():
    _print_header("BodyMap Net — super demo tester")

    # Every demo password must satisfy the same policy the web app enforces
    # (config.validate_password_policy) -- fail loudly here rather than
    # silently seeding accounts the real app would have rejected.
    for acct in ACCOUNTS:
        ok, reason = config.validate_password_policy(acct["password"])
        if not ok:
            raise ValueError(f"Demo password for {acct['name']!r} ({acct['password']!r}) "
                             f"violates the password policy: {reason}")

    _wipe_existing_demo_accounts()

    base_monday = _this_monday() - timedelta(days=7)  # last full week ends "this week"
    created = []

    for acct in ACCOUNTS:
        unique_id = db.create_user(acct["name"], acct["age"], acct["gender"],
                                   acct["goal"], acct["password"])
        user = db.get_user(unique_id)
        n_weeks = acct["weeks"]

        for week_index in range(n_weeks):
            week_start_date = base_monday - timedelta(weeks=(n_weeks - 1 - week_index))
            week_end_date = week_start_date + timedelta(days=6)
            week_start = week_start_date.isoformat()
            week_end = week_end_date.isoformat()
            acct["builder"](unique_id, user, week_start, week_end, week_index)

        created.append((acct, unique_id, user))
        print(f"  + {acct['name']:<16} goal={acct['goal']:<18} "
              f"id={unique_id}  password={acct['password']}  weeks={n_weeks}")

    _print_header("Weekly streaks & latest goal verdict per account")
    for acct, unique_id, user in created:
        weeks = db.get_weeks_for_user(unique_id)
        weekly = streaks.compute_weekly_streaks(user, weeks)
        daily = db.get_current_streak(unique_id)

        print(f"\n{acct['name']} ({unique_id}) — goal: {acct['goal']}")
        print(f"  daily check-in streak: current={daily['current']} best={daily['best']}")
        if weekly:
            for s in weekly:
                arrow = "+" if s["direction"] == "positive" else "-"
                print(f"  [{arrow}] {s['count']}x {s['label']}: {s['message']}")
        else:
            print("  (no 2+ week streak yet — by design for this account)")

        if weeks:
            latest = weeks[0]
            verdict = insights.generate_goal_verdict(
                user,
                exercise_result=latest.get("exercise_result_json"),
                bmi_result=latest.get("bmi_result_json"),
                bodyfat_result=latest.get("bodyfat_result_json"),
                calorie_result=latest.get("calorie_result_json"),
                fused_result=latest.get("fused_result_json"),
            )
            print(f"  latest-week verdict: [{verdict['status'].upper()}] {verdict['message']}")

    _print_header("Done")
    print("Start the app and log in as any account above, or as admin "
          "(password: BodyMap#2025, unless changed)")
    print("and look them up from Test / History / Settings to see the streaks and")
    print("goal-verdict banner rendered on the result and history pages.")


if __name__ == "__main__":
    main()
