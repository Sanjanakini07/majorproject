// Light / dark theme. Loaded in <head> so the right theme is set before the page paints (no flash).
// The choice is remembered in the browser; with no choice yet, the device's setting is followed.
(function () {
  var KEY = 'nva-theme';
  var root = document.documentElement;
  var query = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function current() {
    return stored() || (query && query.matches ? 'dark' : 'light');
  }
  function apply() {
    root.setAttribute('data-theme', current());
    document.querySelectorAll('[data-theme-toggle]').forEach(refresh);
  }

  var MOON = '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
  var SUN = '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';

  function refresh(button) {
    var dark = current() === 'dark';
    button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (dark ? SUN : MOON) + '</svg>';
    button.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    button.title = dark ? 'Light theme' : 'Dark theme';
  }

  var Theme = {
    toggle: function () {
      var next = current() === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, next); } catch (e) { /* private window: applies until reload */ }
      root.setAttribute('data-theme', next);
      document.querySelectorAll('[data-theme-toggle]').forEach(refresh);
    },
    // A toggle button for the top bar.
    button: function () {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn small ghost theme-toggle';
      b.setAttribute('data-theme-toggle', '');
      b.addEventListener('click', Theme.toggle);
      refresh(b);
      return b;
    },
  };
  window.Theme = Theme;

  apply();
  if (query && query.addEventListener) query.addEventListener('change', function () { if (!stored()) apply(); });

  // Pages without the top bar (sign-in pages) get a floating toggle.
  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('bar')) return;
    var right = document.querySelector('.bar .bar-right');
    if (right) { right.insertBefore(Theme.button(), right.firstChild); return; }
    var fab = Theme.button();
    fab.classList.add('fab');
    document.body.appendChild(fab);
  });
})();
