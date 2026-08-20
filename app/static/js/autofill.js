/**
 * Auto-fill helper: load saved averages, populate exercise with 0 sets, and save on blur.
 */

/**
 * Get saved preferences from html data attributes (set by backend in base.html).
 */
function getSavedPreferences() {
  const htmlElement = document.documentElement;
  return {
    avg_height_cm: htmlElement.dataset.avgHeightCm ? parseFloat(htmlElement.dataset.avgHeightCm) : null,
    avg_weight_kg: htmlElement.dataset.avgWeightKg ? parseFloat(htmlElement.dataset.avgWeightKg) : null,
    avg_neck_cm: htmlElement.dataset.avgNeckCm ? parseFloat(htmlElement.dataset.avgNeckCm) : null,
    avg_waist_cm: htmlElement.dataset.avgWaistCm ? parseFloat(htmlElement.dataset.avgWaistCm) : null,
    avg_hip_cm: htmlElement.dataset.avgHipCm ? parseFloat(htmlElement.dataset.avgHipCm) : null,
    avg_activity_level: htmlElement.dataset.avgActivityLevel || null,
    avg_current_intake: htmlElement.dataset.avgCurrentIntake ? parseFloat(htmlElement.dataset.avgCurrentIntake) : null,
    avg_exercise_sets_total: htmlElement.dataset.avgExerciseSetsTotal ? parseFloat(htmlElement.dataset.avgExerciseSetsTotal) : null,
  };
}

/**
 * Load saved averages into form fields (via data-prefs-field attribute).
 */
function loadSavedAverages() {
  const prefs = getSavedPreferences();
  
  document.querySelectorAll('[data-prefs-field]').forEach(function (field) {
    const prefKey = field.dataset.prefsField;
    const savedValue = prefs[prefKey];
    
    if (savedValue !== null && savedValue !== undefined) {
      if (field.tagName === 'SELECT') {
        field.value = savedValue;
      } else {
        field.value = savedValue;
        field.placeholder = `e.g. ${savedValue.toFixed(0) || savedValue} (your avg)`;
      }
    }
  });
}

/**
 * Auto-fill all exercise inputs with 0 sets when exercise test is selected.
 */
function initExerciseAutofill() {
  const exerciseCheckbox = document.getElementById('chk_exercise');
  const exerciseSection = document.querySelector('.test-section[data-test="exercise"]');
  
  if (!exerciseCheckbox || !exerciseSection) return;
  
  exerciseCheckbox.addEventListener('change', function () {
    if (this.checked) {
      // Populate all exercise inputs with 0
      document.querySelectorAll('.ex-sets-input').forEach(function (inp) {
        if (!inp.value || inp.value === '') {
          inp.value = 0;
        }
      });
    }
  });
}

/**
 * Save measurements to server on blur (auto-save averages).
 */
function initAutoSave() {
  const uniqueId = document.querySelector('input[name="unique_id"]');
  if (!uniqueId) return;
  
  const userId = uniqueId.value;
  
  // Save measurement fields on blur
  const measurementFields = ['bmi_height_cm', 'bmi_weight_kg', 'bf_neck_cm', 'bf_waist_cm', 'bf_hip_cm', 'cal_current_intake'];
  
  measurementFields.forEach(function (fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
      field.addEventListener('blur', function () {
        if (this.value) {
          const prefField = this.dataset.prefsField;
          if (prefField) {
            const data = {};
            data[prefField] = this.value;
            
            // Send to server
            fetch('/settings/avg-measurements', {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: 'unique_id=' + userId + '&' + prefField + '=' + this.value,
            }).catch(function (err) {
              console.log('[v0] Auto-save failed (non-critical):', err);
            });
          }
        }
      });
    }
  });
  
  // Save activity level on change
  const activityField = document.getElementById('cal_activity_level');
  if (activityField) {
    activityField.addEventListener('change', function () {
      fetch('/settings/avg-measurements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'unique_id=' + userId + '&avg_activity_level=' + this.value,
      }).catch(function (err) {
        console.log('[v0] Auto-save activity failed (non-critical):', err);
      });
    });
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
  loadSavedAverages();
  initExerciseAutofill();
  initAutoSave();
});
