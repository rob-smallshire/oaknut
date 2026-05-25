/*
 * platform-tabs.js — auto-select the host-platform tab on page load.
 *
 * Pages use sphinx-design `tab-set`s with `:sync:` IDs to group
 * platform-specific code samples. By convention the sync IDs are:
 *
 *     bash         — Linux / generic Unix
 *     zsh          — macOS (default shell since Catalina)
 *     powershell   — Windows
 *
 * On first visit, sphinx-design otherwise activates whichever tab
 * appears first in the source. This script detects the visitor's
 * platform via the User-Agent Client Hints API (with a fallback to
 * the legacy `navigator.platform` string) and clicks the matching
 * tab once the DOM is ready. sphinx-design then propagates that
 * choice to every other synced tab-set on the page and persists it
 * across navigation via localStorage.
 *
 * A reader can always override the auto-selection by clicking a
 * different tab; sphinx-design respects the manual choice and stops
 * second-guessing.
 */
(function () {
    "use strict";

    function detectSyncId() {
        // Honour an explicit override saved by a previous click.
        try {
            const stored = window.localStorage.getItem("sphinx-design-tab-sync-platform");
            if (stored) return null;
        } catch (e) {
            /* localStorage might be unavailable; fall through to detection */
        }

        const platform =
            (navigator.userAgentData && navigator.userAgentData.platform) ||
            navigator.platform ||
            "";

        const lower = platform.toLowerCase();
        if (lower.indexOf("mac") !== -1) return "zsh";
        if (lower.indexOf("win") !== -1) return "powershell";
        return "bash";
    }

    function activate(syncId) {
        // sphinx-design renders each tab as a hidden <input type="radio">
        // labelled by the visible tab header. The radio's `name` is the
        // tab-set ID; its data-sync-id matches the :sync: directive value.
        const selector = `.sd-tab-set input[type=radio][data-sync-id="${syncId}"]`;
        const radios = document.querySelectorAll(selector);
        radios.forEach((radio) => {
            const label = document.querySelector(`label[for="${radio.id}"]`);
            if (label) label.click();
        });
    }

    function init() {
        const syncId = detectSyncId();
        if (!syncId) return;
        activate(syncId);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
