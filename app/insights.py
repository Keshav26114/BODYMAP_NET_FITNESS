"""
app/insights.py — personalized coaching insights for the result page.

Generates multiple actionable insights per test, covering:
- Exercise: per-group volume analysis, lagging muscle groups, overtraining warnings
- BMI: goal-aligned weight management advice, healthy range context
- Body Fat: percentage interpretation, comparison to healthy norms
- Calories: deficit/surplus advice, Mifflin-St Jeor context
- Archetype: persona-specific training recommendations (displayed as "Behaviour profile")
"""

import config
from app import outcomes

# Weekly set baselines per group (matches config.py EXERCISE_GROUP_BASELINES)
_GROUP_BASELINES = config.EXERCISE_GROUP_BASELINES

# Healthy body fat % ranges by gender (ACE guidelines)
_BF_HEALTHY = {
    "male":   (6, 25),   # athletic < 14, fitness < 18, average < 25
    "female": (14, 32),  # athletic < 21, fitness < 25, average < 32
}

# Per-group advice for lagging muscles
_LAG_TIPS = {
    "Shoulder":   "Add Overhead Press and Lateral Raises — aim for 3-4 sets each, 2x/week.",
    "Chest":      "Prioritise Bench Press 3x/week. Incline + Fly will fill in upper/outer chest.",
    "Triceps":    "Triceps are 2/3 of your arm. Add Pushdowns or Dips to your next push session.",
    "Biceps":     "Curl with intent — Hammer + Barbell Curl 2-3x/week for full development.",
    "Abs":        "Add Plank holds and Hanging Leg Raises. Core work should be daily or near-daily.",
    "Quads":      "Squats and Leg Press are the foundations — hit 3-4 sets each at least 2x/week.",
    "Hamstrings": "Romanian Deadlifts and Leg Curls protect your knees and balance quad strength.",
    "Calves":     "Calves respond best to high reps (15-20) and high frequency (3x/week minimum).",
    "Cardio":     "Cardio supports recovery and heart health. Aim for at least 2-3 sessions/week.",
}

# Per-group warnings for high volume
_HIGH_VOL_TIPS = {
    "Shoulder":   "High shoulder volume — make sure you include rear delt work to prevent impingement.",
    "Chest":      "Heavy chest volume stresses shoulder joints. Schedule 48+ hrs between sessions.",
    "Triceps":    "Triceps take synergistic load from all pressing. Manage total pressing volume.",
    "Biceps":     "Bicep overtraining is rare but ensure forearms and tendons get adequate rest.",
    "Abs":        "Core can handle volume, but ensure lower back is not taking excessive strain.",
    "Quads":      "High quad volume — ensure knee health and recovery. Include hamstrings to balance.",
    "Hamstrings": "Heavy posterior chain work increases injury risk without adequate warm-up and sleep.",
    "Calves":     "High calf volume is usually fine. Ensure Achilles tendon is not strained.",
    "Cardio":     "High cardio volume can blunt muscle growth. Balance with adequate protein and sleep.",
}


def _goal(user):
    return user.get("body_goal", "maintain").lower()


def _age(user):
    return int(user.get("age", 30))


# ---------------------------------------------------------------------------
# GOAL VERDICT -- "is this week's result good for what the user is going for?"
# Shown as a banner at the top of the result page, above everything else.
#
# Every per-metric judgment is delegated to app/outcomes.py -- the same
# module app/streaks.py uses -- so this banner, the streaks, and the tips
# panel below always agree about whether a given label is good or bad news
# for this user's goal.
# ---------------------------------------------------------------------------
_GOAL_LABELS = {
    "lose_fat":          "lose fat",
    "gain_muscle":        "gain muscle",
    "maintain":           "maintain your current physique",
    "improve_endurance":  "improve your endurance",
}

_OUTCOME_SCORE = {"good": 1, "bad": -1, "neutral": 0}


def generate_goal_verdict(user, exercise_result=None, bmi_result=None,
                          bodyfat_result=None, calorie_result=None, fused_result=None):
    """
    Return {"status": "good"|"mixed"|"poor"|"neutral", "message": str}
    summarising whether this week's results are actually good news for the
    user's stated body_goal -- not just "healthy in general".
    """
    goal = _goal(user)
    goal_label = _GOAL_LABELS.get(goal, "your goal")
    score = 0.0
    total = 0

    if exercise_result:
        total += 1
        score += _OUTCOME_SCORE[outcomes.exercise_outcome(exercise_result.get("label"), goal)]

    if bmi_result:
        total += 1
        score += _OUTCOME_SCORE[outcomes.bmi_outcome(bmi_result.get("label"), goal)]

    if bodyfat_result:
        total += 1
        score += _OUTCOME_SCORE[outcomes.bodyfat_outcome(bodyfat_result.get("label"), goal)]

    if calorie_result:
        total += 1
        score += _OUTCOME_SCORE[outcomes.calorie_outcome(calorie_result.get("label"), goal)]

    if fused_result:
        total += 1
        score += _OUTCOME_SCORE[outcomes.archetype_outcome(fused_result.get("archetype"), goal)]

    if total == 0:
        return {
            "status": "neutral",
            "message": f"Log a test to see whether you're on track to {goal_label}.",
        }

    ratio = score / total
    if ratio >= 0.5:
        return {
            "status": "good",
            "message": f"Good news -- this week's results are well aligned with your goal to {goal_label}.",
        }
    if ratio > -0.25:
        return {
            "status": "mixed",
            "message": f"Mixed results for your goal to {goal_label} -- some areas are on track, others need work (see below).",
        }
    return {
        "status": "poor",
        "message": f"This week's results aren't well aligned with your goal to {goal_label} -- check the recommendations below.",
    }


def generate_insights(user, exercise_result=None, bmi_result=None,
                      bodyfat_result=None, calorie_result=None, fused_result=None,
                      exercise_inputs=None):
    """
    Return a list of insight dicts: [{"type": ..., "title": ..., "text": ...}]
    Types: "success", "warning", "info", "tip"
    Up to 8 insights are returned so the result page shows comprehensive coaching.
    """
    out = []

    goal = _goal(user)
    age = _age(user)
    gender = user.get("gender", "male")

    # ------------------------------------------------------------------ #
    # EXERCISE INSIGHTS                                                    #
    # ------------------------------------------------------------------ #
    if exercise_result and exercise_inputs:
        label = exercise_result.get("label", "")
        group_scores = exercise_result.get("group_scores", {})
        group_totals = exercise_inputs.get("group_totals", {})

        # Classify every group
        not_trained = [g for g in config.EXERCISE_GROUPS if group_scores.get(g, 0) == 0.0]
        lagging     = [g for g in config.EXERCISE_GROUPS if 0 < group_scores.get(g, 0) < 0.5]
        light       = [g for g in config.EXERCISE_GROUPS if 0.5 <= group_scores.get(g, 0) < 0.8]
        overloaded  = [g for g in config.EXERCISE_GROUPS if group_scores.get(g, 0) > 1.5]

        if not_trained:
            out.append({
                "type": "warning",
                "title": "Untrained muscles this week",
                "text": f"{', '.join(not_trained)} received no sets. "
                        + (_LAG_TIPS.get(not_trained[0], "Plan a session targeting these groups.") if not_trained else ""),
            })

        if overloaded:
            g = overloaded[0]
            pct = int(group_scores.get(g, 0) * 100)
            out.append({
                "type": "warning",
                "title": f"High volume: {g}",
                "text": f"{g} is at {pct}% of the weekly baseline. " + _HIGH_VOL_TIPS.get(g, "Allow 48-72 hrs recovery."),
            })

        if lagging:
            g = lagging[0]
            pct = int(group_scores.get(g, 0) * 100)
            out.append({
                "type": "info",
                "title": f"Low volume: {g}",
                "text": f"{g} is at only {pct}% of the weekly baseline. " + _LAG_TIPS.get(g, "Add more sets."),
            })

        if label == "Under-training":
            exercise_type = outcomes.badge_type(outcomes.exercise_outcome(label, goal))
            if "gain" in goal:
                out.append({
                    "type": exercise_type,
                    "title": "Volume needed for muscle gain",
                    "text": "For hypertrophy, target 10-20 sets per muscle group per week. "
                            "Add one extra working set per exercise session.",
                })
            elif "endurance" in goal:
                out.append({
                    "type": exercise_type,
                    "title": "Build your base",
                    "text": "Endurance improves with consistent, progressive volume. "
                            "Increase cardio duration by 10% per week.",
                })
            else:
                out.append({
                    "type": exercise_type,
                    "title": "More training volume needed",
                    "text": "This week's volume was too low to drive meaningful adaptation, even for "
                            "a maintenance goal. Aim for at least 2-3 sets per muscle group, 2x/week.",
                })

        if label == "Over-training":
            out.append({
                "type": outcomes.badge_type(outcomes.exercise_outcome(label, goal)),
                "title": "Deload recommended",
                "text": "Overtraining suppresses immune function and slows adaptation. "
                        "Consider a deload week at 50% volume every 4-6 weeks.",
            })

        if label == "Balanced" and not overloaded and not not_trained:
            trained_count = sum(1 for g in config.EXERCISE_GROUPS if group_scores.get(g, 0) > 0)
            out.append({
                "type": outcomes.badge_type(outcomes.exercise_outcome(label, goal)),
                "title": "Well-rounded training week",
                "text": f"You hit {trained_count}/{len(config.EXERCISE_GROUPS)} muscle groups with balanced volume. "
                        "Keep consistency over weeks to drive adaptations.",
            })

    # ------------------------------------------------------------------ #
    # BMI INSIGHTS                                                         #
    # ------------------------------------------------------------------ #
    if bmi_result:
        label = bmi_result.get("label", "")
        bmi_val = bmi_result.get("bmi_value")
        h = bmi_result.get("height_cm")
        w = bmi_result.get("weight_kg")

        if bmi_val:
            bmi_val_r = round(bmi_val, 1)
            bmi_type = outcomes.badge_type(outcomes.bmi_outcome(label, goal))
            if label == "Obese":
                out.append({
                    "type": bmi_type,
                    "title": f"BMI {bmi_val_r} — Obese range",
                    "text": "BMI above 30 is associated with increased cardiovascular and metabolic risk. "
                            "A 5-10% body weight reduction significantly reduces those risks. Combine "
                            "moderate-intensity cardio with a 500 kcal daily deficit.",
                })
            elif label == "Overweight":
                if "lose" in goal:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Overweight",
                        "text": "A deficit of 500 kcal/day targets ~0.5 kg/week loss. "
                                "Prioritise strength training to preserve lean mass during the cut.",
                    })
                elif "gain" in goal:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Overweight",
                        "text": "BMI alone can't tell muscle from fat, so this isn't necessarily a problem "
                                "while bulking. Track body fat % too, and keep the surplus modest (200-300 kcal).",
                    })
                else:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Overweight",
                        "text": "BMI is mildly elevated. Consider adjusting your goal to include fat loss. "
                                "Even 5% weight loss improves insulin sensitivity and joint health.",
                    })
            elif label == "Underweight":
                if "gain" in goal:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Underweight",
                        "text": "You are below healthy weight — ideal for lean bulking. "
                                "Aim for a 200-300 kcal surplus and 1.6-2.2 g protein/kg body weight.",
                    })
                elif "endurance" in goal:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Underweight",
                        "text": "Many endurance athletes sit below the 'Normal' BMI band without it being "
                                "unhealthy. Keep an eye on energy levels and iron intake.",
                    })
                else:
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Underweight",
                        "text": "BMI below 18.5 can indicate insufficient nutrition or muscle mass. "
                                "Increase calorie intake and prioritise compound resistance training.",
                    })
            elif label == "Normal":
                if h and w:
                    healthy_min = round(18.5 * (h / 100) ** 2, 1)
                    healthy_max = round(25.0 * (h / 100) ** 2, 1)
                    out.append({
                        "type": bmi_type,
                        "title": f"BMI {bmi_val_r} — Healthy range",
                        "text": f"For your height ({h} cm) the healthy weight range is {healthy_min}-{healthy_max} kg. "
                                "You are right in the middle. Maintain with balanced nutrition and exercise.",
                    })

    # ------------------------------------------------------------------ #
    # BODY FAT INSIGHTS                                                    #
    # ------------------------------------------------------------------ #
    if bodyfat_result:
        bf_val = bodyfat_result.get("bodyfat_value")
        label = bodyfat_result.get("label", "")

        if bf_val:
            bf_val_r = round(bf_val, 1)
            lo, hi = _BF_HEALTHY.get(gender, (6, 30))
            bf_type = outcomes.badge_type(outcomes.bodyfat_outcome(label, goal))
            if label in ("Average", "Obese") or bf_val > hi:
                out.append({
                    "type": bf_type,
                    "title": f"Body fat {bf_val_r}% — above average",
                    "text": f"Healthy range for {gender} is approximately {lo}-{hi}%. "
                            "High body fat raises cardiovascular risk. Combine strength training with "
                            "a mild calorie deficit to reduce fat while preserving muscle.",
                })
            elif label in ("Athletic", "Essential"):
                out.append({
                    "type": bf_type,
                    "title": f"Body fat {bf_val_r}% — very lean",
                    "text": "Extremely low body fat can impair hormonal function and recovery. "
                            "Ensure adequate dietary fat (>20% of calories) and monitor energy levels.",
                })
            elif label == "Fitness":
                out.append({
                    "type": bf_type,
                    "title": f"Body fat {bf_val_r}% — fitness range",
                    "text": "You are in excellent shape. Maintain with consistent training and protein intake "
                            f"(1.6-2.2 g/kg). Retest every 4-6 weeks to track trends.",
                })

    # ------------------------------------------------------------------ #
    # CALORIE INSIGHTS                                                     #
    # ------------------------------------------------------------------ #
    if calorie_result:
        label = calorie_result.get("label", "")
        current = calorie_result.get("current_intake")
        target = calorie_result.get("target_intake")

        if current and target:
            diff = int(current - target)
            diff_abs = abs(diff)
            cal_type = outcomes.badge_type(outcomes.calorie_outcome(label, goal))

            if label == "Over-eating":
                surplus_kg = round(diff * 7 / 7700, 2)  # approx weekly gain at that surplus
                if "gain" in goal or "endurance" in goal:
                    out.append({
                        "type": cal_type,
                        "title": f"Eating {diff_abs} kcal above target",
                        "text": f"A surplus can be appropriate here, but at +{diff} kcal/day keep an eye on "
                                "the scale — more than ~0.5 kg/week of gain is mostly fat, not muscle.",
                    })
                else:
                    out.append({
                        "type": cal_type,
                        "title": f"Eating {diff_abs} kcal above target",
                        "text": f"At +{diff} kcal/day you would gain ~{surplus_kg} kg/week of mostly fat. "
                                "Reduce portion sizes or swap high-calorie snacks for protein-dense foods.",
                    })
            elif label == "Under-eating":
                if "gain" in goal:
                    out.append({
                        "type": cal_type,
                        "title": f"Underfuelled for muscle gain",
                        "text": f"You are {diff_abs} kcal below your TDEE. "
                                "A calorie deficit prevents muscle growth. "
                                f"Increase intake to at least {int(target) + 200} kcal/day.",
                    })
                elif "lose" in goal:
                    out.append({
                        "type": cal_type,
                        "title": f"On track — {diff_abs} kcal deficit",
                        "text": f"A {diff_abs} kcal deficit targets ~{round(diff_abs * 7 / 7700, 2)} kg/week loss. "
                                "Stay consistent; never drop below 1200 kcal (women) or 1500 kcal (men).",
                    })
                else:
                    out.append({
                        "type": cal_type,
                        "title": f"{diff_abs} kcal below TDEE",
                        "text": "Mild deficit supports slow fat loss but may reduce performance. "
                                "Fuel workouts with 20-30g protein pre/post training.",
                    })
            else:  # On-target
                out.append({
                    "type": cal_type,
                    "title": "Calories on target",
                    "text": f"Your intake ({int(current)} kcal) matches your TDEE of {int(target)} kcal. "
                            "Adjust if weight trends differ from your goal over 2+ weeks.",
                })

    # ------------------------------------------------------------------ #
    # AGE-SPECIFIC ADVICE                                                  #
    # ------------------------------------------------------------------ #
    if age >= 40 and (exercise_result or bmi_result):
        out.append({
            "type": "tip",
            "title": "Recovery priority (age 40+)",
            "text": "Anabolic hormones decline with age — recovery becomes the limiting factor. "
                    "Prioritise 7-9 hrs sleep, keep protein at 2.0+ g/kg, and consider "
                    "creatine monohydrate (3-5 g/day) for muscle and cognitive support.",
        })

    # ------------------------------------------------------------------ #
    # ARCHETYPE / FUSED INSIGHTS                                           #
    # ------------------------------------------------------------------ #
    if fused_result:
        archetype = fused_result.get("archetype", "")
        tips = {
            "Obesity Risk":         "Focus on sustainable fat loss: high-protein diet, daily walks, progressive strength training.",
            "Buff / Muscular":      "Impressive muscularity. Consider tracking cardiovascular fitness — VO2max matters long-term.",
            "Skinny Athlete":       "Great endurance base — keep cardio as the priority. A couple of light compound lifts a week is plenty for joint health and longevity; no need to chase heavy weight-training volume.",
            "Average / Balanced":   "Solid foundation. Periodise your training — 4 weeks strength, 4 weeks conditioning.",
            "Endurance-Focused":    "Excellent aerobic capacity. Add 2x/week strength training to prevent muscle loss with age.",
        }
        if archetype in tips:
            out.append({
                "type": outcomes.badge_type(outcomes.archetype_outcome(archetype, goal)),
                "title": f"Behaviour profile: {archetype}",
                "text": tips[archetype],
            })

    # ------------------------------------------------------------------ #
    # FALLBACK                                                             #
    # ------------------------------------------------------------------ #
    if not out:
        out.append({
            "type": "info",
            "title": "Keep tracking",
            "text": "You are building a valuable health history. Consistency in tracking leads to "
                    "better pattern recognition and smarter training decisions over time.",
        })

    return out[:8]  # Show up to 8 insights
