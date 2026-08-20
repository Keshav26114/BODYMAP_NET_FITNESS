/**
 * Advanced dynamic validators with context-aware thresholds.
 * RED/YELLOW/GREEN indicators adjust based on entered values and health ratios.
 */

// Static thresholds from config
const THRESHOLDS = {
  bmi_weight_kg: { low_red: 35, low_yellow: 45, high_yellow: 100, high_red: 130 },
  bmi_height_cm: { low_red: 140, low_yellow: 140, high_yellow: 210, high_red: 230 },
  bf_neck_cm: { low_red: 25, low_yellow: 30, high_yellow: 45, high_red: 55 },
  bf_waist_cm: { low_red: 55, low_yellow: 65, high_yellow: 110, high_red: 140 },
  bf_hip_cm: { low_red: 60, low_yellow: 70, high_yellow: 120, high_red: 150 },
  cal_current_intake: { low_red: 900, low_yellow: 1200, high_yellow: 3500, high_red: 4500 },
};

// Healthy BMI range: 18.5 to 25
const BMI_HEALTHY_MIN = 18.5;
const BMI_HEALTHY_MAX = 25;

// Exercise baselines per group — WEEKLY totals (sum of per-exercise baselines
// from config.py). Resistance-training groups are calibrated to a realistic
// 12-36 sets/week per body part (roughly 10-20 sets/muscle/week to maintain
// or grow, up to ~25-36 for advanced/high-frequency training).
// Cardio is kept on the SAME small "sessions/week" scale as every other
// group (baseline 1 per activity, 5 total) rather than raw minutes, so a
// normal cardio week can no longer display as an impossible "202 sets".
// Shoulder: 3+4+4+3+4=18   Chest: 4+4+4+6+4=22   Triceps: 3+3+3+3+3=15
// Biceps: 3+3+3+3+3=15     Abs: 3+10+2+2+3=20 (plank counted in sets)
// Quads: 5+7+5+4+3=24      Hamstrings: 5+3+3+2+3=16
// Calves: 6+5+4+1=16       Cardio (sessions): 1+1+1+1+1=5
const EXERCISE_GROUP_BASELINES = {
  "Shoulder":    18,
  "Chest":       22,
  "Triceps":     15,
  "Biceps":      15,
  "Abs":         20,
  "Quads":       24,
  "Hamstrings":  16,
  "Calves":      16,
  "Cardio":      5,
};

/**
 * Calculate healthy weight range given height in cm.
 * Uses BMI range 18.5-25 (normal weight).
 */
function getHealthyWeightRange(heightCm) {
  if (!heightCm || heightCm < 140 || heightCm > 230) return null;
  const heightM = heightCm / 100;
  const minWeight = BMI_HEALTHY_MIN * (heightM * heightM);
  const maxWeight = BMI_HEALTHY_MAX * (heightM * heightM);
  return { min: minWeight, max: maxWeight };
}

/**
 * Validate BMI height (always required, dynamic weight thresholds).
 * Height RED if <140 or >230, YELLOW if <150 or >220, GREEN otherwise.
 */
function validateBmiHeight(heightCm) {
  if (!heightCm) return { status: 'red', msg: 'Height is required' };
  if (heightCm < 140 || heightCm > 230) return { status: 'red', msg: 'Height out of safe range (140-230 cm)' };
  if (heightCm < 150 || heightCm > 220) return { status: 'yellow', msg: 'Height slightly outside normal range' };
  return { status: 'green', msg: 'Height is healthy' };
}

/**
 * Validate BMI weight based on entered height (dynamic thresholds).
 * Calculates healthy range from height and compares weight.
 */
function validateBmiWeight(weightKg, heightCm) {
  if (!weightKg) return { status: null, msg: '' }; // Optional, no status
  
  const range = getHealthyWeightRange(heightCm);
  if (!range) return { status: 'yellow', msg: 'Invalid height, cannot compute range' };
  
  if (weightKg < range.min - 5 || weightKg > range.max + 5) {
    return { status: 'red', msg: `Weight outside safe range for your height (${range.min.toFixed(0)}-${range.max.toFixed(0)} kg)` };
  }
  if (weightKg < range.min || weightKg > range.max) {
    return { status: 'yellow', msg: `Weight slightly outside healthy range (${range.min.toFixed(0)}-${range.max.toFixed(0)} kg)` };
  }
  return { status: 'green', msg: 'Weight is healthy for your height' };
}

/**
 * Validate body fat measurements (context-aware based on gender).
 * Larger measurements relative to baseline = yellow/red.
 */
function validateBodyfatMeasurement(fieldName, valueCm, gender) {
  if (!valueCm) return { status: null, msg: '' }; // Optional
  
  const thresholds = THRESHOLDS[fieldName];
  if (!thresholds) return { status: null, msg: '' };
  
  if (valueCm <= thresholds.low_red || valueCm >= thresholds.high_red) {
    return { status: 'red', msg: `${fieldName}: critically outside healthy range` };
  }
  if (valueCm <= thresholds.low_yellow || valueCm >= thresholds.high_yellow) {
    return { status: 'yellow', msg: `${fieldName}: slightly elevated` };
  }
  return { status: 'green', msg: `${fieldName}: healthy` };
}

/**
 * Validate exercise sets dynamically against baseline.
 * If total group sets are <50% of baseline: GREEN, 50-80%: YELLOW, >80%: GREEN, >150%: RED.
 */
function validateExerciseSets(groupKey, inputSets, baseline) {
  if (inputSets === null || inputSets === undefined || inputSets === '') {
    return { status: null, msg: '' }; // Not filled
  }
  
  const sets = parseFloat(inputSets);
  if (isNaN(sets) || sets < 0) return { status: 'red', msg: 'Invalid sets' };
  
  if (sets === 0) return { status: null, msg: '' }; // Empty is OK (not required)
  
  const ratio = sets / baseline;
  if (ratio < 0.5) {
    return { status: 'yellow', msg: `${groupKey}: light activity (${(ratio * 100).toFixed(0)}% of baseline)` };
  }
  if (ratio > 1.5) {
    return { status: 'red', msg: `${groupKey}: excessive volume (${(ratio * 100).toFixed(0)}% of baseline) - risk of overtraining` };
  }
  if (ratio > 1.2) {
    return { status: 'yellow', msg: `${groupKey}: high volume (${(ratio * 100).toFixed(0)}% of baseline)` };
  }
  return { status: 'green', msg: `${groupKey}: optimal volume` };
}

/**
 * Validate calorie intake based on activity level and entered values.
 */
function validateCalorieIntake(valueCal) {
  if (!valueCal) return { status: null, msg: '' };
  
  const thresholds = THRESHOLDS.cal_current_intake;
  if (valueCal <= thresholds.low_red || valueCal >= thresholds.high_red) {
    return { status: 'red', msg: 'Calorie intake critically unhealthy' };
  }
  if (valueCal <= thresholds.low_yellow || valueCal >= thresholds.high_yellow) {
    return { status: 'yellow', msg: 'Calorie intake slightly high/low' };
  }
  return { status: 'green', msg: 'Calorie intake is healthy' };
}

/**
 * Initialize validators on all fields with data-validator attribute.
 */
function initValidators() {
  document.querySelectorAll('[data-validator]').forEach(function (field) {
    const validatorType = field.dataset.validator;
    
    if (validatorType === 'bmi_height_cm') {
      field.addEventListener('input', function () {
        updateBmiValidators();
      });
      // Initial validation
      updateBmiValidators();
    } else if (validatorType === 'bmi_weight_kg') {
      field.addEventListener('input', function () {
        updateBmiValidators();
      });
    } else if (validatorType === 'bf_neck_cm' || validatorType === 'bf_waist_cm' || validatorType === 'bf_hip_cm') {
      field.addEventListener('input', function () {
        const gender = field.dataset.gender || 'male';
        updateBodyfatValidator(validatorType, gender);
      });
    } else if (validatorType === 'cal_current_intake') {
      field.addEventListener('input', function () {
        updateCalorieValidator();
      });
    } else if (validatorType === 'exercise_sets') {
      field.addEventListener('input', function () {
        updateExerciseValidator(field);
      });
    }
  });
}

/**
 * Update both BMI validators (height and weight interdependent).
 */
function updateBmiValidators() {
  const heightField = document.getElementById('bmi_height_cm');
  const weightField = document.getElementById('bmi_weight_kg');
  const heightStatus = document.getElementById('status_bmi_height_cm');
  const weightStatus = document.getElementById('status_bmi_weight_kg');
  
  const height = heightField ? parseFloat(heightField.value) : null;
  const weight = weightField ? parseFloat(weightField.value) : null;
  
  // Validate height
  if (heightStatus && height !== null) {
    const result = validateBmiHeight(height);
    setStatusIndicator(heightStatus, result.status, result.msg);
  }
  
  // Validate weight (depends on height)
  if (weightStatus && weight !== null) {
    const result = validateBmiWeight(weight, height);
    setStatusIndicator(weightStatus, result.status, result.msg);
  }
}

/**
 * Update body fat validator for a specific field.
 */
function updateBodyfatValidator(fieldId, gender) {
  const field = document.getElementById(fieldId);
  const statusElement = document.getElementById('status_' + fieldId);
  
  if (!field || !statusElement) return;
  
  const value = parseFloat(field.value);
  const result = validateBodyfatMeasurement(fieldId, value, gender);
  setStatusIndicator(statusElement, result.status, result.msg);
}

/**
 * Update calorie validator.
 */
function updateCalorieValidator() {
  const field = document.getElementById('cal_current_intake');
  const statusElement = document.getElementById('status_cal_current_intake');
  
  if (!field || !statusElement) return;
  
  const value = parseFloat(field.value);
  const result = validateCalorieIntake(value);
  setStatusIndicator(statusElement, result.status, result.msg);
}

/**
 * Update exercise validator for a single exercise field.
 * Aggregates all exercises in the same group and validates against baseline.
 */
function updateExerciseValidator(field) {
  const groupKey = field.dataset.group.replace(/_/g, ' ');
  const baseline = EXERCISE_GROUP_BASELINES[groupKey] || 10;
  
  // Sum all exercises in this group
  const groupInputs = document.querySelectorAll(`.ex-sets-input[data-group="${field.dataset.group}"]`);
  let totalSets = 0;
  groupInputs.forEach(function (inp) {
    const val = parseFloat(inp.value);
    if (!isNaN(val) && val > 0) totalSets += val;
  });
  
  // Get or create status badge for this group (appears on first exercise)
  let statusElement = document.getElementById('status_exercise_group_' + field.dataset.group);
  if (!statusElement && groupInputs.length > 0) {
    statusElement = document.createElement('span');
    statusElement.id = 'status_exercise_group_' + field.dataset.group;
    statusElement.className = 'field-status';
    groupInputs[0].parentElement.appendChild(statusElement);
  }
  
  if (statusElement && totalSets > 0) {
    const result = validateExerciseSets(groupKey, totalSets, baseline);
    setStatusIndicator(statusElement, result.status, result.msg);
  }
}

/**
 * Set the visual status indicator (red/yellow/green circle) and tooltip.
 */
function setStatusIndicator(element, status, message) {
  element.className = 'field-status';
  element.title = message || '';
  
  if (status === 'red') {
    element.classList.add('field-status--red');
  } else if (status === 'yellow') {
    element.classList.add('field-status--yellow');
  } else if (status === 'green') {
    element.classList.add('field-status--green');
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initValidators);

// Re-validate when test sections toggle
document.addEventListener('change', function (e) {
  if (e.target && e.target.classList.contains('test-toggle')) {
    setTimeout(initValidators, 100);
  }
});
