

(function () {
  var tabs = [].slice.call(document.querySelectorAll('[data-yz-tab]'));
  var grid = document.getElementById('yz-grid');
  var heya = document.getElementById('yz-heya');
  var pick = document.getElementById('yz-heya-pick');
  if (!tabs.length || !grid || !heya || !pick) return;
  var lists = [].slice.call(heya.querySelectorAll('[data-heya]'));
  var hint = document.getElementById('yz-heya-hint');

  function setHash(h) {
    try {
      var url = new URL(window.location.href);
      url.hash = h;
      history.replaceState(null, '', url.toString());
    } catch (err) {}
  }
  function show(tab) {
    tabs.forEach(function (b) {
      var on = b.getAttribute('data-yz-tab') === tab;
      if (on) { b.classList.add('is-on'); } else { b.classList.remove('is-on'); }
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    grid.hidden = tab !== 'grid';
    heya.hidden = tab !== 'heya';
  }
  function choose(slug, keepHash) {
    var found = false;
    lists.forEach(function (el) {
      var on = el.getAttribute('data-heya') === slug;
      el.hidden = !on;
      if (on) found = true;
    });
    if (hint) hint.hidden = found;
    pick.value = found ? slug : '';
    if (!keepHash) setHash(found ? 'heya-' + slug : 'heya');
  }
  tabs.forEach(function (b) {
    b.addEventListener('click', function () {
      var tab = b.getAttribute('data-yz-tab');
      show(tab);
      if (tab === 'heya') { choose(pick.value); } else { setHash(''); }
    });
  });
  pick.addEventListener('change', function () { choose(pick.value); });

  var h = decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
  if (h === 'heya' || h.indexOf('heya-') === 0) {
    show('heya');
    choose(h.slice(5), true);
    var bar = document.querySelector('.yz-tabs');
    if (bar && bar.scrollIntoView) { bar.scrollIntoView(); }
  }
})();
