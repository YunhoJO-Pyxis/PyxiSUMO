

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

(function () {
  var pop = null, on = null;
  function close() {
    if (pop) { pop.remove(); pop = null; }
    if (on) { on.classList.remove('is-on'); on = null; }
  }
  document.addEventListener('click', function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('.bz-hoshi i[title]') : null;
    if (!el || el === on) { close(); return; }
    close();
    on = el; el.classList.add('is-on');
    pop = document.createElement('div');
    pop.className = 'hoshi-pop';
    pop.setAttribute('role', 'status');
    pop.textContent = el.getAttribute('title');
    document.body.appendChild(pop);
    var r = el.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    var x = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12));
    var y = r.top - h - 6;
    if (y < 8) y = r.bottom + 6;
    pop.style.left = x + 'px'; pop.style.top = y + 'px';
  });
  window.addEventListener('scroll', close, { passive: true });
  window.addEventListener('resize', close);
})();
