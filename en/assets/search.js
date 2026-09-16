
(function () {
  var box = document.getElementById('q');
  var out = document.getElementById('results');
  if (!box || !out) return;
  var rows = [];

  var inline = document.getElementById('search-data');
  if (inline) {
    try { rows = JSON.parse(inline.textContent || '[]'); } catch (err) { rows = []; }
  }
  if (rows.length) {
    render('');
  } else {
    fetch('search-index.json')
      .then(function (r) { return r.json(); })
      .then(function (d) { rows = d; render(''); })
      .catch(function () {
        out.textContent = "Could not load the search data.";
        out.className = 'search-empty';
      });
  }

  function norm(s) { return (s || '').toString().toLowerCase(); }

  function render(q) {
    q = norm(q).trim();
    var hits = rows;
    if (q) {
      hits = rows.filter(function (r) {
        return norm(r.n).indexOf(q) >= 0 || norm(r.j).indexOf(q) >= 0 ||
               norm(r.e).indexOf(q) >= 0 || norm(r.k).indexOf(q) >= 0 ||
               norm(r.h).indexOf(q) >= 0;
      });
    }
    out.textContent = '';
    if (!hits.length) {
      var p = document.createElement('p');
      p.className = 'search-empty';
      p.textContent = "No rikishi found.";
      out.appendChild(p);
      return;
    }

    function div(cls, text) {
      var d = document.createElement('div');
      d.className = cls;
      d.textContent = text;
      return d;
    }

    var grid = document.createElement('div');
    grid.className = 'cards';
    hits.slice(0, 120).forEach(function (r) {
      var a = document.createElement('a');
      a.className = r.x ? 'card is-retired' : 'card';
      a.href = r.u || (encodeURIComponent(r.i) + '.html');
      var title = div('t', r.n || '');
      if (r.x) {
        var tag = document.createElement('span');
        tag.className = 'tag-retired';
        tag.textContent = "Retired";
        title.appendChild(tag);
      }
      a.appendChild(title);
      a.appendChild(div('ja', (r.j || '') + (r.e ? ' · ' + r.e : '')));
      a.appendChild(div('m', (r.r || '') + (r.h ? ' · ' + r.h : '')));
      grid.appendChild(a);
    });
    out.appendChild(grid);

    if (hits.length > 120) {
      var more = document.createElement('p');
      more.className = 'search-empty';
      more.textContent = "Showing 120 of {n}. Try a more specific search.".replace('{n}', hits.length);
      out.appendChild(more);
    }
  }

  box.addEventListener('input', function () { render(box.value); });
})();
