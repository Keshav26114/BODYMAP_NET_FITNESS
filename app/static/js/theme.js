/**
 * theme.js — Light/Dark theme switcher with LocalStorage persistence.
 * Saves preference to server and syncs across tabs.
 */

const THEME = {
  LIGHT: "light",
  DARK: "dark",
};

class ThemeManager {
  constructor() {
    this.currentTheme = this.getStoredTheme() || THEME.LIGHT;
    this.initializeTheme();
    this.setupListeners();
  }

  getStoredTheme() {
    return localStorage.getItem("bodymap_theme");
  }

  setStoredTheme(theme) {
    localStorage.setItem("bodymap_theme", theme);
  }

  applyTheme(theme) {
    const html = document.documentElement;
    html.setAttribute("data-theme", theme);
    this.currentTheme = theme;
    this.setStoredTheme(theme);
    
    // Update toggle button if it exists
    const toggle = document.getElementById("theme_toggle");
    if (toggle) {
      toggle.checked = theme === THEME.DARK;
    }

    // Notify server if user is logged in (optional)
    this.syncThemeToServer(theme);
  }

  initializeTheme() {
    // Check if user has a preference in their profile, otherwise use localStorage
    const prefTheme = document.documentElement.getAttribute("data-user-theme");
    const theme = prefTheme || this.currentTheme;
    this.applyTheme(theme);
  }

  setupListeners() {
    const toggle = document.getElementById("theme_toggle");
    if (toggle) {
      toggle.addEventListener("change", () => {
        const newTheme = toggle.checked ? THEME.DARK : THEME.LIGHT;
        this.applyTheme(newTheme);
      });
    }

    // Listen for storage changes (multi-tab sync)
    window.addEventListener("storage", (e) => {
      if (e.key === "bodymap_theme" && e.newValue) {
        this.applyTheme(e.newValue);
      }
    });
  }

  syncThemeToServer(theme) {
    // Theme is shared site-wide now (not per-account), so always sync.
    fetch("/settings/theme", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `theme=${encodeURIComponent(theme)}`,
    }).catch(() => {
      // Silently fail; theme still updates locally
    });
  }

  getActiveUserId() {
    // Try to extract from page (data attribute, form field, etc.)
    const userElem = document.querySelector("[data-user-id]");
    if (userElem) return userElem.getAttribute("data-user-id");
    const inp = document.querySelector("input[name='unique_id']");
    if (inp) return inp.value;
    return null;
  }
}

// Auto-init on page load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    window.themeManager = new ThemeManager();
  });
} else {
  window.themeManager = new ThemeManager();
}
