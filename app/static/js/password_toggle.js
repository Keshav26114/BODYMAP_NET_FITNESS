/**
 * password_toggle.js — progressive enhancement that adds a small eye-icon
 * button next to every password input on the page, so people can check
 * what they've typed (e.g. while creating a user or setting a new
 * password) without actually storing or exposing anything server-side.
 */
(function () {
    "use strict";

    // Two small inline SVGs (open eye / eye with a slash) so the toggle
    // doesn't depend on an external icon font or CDN.
    var EYE_OPEN =
        '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/>' +
        '<circle cx="12" cy="12" r="3"/></svg>';
    var EYE_CLOSED =
        '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a20.3 20.3 0 0 1 4.22-5.94M9.9 4.24A10.4 10.4 0 0 1 12 4c7 0 11 8 11 8a20.3 20.3 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"/>' +
        '<path d="M1 1l22 22"/></svg>';

    function wire(input) {
        if (input.dataset.pwWired) return;
        input.dataset.pwWired = "1";

        var wrapper = document.createElement("div");
        wrapper.className = "pw-field";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pw-toggle-btn";
        btn.innerHTML = EYE_OPEN;
        btn.setAttribute("aria-label", "Show password");
        wrapper.appendChild(btn);

        btn.addEventListener("click", function () {
            var showing = input.type === "text";
            input.type = showing ? "password" : "text";
            btn.innerHTML = showing ? EYE_OPEN : EYE_CLOSED;
            btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        });
    }

    function wireAll() {
        document.querySelectorAll("input[type='password']").forEach(wire);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wireAll);
    } else {
        wireAll();
    }

    // Exposed in case a page injects password fields dynamically later
    // (e.g. the login modal, which is always present in the DOM already,
    // but doesn't hurt to allow re-wiring after any future DOM changes).
    window.wirePasswordToggles = wireAll;
})();
