"""
app/app.py — Flask web server for BodyMap Net.
"""

import os
import re
import sys
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, abort,
    session, flash,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402
from db import database as db  # noqa: E402
from app import inference  # noqa: E402
from app import charts  # noqa: E402
from app import insights  # noqa: E402
from app import streaks  # noqa: E402

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = config.SECRET_KEY

# Context available to every template.
app.jinja_env.globals.update(
    EXERCISES=config.EXERCISES,
    EXERCISE_GROUPS=config.EXERCISE_GROUPS,
    BODY_GOALS=config.BODY_GOALS,
    ACTIVITY_LEVELS=config.ACTIVITY_LEVELS,
)


@app.context_processor
def inject_auth():
    """
    Every template gets: auth_role ('admin' | 'user' | None), auth_unique_id
    (when role == 'user'), auth_name (display name), auth_admin_username,
    and — only while logged out — login_users (for the login modal's
    account picker).
    """
    role = session.get("role")
    ctx = {
        "auth_role": role,
        "auth_unique_id": session.get("unique_id"),
        "auth_admin_username": session.get("admin_username"),
        "auth_name": None,
    }
    if role == "user":
        u = db.get_user(session.get("unique_id"))
        ctx["auth_name"] = u["name"] if u else None
    if role is None:
        ctx["login_users"] = db.list_users()
    ctx["global_prefs"] = db.get_appearance()
    return ctx


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "role" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("That action requires an admin login.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _is_valid_hex_color(value):
    return bool(value) and bool(_HEX_COLOR_RE.match(value))


def _band_index(label, bands):
    for k, v in bands.items():
        if v == label:
            return k
    return 0


def _build_week_autofill_data(unique_id):
    """
    Build a compact JSON-able list describing each of the user's previously
    logged weeks, for the "autofill from a previous week" dropdown on the
    Test page. Only includes fields that were actually filled in that week's
    (most recent) submission, so the frontend knows which sections to
    populate/reveal.
    """
    weeks = db.get_weeks_for_user(unique_id)
    out = []
    for w in weeks:
        entry = {
            "run_id": w["run_id"],
            "week_start": w["week_start"],
            "week_end": w["week_end"],
            "tests_included": (w.get("tests_included") or "").split(",") if w.get("tests_included") else [],
        }
        ex = w.get("exercise_inputs_json") or {}
        raw_ex = ex.get("raw") or {}
        if raw_ex:
            # raw_ex keys look like "<exercise_id>_sets" -> matches form field "ex_<exercise_id>".
            entry["exercise"] = raw_ex
        if w.get("bmi_height_cm") is not None or w.get("bmi_weight_kg") is not None:
            entry["bmi_height_cm"] = w.get("bmi_height_cm")
            entry["bmi_weight_kg"] = w.get("bmi_weight_kg")
        if (w.get("bf_neck_cm") is not None or w.get("bf_waist_cm") is not None
                or w.get("bf_hip_cm") is not None):
            entry["bf_neck_cm"] = w.get("bf_neck_cm")
            entry["bf_waist_cm"] = w.get("bf_waist_cm")
            entry["bf_hip_cm"] = w.get("bf_hip_cm")
        if w.get("cal_activity_level") is not None or w.get("cal_current_intake") is not None:
            entry["cal_activity_level"] = w.get("cal_activity_level")
            entry["cal_current_intake"] = w.get("cal_current_intake")
        out.append(entry)
    return out


def _compute_calorie_target(user, height_cm, weight_kg, activity_level_id):
    """Mifflin-St Jeor target using whatever height/weight is available."""
    gender = user["gender"]
    age = user["age"]
    height_cm = height_cm or (175 if gender == "male" else 162)
    weight_kg = weight_kg or (78 if gender == "male" else 65)
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    mult = config.ACTIVITY_MULTIPLIERS.get(activity_level_id, 1.55)
    return bmr * mult


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login/user", methods=["POST"])
def login_user():
    unique_id = request.form.get("unique_id", "").strip().upper()
    password = request.form.get("password", "")
    user = db.verify_user(unique_id, password)
    if user is None:
        flash("Invalid ID or password.", "error")
        return redirect(url_for("home", tab="user"))
    session.clear()
    session["role"] = "user"
    session["unique_id"] = user["unique_id"]
    flash(f"Welcome back, {user['name']}.", "success")
    return redirect(url_for("home"))


@app.route("/login/admin", methods=["POST"])
def login_admin():
    password = request.form.get("password", "")
    username = db.verify_admin_password(password)
    if username is None:
        flash("Incorrect admin password.", "error")
        return redirect(url_for("home", tab="admin"))
    session.clear()
    session["role"] = "admin"
    session["admin_username"] = username
    flash("Logged in as admin.", "success")
    return redirect(url_for("home"))


@app.route("/login/admin/create", methods=["POST"])
def login_admin_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    current_admin_password = request.form.get("current_admin_password", "")

    if not username or not password:
        flash("Choose a username and password for the new admin account.", "error")
        return redirect(url_for("home", tab="admin"))

    # Only an existing admin can create another admin -- otherwise anyone
    # who finds this form could grant themselves admin access.
    if db.verify_admin_password(current_admin_password) is None:
        flash("That's not a valid current admin password -- new admin accounts can only be "
              "created by an existing admin.", "error")
        return redirect(url_for("home", tab="admin"))

    ok_policy, policy_error = config.validate_password_policy(password)
    if not ok_policy:
        flash(policy_error, "error")
        return redirect(url_for("home", tab="admin"))

    ok = db.create_admin(username, password)
    if not ok:
        flash("That admin username is already taken.", "error")
        return redirect(url_for("home", tab="admin"))
    session.clear()
    session["role"] = "admin"
    session["admin_username"] = username
    flash("Admin account created — you're logged in.", "success")
    return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/test")
@login_required
def test():
    if session["role"] == "user":
        unique_id = session["unique_id"]
        user = db.get_user(unique_id)
        prefs = db.get_preferences(unique_id)
        weeks_autofill = _build_week_autofill_data(unique_id)
        return render_template("test.html", user=user, prefs=prefs, weeks_autofill=weeks_autofill)
    return render_template("test.html", users=db.list_users())


@app.route("/test/register", methods=["POST"])
@admin_required
def test_register():
    name = request.form.get("name", "").strip() or "Anonymous"
    age = request.form.get("age", "").strip() or "30"
    gender = request.form.get("gender", "other")
    body_goal = request.form.get("body_goal", "maintain")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    try:
        age_int = int(age)
    except ValueError:
        age_int = 30
    if not password:
        return render_template("test.html", error="A password is required to create a user.",
                               users=db.list_users())
    if password != confirm_password:
        return render_template("test.html", error="Password and confirmation don't match.",
                               users=db.list_users())
    unique_id = db.create_user(name, age_int, gender, body_goal, password)
    user = db.get_user(unique_id)
    prefs = db.get_preferences(unique_id)
    weeks_autofill = _build_week_autofill_data(unique_id)
    return render_template("test.html", user=user, new_id=unique_id, prefs=prefs,
                           weeks_autofill=weeks_autofill,
                           message=f"Save this ID: {unique_id}", users=db.list_users())


@app.route("/test/lookup", methods=["POST"])
@admin_required
def test_lookup():
    unique_id = request.form.get("unique_id", "").strip().upper()
    user = db.get_user(unique_id)
    if user is None:
        return render_template("test.html", error=f"No account found for ID '{unique_id}'.",
                               users=db.list_users())
    prefs = db.get_preferences(unique_id)
    weeks_autofill = _build_week_autofill_data(unique_id)
    return render_template("test.html", user=user, prefs=prefs, weeks_autofill=weeks_autofill,
                           users=db.list_users())


@app.route("/test/submit", methods=["POST"])
@login_required
def test_submit():
    # Users can only ever submit tests for themselves — the account picker
    # in the form is ignored (and hidden) for them; admins may submit on
    # behalf of anyone.
    if session["role"] == "user":
        unique_id = session["unique_id"]
    else:
        unique_id = request.form.get("unique_id", "").strip().upper()
    user = db.get_user(unique_id)
    if user is None:
        return render_template("test.html", error="Unknown ID — please look up or register again.")

    checked = request.form.getlist("tests")
    used_inference = request.form.get("used_inference") == "on"

    exercise_result = bmi_result = bodyfat_result = calorie_result = None
    exercise_inputs = None
    bmi_height = bmi_weight = bf_neck = bf_waist = bf_hip = None
    cal_activity = cal_intake = None
    embeddings = {"exercise": None, "bmi": None, "bodyfat": None, "calories": None}

    if "exercise" in checked:
        raw = inference.form_to_raw_exercise(request.form)
        # Build a human-readable per-exercise inputs dict for display.
        ex_inputs_display = {}
        for ex in config.EXERCISES:
            v = inference._to_float_or_none(request.form.get(f"ex_{ex['id']}"))
            if v is not None:
                ex_inputs_display[ex["name"]] = {"sets": v, "group": ex["group"]}
        # Also compute group totals for display.
        group_totals_display = {}
        for g in config.EXERCISE_GROUPS:
            total = sum(
                inference._to_float_or_none(request.form.get(f"ex_{ex['id']}")) or 0.0
                for ex in config.EXERCISES if ex["group"] == g
                if inference._to_float_or_none(request.form.get(f"ex_{ex['id']}")) is not None
            )
            if total > 0:
                group_totals_display[g] = total
        # Keep the raw "<exercise_id>_sets" -> value pairs too (id-keyed, not
        # name-keyed) so a future week can be autofilled by mapping each key
        # straight back onto its "ex_<exercise_id>" form field.
        raw_ex_display = {k: v for k, v in raw.items() if v is not None}
        exercise_inputs = {
            "per_exercise": ex_inputs_display,
            "group_totals": group_totals_display,
            "raw": raw_ex_display,
        }
        res = inference.predict_exercise(raw, user["body_goal"])
        embeddings["exercise"] = res["embedding"]
        exercise_result = {"label": res["label"], "confidence": res["confidence"],
                           "group_scores": res["group_scores"]}

    if "bmi" in checked:
        raw = inference.form_to_raw_bmi(request.form, user)
        bmi_height, bmi_weight = raw["height_cm"], raw["weight_kg"]
        res = inference.predict_bmi(raw, user["body_goal"])
        embeddings["bmi"] = res["embedding"]
        bmi_result = {"label": res["label"], "confidence": res["confidence"],
                      "bmi_value": res["bmi_value"],
                      "height_cm": bmi_height, "weight_kg": bmi_weight}

    if "bodyfat" in checked:
        raw = inference.form_to_raw_bodyfat(request.form, user)
        bf_neck, bf_waist, bf_hip = raw["neck_cm"], raw["waist_cm"], raw["hip_cm"]
        res = inference.predict_bodyfat(raw, user["body_goal"])
        embeddings["bodyfat"] = res["embedding"]
        bodyfat_result = {"label": res["label"], "confidence": res["confidence"],
                          "bodyfat_value": res["bodyfat_value"],
                          "neck_cm": bf_neck, "waist_cm": bf_waist, "hip_cm": bf_hip}

    if "calories" in checked:
        raw = inference.form_to_raw_calories(request.form, user)
        cal_activity = config.ACTIVITY_LEVELS.get(raw["activity_level"])
        cal_intake = raw["current_intake"]
        target = _compute_calorie_target(user, bmi_height, bmi_weight, raw["activity_level"])
        res = inference.predict_calories(raw, user["body_goal"])
        embeddings["calories"] = res["embedding"]
        calorie_result = {"label": res["label"], "confidence": res["confidence"],
                          "current_intake": cal_intake, "target_intake": round(target, 0),
                          "activity_level": cal_activity}

    fused_result = None
    if used_inference and any(v is not None for v in embeddings.values()):
        fused = inference.predict_fused(embeddings, user["body_goal"])
        fused_result = {"archetype": fused["archetype"], "confidence": fused["confidence"],
                        "archetype_label": fused["archetype_label"],
                        "embedding_2d": fused["embedding_2d"]}

    # Week the data was logged for (optional — set by the week-picker widget).
    week_start = request.form.get("week_start", "").strip() or None
    week_end = request.form.get("week_end", "").strip() or None

    run_id = db.insert_test_run(
        unique_id=unique_id,
        tests_included=",".join(checked),
        used_inference=used_inference,
        week_start=week_start,
        week_end=week_end,
        exercise_inputs=exercise_inputs,
        bmi_height_cm=bmi_height, bmi_weight_kg=bmi_weight,
        bf_neck_cm=bf_neck, bf_waist_cm=bf_waist, bf_hip_cm=bf_hip,
        cal_activity_level=cal_activity, cal_current_intake=cal_intake,
        exercise_result=exercise_result, bmi_result=bmi_result,
        bodyfat_result=bodyfat_result, calorie_result=calorie_result,
        fused_result=fused_result,
    )
    # Check in streak for today (or the date provided)
    test_date = request.form.get("test_date")  # ISO format (YYYY-MM-DD) or None for today
    db.checkin_streak(unique_id, test_date)
    
    # Save entered values as averages for future quick-fill
    avg_kwargs = {}
    if bmi_height is not None:
        avg_kwargs["avg_height_cm"] = bmi_height
    if bmi_weight is not None:
        avg_kwargs["avg_weight_kg"] = bmi_weight
    if bf_neck is not None:
        avg_kwargs["avg_neck_cm"] = bf_neck
    if bf_waist is not None:
        avg_kwargs["avg_waist_cm"] = bf_waist
    if bf_hip is not None:
        avg_kwargs["avg_hip_cm"] = bf_hip
    if "calories" in checked and raw.get("activity_level"):
        avg_kwargs["avg_activity_level"] = raw["activity_level"]
    if cal_intake is not None:
        avg_kwargs["avg_current_intake"] = cal_intake
    # Store total exercise sets as average
    if exercise_inputs and exercise_inputs.get("group_totals"):
        total_sets = sum(exercise_inputs["group_totals"].values())
        avg_kwargs["avg_exercise_sets_total"] = total_sets
    if avg_kwargs:
        db.update_preferences(unique_id, **avg_kwargs)
    
    return redirect(url_for("result", run_id=run_id))


@app.route("/result/<int:run_id>")
@login_required
def result(run_id):
    run = db.get_run(run_id)
    if run is None:
        abort(404, description="Test run not found.")
    if session["role"] == "user" and run["unique_id"] != session["unique_id"]:
        abort(403, description="You can only view your own results.")

    user = db.get_user(run["unique_id"])
    prefs = db.get_preferences(run["unique_id"])
    streak_info = db.get_current_streak(run["unique_id"])

    charts_out = {}

    if run.get("exercise_result_json"):
        gs = run["exercise_result_json"].get("group_scores", {})
        charts_out["exercise"] = charts.make_exercise_bar_chart(gs)

    if run.get("bmi_result_json"):
        idx = _band_index(run["bmi_result_json"]["label"], config.BMI_BANDS)
        charts_out["bmi"] = charts.make_gauge_bar_chart(idx + 0.5, config.BMI_BANDS, "BMI")

    if run.get("bodyfat_result_json"):
        idx = _band_index(run["bodyfat_result_json"]["label"], config.BODYFAT_BANDS)
        charts_out["bodyfat"] = charts.make_gauge_bar_chart(idx + 0.5, config.BODYFAT_BANDS, "Body Fat")

    if run.get("calorie_result_json"):
        cr = run["calorie_result_json"]
        charts_out["calorie"] = charts.make_calorie_bar_chart(
            cr.get("current_intake"), cr.get("target_intake"))

    if run.get("fused_result_json"):
        fr = run["fused_result_json"]
        charts_out["fused"] = charts.make_archetype_map_chart(
            fr.get("embedding_2d"), fr.get("archetype_label"))

    # Generate personalized AI insights
    user_insights = insights.generate_insights(
        user=user,
        exercise_result=run.get("exercise_result_json"),
        bmi_result=run.get("bmi_result_json"),
        bodyfat_result=run.get("bodyfat_result_json"),
        calorie_result=run.get("calorie_result_json"),
        fused_result=run.get("fused_result_json"),
        exercise_inputs=run.get("exercise_inputs_json"),
    )

    # Is this week's result actually good news for what the user is going for?
    goal_verdict = insights.generate_goal_verdict(
        user=user,
        exercise_result=run.get("exercise_result_json"),
        bmi_result=run.get("bmi_result_json"),
        bodyfat_result=run.get("bodyfat_result_json"),
        calorie_result=run.get("calorie_result_json"),
        fused_result=run.get("fused_result_json"),
    )

    # Consecutive-week consistency streaks (positive & negative).
    weekly_streaks = streaks.compute_weekly_streaks(user, db.get_weeks_for_user(run["unique_id"]))

    return render_template("result.html", run=run, charts=charts_out,
                           user_insights=user_insights, streak_info=streak_info,
                           goal_verdict=goal_verdict, weekly_streaks=weekly_streaks,
                           user_prefs=prefs)


@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    is_user = session["role"] == "user"
    own_id = session.get("unique_id")
    users_list = [u for u in db.list_users() if u["unique_id"] == own_id] if is_user else db.list_users()

    if request.method == "GET":
        return render_template("history.html", users=users_list)

    unique_id = own_id if is_user else request.form.get("unique_id", "").strip().upper()
    user = db.get_user(unique_id)
    if user is None:
        return render_template("history.html", error=f"No account found for ID '{unique_id}'.",
                               unique_id=unique_id, users=users_list)
    runs = db.get_runs_for_user(unique_id)
    weekly_streaks = streaks.compute_weekly_streaks(user, db.get_weeks_for_user(unique_id))
    return render_template("history.html", user=user, runs=runs, unique_id=unique_id,
                           users=users_list, weekly_streaks=weekly_streaks)


@app.route("/settings")
@login_required
def settings():
    is_admin = session["role"] == "admin"
    if is_admin:
        return render_template("settings.html", users=db.list_users(), is_admin=True,
                               all_users=db.list_users())
    unique_id = session["unique_id"]
    user = db.get_user(unique_id)
    prefs = db.get_preferences(unique_id)
    return render_template("settings.html", user=user, prefs=prefs, user_prefs=prefs,
                           users=[u for u in db.list_users() if u["unique_id"] == unique_id],
                           is_admin=False)


@app.route("/settings/lookup", methods=["POST"])
@admin_required
def settings_lookup():
    unique_id = request.form.get("unique_id", "").strip().upper()
    user = db.get_user(unique_id)
    if user is None:
        return render_template("settings.html", error=f"No account found for ID '{unique_id}'.",
                               users=db.list_users(), is_admin=True, all_users=db.list_users())
    prefs = db.get_preferences(unique_id)
    return render_template("settings.html", user=user, prefs=prefs, user_prefs=prefs,
                           users=db.list_users(), is_admin=True, all_users=db.list_users())


@app.route("/settings/update", methods=["POST"])
@login_required
def settings_update():
    unique_id = session["unique_id"] if session["role"] == "user" else \
        request.form.get("unique_id", "").strip().upper()
    is_admin = session["role"] == "admin"
    name = request.form.get("name", "").strip() or None
    age = request.form.get("age", "").strip() or None
    gender = request.form.get("gender") or None
    new_goal = request.form.get("body_goal", "maintain")
    ok = db.update_profile(unique_id, name=name, age=age, gender=gender, body_goal=new_goal)
    user = db.get_user(unique_id)
    users_list = db.list_users() if is_admin else [u for u in db.list_users() if u["unique_id"] == unique_id]
    if not ok or user is None:
        return render_template("settings.html", error="Could not update — unknown ID.",
                               users=users_list, is_admin=is_admin,
                               all_users=db.list_users() if is_admin else None)
    prefs = db.get_preferences(unique_id)
    return render_template("settings.html", user=user, prefs=prefs, user_prefs=prefs,
                           message="Profile updated successfully.", users=users_list, is_admin=is_admin,
                           all_users=db.list_users() if is_admin else None)


@app.route("/settings/change-password", methods=["POST"])
@login_required
def settings_change_password():
    """A user changes their own password. Admin accounts aren't handled here —
    they log in with a single shared password field, not a per-account one."""
    if session["role"] != "user":
        flash("Password changes here are for user accounts only.", "error")
        return redirect(url_for("settings"))
    unique_id = session["unique_id"]
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_new_password", "")

    if db.verify_user(unique_id, current_password) is None:
        flash("Current password is incorrect.", "error")
        return redirect(url_for("settings"))
    if not new_password or new_password != confirm_password:
        flash("New password and confirmation don't match.", "error")
        return redirect(url_for("settings"))
    ok_policy, policy_error = config.validate_password_policy(new_password)
    if not ok_policy:
        flash(policy_error, "error")
        return redirect(url_for("settings"))

    db.set_user_password(unique_id, new_password)
    flash("Password updated.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/theme", methods=["POST"])
def settings_theme():
    """Update the site-wide theme — applies to every account, admin or user, and to
    anonymous visitors too, since it's one shared setting rather than per-account."""
    theme = request.form.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    db.update_appearance(theme=theme)
    return "", 204  # No content


@app.route("/settings/appearance", methods=["POST"])
def settings_appearance():
    """Update theme, font size, and accent color together — shared site-wide, not per-account."""
    theme = request.form.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    font_size = request.form.get("font_size", "medium")
    if font_size not in ("small", "medium", "large"):
        font_size = "medium"
    accent_color = request.form.get("accent_color", "#FF3E00").strip()
    if not _is_valid_hex_color(accent_color):
        accent_color = "#FF3E00"

    db.update_appearance(theme=theme, font_size=font_size, accent_color=accent_color)

    is_admin = session.get("role") == "admin"
    unique_id = request.form.get("unique_id", "").strip().upper() if is_admin else session.get("unique_id")
    user = db.get_user(unique_id) if unique_id else None
    users_list = db.list_users() if is_admin else ([u for u in db.list_users() if u["unique_id"] == unique_id] if unique_id else [])
    prefs = db.get_preferences(unique_id) if user else None
    if "role" not in session:
        # Anonymous ping (e.g. from a page without the Settings form) — nothing to re-render.
        return "", 204
    return render_template("settings.html", user=user, prefs=prefs, user_prefs=prefs,
                           message="Appearance updated for everyone.", users=users_list, is_admin=is_admin,
                           all_users=db.list_users() if is_admin else None)


@app.route("/settings/avg-measurements", methods=["POST"])
@login_required
def settings_avg_measurements():
    """Save average height/weight for BMI pre-fill."""
    is_admin = session["role"] == "admin"
    unique_id = request.form.get("unique_id", "").strip().upper() if is_admin else session["unique_id"]
    avg_height = request.form.get("avg_height_cm")
    avg_weight = request.form.get("avg_weight_kg")
    try:
        avg_height = float(avg_height) if avg_height else None
        avg_weight = float(avg_weight) if avg_weight else None
    except ValueError:
        pass
    db.update_preferences(unique_id, avg_height_cm=avg_height, avg_weight_kg=avg_weight)
    return "", 204  # No content


# ---------------------------------------------------------------------------
# Admin-only: create / delete user accounts
# ---------------------------------------------------------------------------
@app.route("/settings/admin/create-user", methods=["POST"])
@admin_required
def admin_create_user():
    name = request.form.get("name", "").strip() or "Anonymous"
    age = request.form.get("age", "").strip() or "30"
    gender = request.form.get("gender", "other")
    body_goal = request.form.get("body_goal", "maintain")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    try:
        age_int = int(age)
    except ValueError:
        age_int = 30
    if not password:
        flash("A password is required to create a user.", "error")
        return redirect(url_for("settings"))
    if password != confirm_password:
        flash("Password and confirmation don't match.", "error")
        return redirect(url_for("settings"))
    ok_policy, policy_error = config.validate_password_policy(password)
    if not ok_policy:
        flash(policy_error, "error")
        return redirect(url_for("settings"))
    unique_id = db.create_user(name, age_int, gender, body_goal, password)
    flash(f"Created user '{name}' — unique ID: {unique_id}", "success")
    return redirect(url_for("settings"))


@app.route("/settings/admin/reset-password", methods=["POST"])
@admin_required
def admin_reset_password():
    unique_id = request.form.get("unique_id", "").strip().upper()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_new_password", "")
    user = db.verify_user(unique_id, current_password)
    if user is None:
        flash("Incorrect current password for that account — password not changed.", "error")
        return redirect(url_for("settings"))
    if not new_password:
        flash("Enter a new password.", "error")
        return redirect(url_for("settings"))
    if new_password != confirm_password:
        flash("New password and confirmation don't match.", "error")
        return redirect(url_for("settings"))
    ok_policy, policy_error = config.validate_password_policy(new_password)
    if not ok_policy:
        flash(policy_error, "error")
        return redirect(url_for("settings"))
    db.set_user_password(unique_id, new_password)
    flash(f"Password updated for {user['name']} ({unique_id}).", "success")
    return redirect(url_for("settings"))


@app.route("/settings/admin/delete-user", methods=["POST"])
@admin_required
def admin_delete_user():
    unique_id = request.form.get("unique_id", "").strip().upper()
    password = request.form.get("password", "")
    user = db.verify_user(unique_id, password)
    if user is None:
        flash("Incorrect password for that account — deletion cancelled.", "error")
        return redirect(url_for("settings"))
    ok = db.delete_user(unique_id)
    if ok:
        flash(f"Deleted user {unique_id} and all of their data.", "success")
    else:
        flash(f"No account found for ID '{unique_id}'.", "error")
    return redirect(url_for("settings"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
