/**
 * week_autofill.js — lets a returning user pick one of their previously
 * filled-in weeks from a dropdown and have that week's answers (exercise
 * sets + any measurements) copied straight into the current test form,
 * instead of retyping everything.
 *
 * Data source: a <script type="application/json" id="weeksAutofillData">
 * tag rendered server-side in test.html (see app.py:_build_week_autofill_data).
 */

var TEST_LABELS = {
  exercise: "Exercise",
  bmi: "BMI",
  bodyfat: "Body Fat",
  calories: "Calories",
};

function formatWeekLabel(week) {
  function fmt(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  var range = fmt(week.week_start) + " \u2013 " + fmt(week.week_end);
  var testNames = (week.tests_included || [])
    .map(function (t) { return TEST_LABELS[t] || t; })
    .filter(Boolean);
  return testNames.length ? range + " \u00b7 " + testNames.join(", ") : range;
}

/**
 * Sets a form field's value if the element exists, without clobbering it
 * with null/undefined.
 */
function setFieldValue(id, value) {
  if (value === null || value === undefined) return false;
  var el = document.getElementById(id);
  if (!el) return false;
  el.value = value;
  return true;
}

/**
 * Ticks a "run this test" checkbox and fires its change handler so the
 * matching test-section reveals itself, same as if the user had clicked it.
 */
function checkAndReveal(checkboxId) {
  var chk = document.getElementById(checkboxId);
  if (!chk) return;
  chk.checked = true;
  chk.dispatchEvent(new Event("change"));
}

function applyWeekToForm(week) {
  // Exercise sets — raw keys look like "<exercise_id>_sets", matching the
  // "ex_<exercise_id>" input ids used in the form.
  if (week.exercise && Object.keys(week.exercise).length) {
    checkAndReveal("chk_exercise");
    var touchedGroups = {};
    Object.keys(week.exercise).forEach(function (rawKey) {
      var exerciseId = rawKey.replace(/_sets$/, "");
      var input = document.getElementById("ex_" + exerciseId);
      if (input) {
        input.value = week.exercise[rawKey];
        if (input.dataset.group) touchedGroups[input.dataset.group] = true;
      }
    });
    // Refresh each affected muscle-group's live "N sets" counter.
    Object.keys(touchedGroups).forEach(function (groupKey) {
      if (typeof updateGroupTotal === "function") updateGroupTotal(groupKey);
    });
  }

  // BMI
  if (week.bmi_height_cm !== undefined || week.bmi_weight_kg !== undefined) {
    checkAndReveal("chk_bmi");
    setFieldValue("bmi_height_cm", week.bmi_height_cm);
    setFieldValue("bmi_weight_kg", week.bmi_weight_kg);
  }

  // Body fat
  if (week.bf_neck_cm !== undefined || week.bf_waist_cm !== undefined || week.bf_hip_cm !== undefined) {
    checkAndReveal("chk_bodyfat");
    setFieldValue("bf_neck_cm", week.bf_neck_cm);
    setFieldValue("bf_waist_cm", week.bf_waist_cm);
    setFieldValue("bf_hip_cm", week.bf_hip_cm);
  }

  // Calories
  if (week.cal_activity_level !== undefined || week.cal_current_intake !== undefined) {
    checkAndReveal("chk_calories");
    setFieldValue("cal_activity_level", week.cal_activity_level);
    setFieldValue("cal_current_intake", week.cal_current_intake);
  }

  if (typeof updateFusionState === "function") updateFusionState();
}

function initWeekAutofill() {
  var dataEl = document.getElementById("weeksAutofillData");
  var select = document.getElementById("autofillWeekSelect");
  var clearBtn = document.getElementById("autofillClear");
  if (!dataEl || !select) return;

  var weeks;
  try {
    weeks = JSON.parse(dataEl.textContent || "[]");
  } catch (err) {
    console.log("[v0] Could not parse weeks autofill data:", err);
    return;
  }
  if (!Array.isArray(weeks) || weeks.length === 0) return;

  weeks.forEach(function (week, idx) {
    var opt = document.createElement("option");
    opt.value = String(idx);
    opt.textContent = formatWeekLabel(week);
    select.appendChild(opt);
  });

  select.addEventListener("change", function () {
    if (select.value === "") {
      if (clearBtn) clearBtn.hidden = true;
      return;
    }
    var week = weeks[parseInt(select.value, 10)];
    if (week) applyWeekToForm(week);
    if (clearBtn) clearBtn.hidden = false;
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      select.value = "";
      clearBtn.hidden = true;
    });
  }
}

document.addEventListener("DOMContentLoaded", initWeekAutofill);
