// Make the documentation follow the operating system's light/dark
// preference, and keep following it live when the OS setting changes.
//
// The clarity theme's own dark-mode.js reads the OS preference only
// once, on load, and pins any manual choice in localStorage. We have
// removed the toggle (see _templates/partials/mode_select.html), so
// here we drop any previously-pinned choice and mirror the OS scheme on
// load and on every change.
(function () {
  var DARK = "dark";
  var LIGHT = "light";
  var query = window.matchMedia("(prefers-color-scheme: dark)");

  function syncPygments(isDark) {
    // Mirror the theme's own Pygments handling: the dark highlight
    // stylesheet is toggled via its `disabled` flag.
    var link = document.getElementById("pygments_dark_css");
    if (link) {
      link.removeAttribute("media");
      link.disabled = !isDark;
    }
  }

  function apply(isDark) {
    document.documentElement.dataset.theme = isDark ? DARK : LIGHT;
    syncPygments(isDark);
  }

  // Never let a pinned preference override the OS scheme.
  try {
    localStorage.removeItem("theme");
  } catch (e) {
    /* localStorage may be unavailable; ignore. */
  }

  // Set the attribute immediately; the Pygments <link> may not be
  // parsed yet, so sync it once the DOM is ready.
  document.documentElement.dataset.theme = query.matches ? DARK : LIGHT;
  document.addEventListener("DOMContentLoaded", function () {
    syncPygments(query.matches);
  });

  // Live updates when the OS preference flips.
  query.addEventListener("change", function (event) {
    apply(event.matches);
  });
})();
