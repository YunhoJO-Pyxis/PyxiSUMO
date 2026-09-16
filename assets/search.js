
(function () {
  var box = document.getElementById('q');
  var out = document.getElementById('results');
  if (!box || !out) return;
  var rows = [];

  // 자료는 페이지 안에 들어 있다. fetch 를 쓰면 파일을 직접 열었을 때
  // 브라우저가 막아 검색이 통째로 죽는다.
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
        out.textContent = '검색 자료를 불러오지 못했습니다.';
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
      p.textContent = '찾는 선수가 없습니다.';
      out.appendChild(p);
      return;
    }

    // 이름은 외부 데이터다. innerHTML 로 넣지 않고 textContent 로 만든다.
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
        // 은퇴 선수를 현역과 같은 모양으로 보여주면 지금 뛰는 줄 알게 된다.
        var tag = document.createElement('span');
        tag.className = 'tag-retired';
        tag.textContent = '은퇴';
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
      more.textContent = hits.length +
        '명 중 120명만 표시했습니다. 더 구체적으로 입력해 보세요.';
      out.appendChild(more);
    }
  }

  box.addEventListener('input', function () { render(box.value); });
})();
