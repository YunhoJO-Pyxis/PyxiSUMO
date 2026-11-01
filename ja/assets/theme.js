

(function () {
  'use strict';
  var KEY = 'pyxisumo-theme';
  var ORDER = ['system', 'light', 'dark'];
  var root = document.documentElement;
  var mode = 'system';

  try {
    var saved = window.localStorage.getItem(KEY);
    if (ORDER.indexOf(saved) >= 0) { mode = saved; }
  } catch (err) {  }

  function apply(m) {
    if (m === 'system') { root.removeAttribute('data-theme'); }
    else { root.setAttribute('data-theme', m); }
  }

  apply(mode);
  
  root.className += (root.className ? ' ' : '') + 'has-js';

  function wire() {
    var btn = document.getElementById('theme-switch');
    if (!btn) { return; }

    
    function label() {
      btn.textContent = btn.getAttribute('data-l-' + mode) || '';
      btn.setAttribute('aria-label', btn.getAttribute('data-a-' + mode) || '');
      btn.setAttribute('title', btn.getAttribute('data-a-' + mode) || '');
    }

    label();
    btn.addEventListener('click', function () {
      mode = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
      apply(mode);
      try { window.localStorage.setItem(KEY, mode); } catch (err) {  }
      label();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
