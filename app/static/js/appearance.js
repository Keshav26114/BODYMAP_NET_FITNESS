/**
 * appearance.js — Font size + accent color, site-wide.
 * Mirrors theme.js: works instantly for everyone via LocalStorage (no
 * account needed), and additionally syncs to the server whenever a
 * unique_id is available on the page (Test/History/Settings), so a
 * signed-in-by-ID user's look carries across devices/sessions.
 */

const APPEARANCE_DEFAULTS = { fontSize: "medium", accentColor: "#FF3E00" };

class AppearanceManager {
  constructor() {
    this.fontSize = localStorage.getItem("bodymap_font_size") || APPEARANCE_DEFAULTS.fontSize;
    this.accentColor = localStorage.getItem("bodymap_accent_color") || APPEARANCE_DEFAULTS.accentColor;
    this.initializeFromPage();
    this.setupSettingsControls();
  }

  // On load, an account's saved prefs (rendered server-side onto <html>)
  // take priority over LocalStorage; otherwise fall back to LocalStorage
  // (or the built-in defaults) so it still works with no account at all.
  initializeFromPage() {
    const html = document.documentElement;

    const serverFontSize = html.getAttribute("data-font-size");
    if (serverFontSize) {
      this.fontSize = serverFontSize;
      localStorage.setItem("bodymap_font_size", serverFontSize);
    } else {
      html.setAttribute("data-font-size", this.fontSize);
    }

    const serverAccent = html.style.getPropertyValue("--accent").trim();
    if (serverAccent) {
      this.accentColor = serverAccent;
      localStorage.setItem("bodymap_accent_color", serverAccent);
    } else {
      html.style.setProperty("--accent", this.accentColor);
    }
  }

  applyFontSize(size) {
    this.fontSize = size;
    document.documentElement.setAttribute("data-font-size", size);
    localStorage.setItem("bodymap_font_size", size);
    this.syncToServer();
  }

  applyAccentColor(color) {
    this.accentColor = color;
    document.documentElement.style.setProperty("--accent", color);
    localStorage.setItem("bodymap_accent_color", color);
    this.syncToServer();
  }

  getActiveUserId() {
    const userElem = document.querySelector("[data-user-id]");
    if (userElem) return userElem.getAttribute("data-user-id");
    const inp = document.querySelector("input[name='unique_id']");
    if (inp && inp.value) return inp.value;
    const sel = document.querySelector("select[name='unique_id']");
    if (sel && sel.value) return sel.value;
    return null;
  }

  syncToServer() {
    // Appearance is shared site-wide now (not per-account), so always sync.
    const theme = document.documentElement.getAttribute("data-theme") || "light";
    const body = new URLSearchParams({
      theme: theme,
      font_size: this.fontSize,
      accent_color: this.accentColor,
    });
    fetch("/settings/appearance", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    }).catch(() => {
      // Silently fail; the look still updates locally either way.
    });
  }

  // Wires up the swatches / custom color / font-size select on the
  // Settings page specifically, if they're present on this page.
  // NOTE: AppearanceManager itself is only ever constructed after
  // DOMContentLoaded has already fired (see bottom of file), so this must
  // run its setup directly rather than registering another
  // "DOMContentLoaded" listener — that event only fires once per page load,
  // so a listener added here would simply never run.
  setupSettingsControls() {
    const swatches = document.querySelectorAll(".accent-swatch");
    const customColor = document.getElementById("accent_custom");
    const fontSizeSelect = document.getElementById("font_size_select");
    const themeSelect = document.getElementById("theme_select");

    if (themeSelect) {
      themeSelect.addEventListener("change", () => {
        if (window.themeManager) {
          window.themeManager.applyTheme(themeSelect.value);
        }
        // Theme sync piggybacks on ThemeManager -> /settings/theme; also
        // push font_size/accent_color together so nothing gets out of sync.
        this.syncToServer();
      });
    }

    const markSelectedSwatch = (color) => {
      swatches.forEach((btn) => {
        btn.classList.toggle("is-selected", btn.dataset.color.toLowerCase() === color.toLowerCase());
      });
    };
    markSelectedSwatch(this.accentColor);
    if (customColor) customColor.value = this.accentColor;
    if (fontSizeSelect) fontSizeSelect.value = this.fontSize;

    swatches.forEach((btn) => {
      btn.addEventListener("click", () => {
        const color = btn.dataset.color;
        this.applyAccentColor(color);
        markSelectedSwatch(color);
        if (customColor) customColor.value = color;
      });
    });

    if (customColor) {
      customColor.addEventListener("input", () => {
        this.applyAccentColor(customColor.value);
        markSelectedSwatch(customColor.value);
      });
    }

    if (fontSizeSelect) {
      fontSizeSelect.addEventListener("change", () => {
        this.applyFontSize(fontSizeSelect.value);
      });
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    window.appearanceManager = new AppearanceManager();
  });
} else {
  window.appearanceManager = new AppearanceManager();
}
