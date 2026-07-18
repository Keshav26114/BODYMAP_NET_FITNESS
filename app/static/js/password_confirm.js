/**
 * password_confirm.js — wires up any "confirm password" field marked with
 * data-match="<id-of-original-password-field>" so the browser flags a
 * mismatch (via the native validity API) before the form can submit.
 * The server re-checks the match too — this is just for fast feedback.
 */
(function () {
    "use strict";

    function wire(confirmField) {
        var targetId = confirmField.dataset.match;
        var target = targetId && document.getElementById(targetId);
        if (!target) return;

        function check() {
            if (target.value && confirmField.value && target.value !== confirmField.value) {
                confirmField.setCustomValidity("Passwords do not match.");
            } else {
                confirmField.setCustomValidity("");
            }
        }

        confirmField.addEventListener("input", check);
        target.addEventListener("input", check);
    }

    function wireAll() {
        document.querySelectorAll("[data-match]").forEach(wire);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wireAll);
    } else {
        wireAll();
    }
})();
