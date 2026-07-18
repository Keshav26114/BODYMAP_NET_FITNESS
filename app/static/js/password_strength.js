/**
 * password_strength.js — live checklist under any "new password" field
 * marked with data-pw-policy="1", showing which of the site's password
 * requirements are currently met as the person types.
 *
 * This is a convenience for the person typing, not the actual enforcement
 * -- the real check happens server-side in config.validate_password_policy()
 * on every route that sets a password, so this list is intentionally kept
 * in sync with that function's rules:
 *   - at least 8 characters
 *   - at least one uppercase letter
 *   - at least one lowercase letter
 *   - at least one special (non-alphanumeric) symbol
 */
(function () {
    "use strict";

    var RULES = [
        { key: "length", label: "At least 8 characters", test: function (v) { return v.length >= 8; } },
        { key: "upper", label: "One uppercase letter (A-Z)", test: function (v) { return /[A-Z]/.test(v); } },
        { key: "lower", label: "One lowercase letter (a-z)", test: function (v) { return /[a-z]/.test(v); } },
        { key: "special", label: "One special symbol (!@#$...)", test: function (v) { return /[^A-Za-z0-9]/.test(v); } },
    ];

    function wire(input) {
        if (input.dataset.pwPolicyWired) return;
        input.dataset.pwPolicyWired = "1";

        var list = document.createElement("ul");
        list.className = "pw-policy-checklist";
        RULES.forEach(function (rule) {
            var item = document.createElement("li");
            item.dataset.rule = rule.key;
            item.textContent = rule.label;
            list.appendChild(item);
        });

        // Insert right after the field's wrapper (password_toggle.js wraps
        // every password input in a .pw-field div) so it sits directly
        // under the visible field regardless of load order.
        var host = input.closest(".pw-field") || input;
        host.parentNode.insertBefore(list, host.nextSibling);

        function update() {
            var value = input.value || "";
            RULES.forEach(function (rule) {
                var item = list.querySelector('li[data-rule="' + rule.key + '"]');
                if (item) item.classList.toggle("pw-policy-checklist__item--met", rule.test(value));
            });
        }

        input.addEventListener("input", update);
        update();
    }

    function wireAll() {
        document.querySelectorAll("input[data-pw-policy]").forEach(wire);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wireAll);
    } else {
        wireAll();
    }
})();
