

(function () {
  var bars = [].slice.call(document.querySelectorAll('[data-filter-for]'));
  bars.forEach(function (bar) {
    var box = document.querySelector(bar.getAttribute('data-filter-for'));
    if (!box) return;
    var attr = bar.getAttribute('data-filter-attr') || 'data-filter-value';
    var prefix = bar.getAttribute('data-hash-prefix') || '';
    var emptySel = bar.getAttribute('data-empty');
    var empty = emptySel ? document.querySelector(emptySel) : null;

    var items = [].slice.call(box.querySelectorAll('[' + attr + ']'));
    var buttons = [].slice.call(bar.querySelectorAll('[data-filter]'));
    if (!items.length || !buttons.length) return;

    function apply(which) {
      var shown = 0;
      items.forEach(function (el) {
        var on = which === 'all' || el.getAttribute(attr) === which;
        el.hidden = !on;
        if (on) shown++;
      });
      buttons.forEach(function (b) {
        var on = b.getAttribute('data-filter') === which;
        if (on) { b.classList.add('is-on'); } else { b.classList.remove('is-on'); }
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      if (empty) empty.hidden = shown !== 0;
      if (!prefix) return;
      try {
        var url = new URL(window.location.href);
        url.hash = which === 'all' ? '' : prefix + which;
        history.replaceState(null, '', url.toString());
      } catch (err) {  }
    }

    buttons.forEach(function (b) {
      b.addEventListener('click', function () {
        apply(b.getAttribute('data-filter'));
      });
    });

    var h = (window.location.hash || '').replace('#', '');
    if (prefix && h.indexOf(prefix) === 0) {
      var want = h.slice(prefix.length);
      if (buttons.some(function (b) { return b.getAttribute('data-filter') === want; })) {
        apply(want);
      }
    }
  });
})();
