"""
db/database.py — thin sqlite3 data-access layer (no ORM).

All persistence for BodyMap Net goes through these functions. JSON columns
are encoded on write and decoded on read so callers always deal in plain
Python dicts/lists.
"""

import os
import sys
import json
import string
import secrets
import sqlite3
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

# Make the project root importable so `import config` works regardless of the
# directory the entry-point script was launched from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402

# Columns that hold JSON and must be decoded back into Python objects on read.
_JSON_COLUMNS = (
    "exercise_inputs_json",
    "exercise_result_json",
    "bmi_result_json",
    "bodyfat_result_json",
    "calorie_result_json",
    "fused_result_json",
)


def _iso_date_today():
    """Return today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).date().isoformat()


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    """
    Open a sqlite3 connection to config.DB_PATH, creating the file and running
    schema.sql on first connect. Rows are returned as sqlite3.Row (dict-like).
    """
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(config.SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    _migrate_appearance_columns(conn)
    _migrate_week_columns(conn)
    _migrate_auth_columns(conn)
    _ensure_default_admin(conn)
    _ensure_app_settings(conn)
    return conn


def _ensure_app_settings(conn):
    """Seed the single shared app_settings row the first time the DB is opened."""
    row = conn.execute("SELECT 1 FROM app_settings WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO app_settings (id, theme, font_size, accent_color) VALUES (1, 'light', 'medium', '#FF3E00')"
        )
        conn.commit()


def _migrate_auth_columns(conn):
    """
    Add password_hash to users for existing databases that predate login
    support. Safe to run on every connect. Existing rows created before
    logins existed will have password_hash = NULL and simply can't log in
    as that user until an admin deletes/recreates the account.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    conn.commit()


_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_PASSWORD = "BodyMap#2025"  # meets validate_password_policy(); change after first login


def _ensure_default_admin(conn):
    """Seed a single default admin account the first time the DB is opened."""
    row = conn.execute("SELECT 1 FROM admins LIMIT 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            (_DEFAULT_ADMIN_USERNAME, generate_password_hash(_DEFAULT_ADMIN_PASSWORD), _utc_now_iso()),
        )
        conn.commit()


def _migrate_appearance_columns(conn):
    """
    CREATE TABLE IF NOT EXISTS won't add columns to a table that already
    exists from before font_size/accent_color were introduced, so patch
    them in with ALTER TABLE when missing. Safe to run on every connect.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()}
    if "font_size" not in cols:
        conn.execute(
            "ALTER TABLE user_preferences ADD COLUMN font_size TEXT NOT NULL DEFAULT 'medium'"
        )
    if "accent_color" not in cols:
        conn.execute(
            "ALTER TABLE user_preferences ADD COLUMN accent_color TEXT NOT NULL DEFAULT '#FF3E00'"
        )
    conn.commit()


def _migrate_week_columns(conn):
    """
    Add week_start / week_end to test_runs for existing databases that
    predate the weekly autofill feature. Safe to run on every connect.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(test_runs)").fetchall()}
    if "week_start" not in cols:
        conn.execute("ALTER TABLE test_runs ADD COLUMN week_start TEXT")
    if "week_end" not in cols:
        conn.execute("ALTER TABLE test_runs ADD COLUMN week_end TEXT")
    conn.commit()


def generate_unique_id():
    """Return an unused 8-char uppercase [A-Z0-9] code (uses secrets)."""
    alphabet = string.ascii_uppercase + string.digits
    conn = get_connection()
    try:
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            row = conn.execute(
                "SELECT 1 FROM users WHERE unique_id = ?", (code,)
            ).fetchone()
            if row is None:
                return code
    finally:
        conn.close()


def create_user(name, age, gender, body_goal, password):
    """
    Insert a new user with a fresh unique_id + UTC timestamp, hashing the
    given password. Returns the id. Only admins create users.
    """
    unique_id = generate_unique_id()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (unique_id, name, age, gender, body_goal, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (unique_id, name, int(age), gender, body_goal,
             generate_password_hash(password), _utc_now_iso()),
        )
        conn.commit()
        return unique_id
    finally:
        conn.close()


def verify_user(unique_id, password):
    """Return the user dict if unique_id/password match, else None."""
    user = get_user(unique_id)
    if user is None or not user.get("password_hash"):
        return None
    if not check_password_hash(user["password_hash"], password or ""):
        return None
    return user


def delete_user(unique_id):
    """
    Permanently delete a user and every record that references them
    (test runs, streaks, preferences). Admin-only action. Returns True if a
    user was actually deleted.
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM test_runs WHERE unique_id = ?", (unique_id,))
        conn.execute("DELETE FROM streaks WHERE unique_id = ?", (unique_id,))
        conn.execute("DELETE FROM user_preferences WHERE unique_id = ?", (unique_id,))
        cur = conn.execute("DELETE FROM users WHERE unique_id = ?", (unique_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================================
# ADMIN ACCOUNTS
# ============================================================================

def create_admin(username, password):
    """Insert a new admin account. Returns True on success, False if the username is taken."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM admins WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), _utc_now_iso()),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def verify_admin_password(password):
    """
    Check a password against every stored admin account (admin login is a
    single shared password field, not username+password). Returns the
    matching admin's username, or None if no admin account matches.
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT username, password_hash FROM admins").fetchall()
        for row in rows:
            if check_password_hash(row["password_hash"], password or ""):
                return row["username"]
        return None
    finally:
        conn.close()


def get_user(unique_id):
    """Return the user's row as a dict, or None if it doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_users():
    """
    Return every registered user as a list of dicts with at least
    'unique_id' and 'name', sorted alphabetically by name.
    Used to populate "existing user" dropdowns (Test / History / Settings)
    so people can pick their account instead of retyping their unique ID.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT unique_id, name FROM users ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_profile(unique_id, name=None, age=None, gender=None, body_goal=None):
    """
    Update any subset of a user's profile fields (name / age / gender /
    body_goal). Only the fields actually passed in are touched, so this
    covers both the "just change my goal" case and a full profile edit.
    Returns True if a row was changed.
    """
    fields = {}
    if name is not None and str(name).strip():
        fields["name"] = str(name).strip()
    if age is not None:
        try:
            fields["age"] = int(age)
        except (TypeError, ValueError):
            pass
    if gender is not None:
        fields["gender"] = gender
    if body_goal is not None:
        fields["body_goal"] = body_goal
    if not fields:
        return False
    conn = get_connection()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [unique_id]
        cur = conn.execute(f"UPDATE users SET {set_clause} WHERE unique_id = ?", values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_goal(unique_id, new_goal):
    """UPDATE the user's goal. Return True if a row changed, else False. Kept as a thin
    convenience wrapper around update_profile for existing call sites."""
    return update_profile(unique_id, body_goal=new_goal)


def set_user_password(unique_id, new_password):
    """Hash and store a new password for an existing user. Returns True if a row changed."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE unique_id = ?",
            (generate_password_hash(new_password), unique_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================================
# GLOBAL APPEARANCE (shared by every account — see app_settings table)
# ============================================================================

def get_appearance():
    """Return the single shared appearance row as a dict."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT theme, font_size, accent_color FROM app_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return {"theme": "light", "font_size": "medium", "accent_color": "#FF3E00"}
        return dict(row)
    finally:
        conn.close()


def update_appearance(theme=None, font_size=None, accent_color=None):
    """Update any subset of the shared theme/font_size/accent_color, for everyone."""
    fields = {}
    if theme is not None:
        fields["theme"] = theme
    if font_size is not None:
        fields["font_size"] = font_size
    if accent_color is not None:
        fields["accent_color"] = accent_color
    if not fields:
        return
    conn = get_connection()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        conn.execute(f"UPDATE app_settings SET {set_clause} WHERE id = 1", values)
        conn.commit()
    finally:
        conn.close()


def _dumps(value):
    """json.dumps a dict/list, or return None untouched."""
    return None if value is None else json.dumps(value)


def insert_test_run(unique_id, tests_included, used_inference,
                    week_start=None, week_end=None,
                    exercise_inputs=None, bmi_height_cm=None, bmi_weight_kg=None,
                    bf_neck_cm=None, bf_waist_cm=None, bf_hip_cm=None,
                    cal_activity_level=None, cal_current_intake=None,
                    exercise_result=None, bmi_result=None, bodyfat_result=None,
                    calorie_result=None, fused_result=None):
    """Insert one row into test_runs, JSON-encoding dict/list args. Returns run_id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO test_runs (
                unique_id, run_at, tests_included, used_inference,
                week_start, week_end,
                exercise_inputs_json, bmi_height_cm, bmi_weight_kg,
                bf_neck_cm, bf_waist_cm, bf_hip_cm,
                cal_activity_level, cal_current_intake,
                exercise_result_json, bmi_result_json, bodyfat_result_json,
                calorie_result_json, fused_result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unique_id, _utc_now_iso(), tests_included, 1 if used_inference else 0,
                week_start or None, week_end or None,
                _dumps(exercise_inputs), bmi_height_cm, bmi_weight_kg,
                bf_neck_cm, bf_waist_cm, bf_hip_cm,
                cal_activity_level, cal_current_intake,
                _dumps(exercise_result), _dumps(bmi_result), _dumps(bodyfat_result),
                _dumps(calorie_result), _dumps(fused_result),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _row_to_run_dict(row):
    """Convert a test_runs sqlite3.Row into a dict, decoding JSON columns."""
    data = dict(row)
    for col in _JSON_COLUMNS:
        if data.get(col) is not None:
            data[col] = json.loads(data[col])
    return data


def get_run(run_id):
    """Fetch one test_runs row by run_id (JSON decoded), or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM test_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_run_dict(row) if row is not None else None
    finally:
        conn.close()


def get_runs_for_user(unique_id):
    """Fetch every test_runs row for a user, most recent first (JSON decoded)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM test_runs WHERE unique_id = ? ORDER BY run_at DESC",
            (unique_id,),
        ).fetchall()
        return [_row_to_run_dict(r) for r in rows]
    finally:
        conn.close()


def get_weeks_for_user(unique_id):
    """
    Return one row per distinct logged week (week_start/week_end) for this
    user, using the most recent run for that week if it was submitted more
    than once. Ordered most-recent week first. Used to power the "autofill
    from a previous week" dropdown on the Test page. Runs with no week
    selected (week_start IS NULL) are excluded — there's nothing to key
    them by.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t1.* FROM test_runs t1
            INNER JOIN (
                SELECT week_start, week_end, MAX(run_id) AS max_run_id
                FROM test_runs
                WHERE unique_id = ? AND week_start IS NOT NULL
                GROUP BY week_start, week_end
            ) latest ON t1.run_id = latest.max_run_id
            WHERE t1.unique_id = ?
            ORDER BY t1.week_start DESC
            """,
            (unique_id, unique_id),
        ).fetchall()
        return [_row_to_run_dict(r) for r in rows]
    finally:
        conn.close()


# ============================================================================
# STREAKS
# ============================================================================

def checkin_streak(unique_id, date_iso=None):
    """
    Mark a date as checked-in (user took a test that day).
    If date_iso is None, uses today. Returns the streak record dict.
    """
    if date_iso is None:
        date_iso = _iso_date_today()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO streaks (unique_id, date, checked_in, created_at) "
            "VALUES (?, ?, 1, ?)",
            (unique_id, date_iso, _utc_now_iso()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM streaks WHERE unique_id = ? AND date = ?",
            (unique_id, date_iso),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_current_streak(unique_id):
    """
    Compute the user's current streak (consecutive days ending today, counting backwards).
    Returns {'current': N, 'best': M} where N is consecutive days to today, M is best all-time.
    """
    conn = get_connection()
    try:
        today = _iso_date_today()
        # Get all checked-in dates, sorted DESC (most recent first).
        rows = conn.execute(
            "SELECT date FROM streaks WHERE unique_id = ? AND checked_in = 1 ORDER BY date DESC",
            (unique_id,),
        ).fetchall()
        dates = [r["date"] for r in rows]
        if not dates:
            return {"current": 0, "best": 0}
        # Compute current streak (consecutive from today backwards).
        current_streak = 0
        from datetime import timedelta
        check_date = datetime.fromisoformat(today).date()
        for d in dates:
            d_date = datetime.fromisoformat(d).date()
            if d_date == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        # Compute best streak (max consecutive run).
        best_streak = 1 if dates else 0
        run_length = 1
        for i in range(1, len(dates)):
            prev_date = datetime.fromisoformat(dates[i - 1]).date()
            curr_date = datetime.fromisoformat(dates[i]).date()
            if (prev_date - curr_date).days == 1:
                run_length += 1
                best_streak = max(best_streak, run_length)
            else:
                run_length = 1
        return {"current": current_streak, "best": best_streak}
    finally:
        conn.close()


def get_streak_dates(unique_id, days_back=30):
    """Fetch all check-in dates in the last N days. Returns list of ISO date strings."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date FROM streaks WHERE unique_id = ? AND checked_in = 1 "
            "ORDER BY date DESC LIMIT ?",
            (unique_id, days_back),
        ).fetchall()
        return [r["date"] for r in rows]
    finally:
        conn.close()


# ============================================================================
# USER PREFERENCES
# ============================================================================

def get_preferences(unique_id):
    """Fetch user's theme and avg measurements. Returns dict or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


_TEXT_PREF_FIELDS = ("theme", "avg_activity_level", "font_size", "accent_color")


def update_preferences(unique_id, theme=None, avg_height_cm=None, avg_weight_kg=None,
                       avg_neck_cm=None, avg_waist_cm=None, avg_hip_cm=None,
                       avg_activity_level=None, avg_current_intake=None,
                       avg_exercise_sets_total=None, font_size=None, accent_color=None):
    """Update user's preferences. Creates row if it doesn't exist."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM user_preferences WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        if existing:
            updates = []
            params = []
            for name, val in [
                ("theme", theme), ("avg_height_cm", avg_height_cm),
                ("avg_weight_kg", avg_weight_kg), ("avg_neck_cm", avg_neck_cm),
                ("avg_waist_cm", avg_waist_cm), ("avg_hip_cm", avg_hip_cm),
                ("avg_activity_level", avg_activity_level), ("avg_current_intake", avg_current_intake),
                ("avg_exercise_sets_total", avg_exercise_sets_total),
                ("font_size", font_size), ("accent_color", accent_color),
            ]:
                if val is not None:
                    updates.append(f"{name} = ?")
                    params.append(val if name in _TEXT_PREF_FIELDS else float(val))
            if updates:
                updates.append("updated_at = ?")
                params.append(_utc_now_iso())
                params.append(unique_id)
                conn.execute(
                    f"UPDATE user_preferences SET {', '.join(updates)} WHERE unique_id = ?",
                    params,
                )
        else:
            conn.execute(
                "INSERT INTO user_preferences "
                "(unique_id, theme, avg_height_cm, avg_weight_kg, avg_neck_cm, avg_waist_cm, "
                "avg_hip_cm, avg_activity_level, avg_current_intake, avg_exercise_sets_total, "
                "font_size, accent_color, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (unique_id, theme or "light", avg_height_cm, avg_weight_kg, avg_neck_cm, avg_waist_cm,
                 avg_hip_cm, avg_activity_level, avg_current_intake, avg_exercise_sets_total,
                 font_size or "medium", accent_color or "#FF3E00", _utc_now_iso()),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Sanity check: create tables and report.
    get_connection().close()
    print(f"Database ready at {config.DB_PATH}")
