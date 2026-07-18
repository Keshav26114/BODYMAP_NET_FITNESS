CREATE TABLE IF NOT EXISTS users (
    unique_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    age            INTEGER NOT NULL,
    gender         TEXT NOT NULL,          -- 'male' | 'female' | 'other'
    body_goal      TEXT NOT NULL,          -- one of config.BODY_GOALS values
    password_hash  TEXT,                   -- set on creation; required to log in as this user
    created_at     TEXT NOT NULL
);

-- Site-wide appearance (theme / font size / accent color). Single row,
-- shared by every visitor regardless of account — changing it in Settings
-- (by any user or admin) updates the look for everyone.
CREATE TABLE IF NOT EXISTS app_settings (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    theme         TEXT NOT NULL DEFAULT 'light',
    font_size     TEXT NOT NULL DEFAULT 'medium',
    accent_color  TEXT NOT NULL DEFAULT '#FF3E00'
);
-- Admin accounts. Seeded on first run with username "admin" / password
-- "keshav100" (see db/database.py::_ensure_default_admin). Additional admin
-- accounts can be created from the "Login as Admin" panel.
CREATE TABLE IF NOT EXISTS admins (
    admin_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id        TEXT NOT NULL REFERENCES users(unique_id),
    run_at           TEXT NOT NULL,
    tests_included   TEXT NOT NULL,     -- comma list, e.g. "exercise,bmi"
    used_inference   INTEGER NOT NULL,  -- 0 or 1

    week_start       TEXT,              -- ISO date (YYYY-MM-DD), Monday of the logged week (or NULL)
    week_end         TEXT,              -- ISO date (YYYY-MM-DD), Sunday of the logged week (or NULL)

    exercise_inputs_json  TEXT,         -- JSON dict of the 44 raw exercise inputs (or NULL if skipped)
    bmi_height_cm         REAL,
    bmi_weight_kg         REAL,
    bf_neck_cm            REAL,
    bf_waist_cm           REAL,
    bf_hip_cm             REAL,
    cal_activity_level    TEXT,
    cal_current_intake    REAL,

    exercise_result_json  TEXT,         -- {"label":..., "confidence":..., "group_scores": {...}}
    bmi_result_json       TEXT,
    bodyfat_result_json   TEXT,
    calorie_result_json   TEXT,
    fused_result_json     TEXT          -- {"archetype":..., "confidence":..., "embedding_2d": [x, y]}
);

CREATE INDEX IF NOT EXISTS idx_test_runs_unique_id ON test_runs(unique_id);

CREATE TABLE IF NOT EXISTS streaks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id       TEXT NOT NULL REFERENCES users(unique_id),
    date            TEXT NOT NULL,                -- ISO date (YYYY-MM-DD)
    checked_in      INTEGER NOT NULL DEFAULT 0,  -- 0 or 1 (whether user tested on this date)
    created_at      TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_streaks_user_date ON streaks(unique_id, date);

CREATE TABLE IF NOT EXISTS user_preferences (
    unique_id           TEXT PRIMARY KEY REFERENCES users(unique_id),
    theme               TEXT NOT NULL DEFAULT 'light',  -- 'light' or 'dark'

    -- Appearance / visual preferences
    font_size           TEXT NOT NULL DEFAULT 'medium', -- 'small' | 'medium' | 'large'
    accent_color        TEXT NOT NULL DEFAULT '#FF3E00', -- hex color, overrides the brand accent
    
    -- BMI averages
    avg_height_cm       REAL,
    avg_weight_kg       REAL,
    
    -- Body Fat averages
    avg_neck_cm         REAL,
    avg_waist_cm        REAL,
    avg_hip_cm          REAL,
    
    -- Calorie averages
    avg_activity_level  TEXT,
    avg_current_intake  REAL,
    
    -- Exercise baseline (sum of all group sets from last test or historical)
    avg_exercise_sets_total REAL,
    
    updated_at          TEXT NOT NULL
);
