/**
 * login.js — opens/closes the top-corner login modal and switches between
 * its "Login as User" / "Login as Admin" panels. Only present on pages
 * where nobody is logged in yet (base.html only renders the modal then).
 */
(function () {
    "use strict";

    var openBtn = document.getElementById("headerLoginBtn");
    var overlay = document.getElementById("loginOverlay");
    var closeBtn = document.getElementById("loginCloseBtn");
    if (!overlay) return; // already logged in — nothing to wire up

    function openModal() {
        overlay.hidden = false;
    }
    function closeModal() {
        overlay.hidden = true;
    }

    if (openBtn) openBtn.addEventListener("click", openModal);
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closeModal();
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !overlay.hidden) closeModal();
    });

    var tabs = overlay.querySelectorAll(".login-tab");
    var panels = overlay.querySelectorAll(".login-panel");

    function activateTab(name) {
        tabs.forEach(function (t) {
            var active = t.dataset.panel === name;
            t.classList.toggle("is-active", active);
            t.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (p) {
            p.hidden = p.dataset.panel !== name;
        });
    }

    var initialTab = overlay.dataset.initialTab || "user";
    if (initialTab === "admin") activateTab("admin");

    // If the server just flashed a login error/success message, pop the
    // modal open automatically (on the relevant tab) so it's visible.
    var params = new URLSearchParams(window.location.search);
    if (overlay.querySelector(".notice") || params.has("tab")) openModal();

    tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            activateTab(tab.dataset.panel);
        });
    });
})();
