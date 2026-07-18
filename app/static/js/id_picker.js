/**
 * id_picker.js — turns any ".id-picker" block into a dropdown of existing
 * users (rendered server-side as "<unique_id> - <name>") with a fallback
 * link to type a unique ID manually. Only the currently-visible control
 * carries the "unique_id" name attribute, so the form still posts a single
 * clean value either way.
 */
(function () {
  "use strict";

  function setupIdPicker(root) {
    var select = root.querySelector(".id-picker__select");
    var manualInput = root.querySelector(".id-picker__manual-input");
    var toggleBtn = root.querySelector(".id-picker__toggle");
    if (!select || !manualInput || !toggleBtn) return;

    function showManual() {
      select.hidden = true;
      select.disabled = true;
      select.removeAttribute("name");
      manualInput.hidden = false;
      manualInput.disabled = false;
      manualInput.setAttribute("name", "unique_id");
      toggleBtn.textContent = "Choose from the list instead";
    }

    function showSelect() {
      select.hidden = false;
      select.disabled = false;
      select.setAttribute("name", "unique_id");
      manualInput.hidden = true;
      manualInput.disabled = true;
      manualInput.removeAttribute("name");
      toggleBtn.textContent = "Enter ID manually instead";
    }

    toggleBtn.addEventListener("click", function () {
      if (select.hidden) {
        showSelect();
      } else {
        showManual();
      }
    });

    // No accounts yet — go straight to manual entry.
    if (select.options.length <= 1) {
      showManual();
      toggleBtn.hidden = true;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".id-picker").forEach(setupIdPicker);
  });
})();
