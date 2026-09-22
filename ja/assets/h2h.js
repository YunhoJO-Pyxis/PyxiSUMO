

(function () {
  'use strict';
  var dataEl = document.getElementById('h2h-data');
  var form = document.getElementById('h2h-form');
  var out = document.getElementById('h2h-out');
  if (!dataEl || !form || !out) { return; }

  var D;
  try { D = JSON.parse(dataEl.textContent || '{}'); } catch (err) { return; }
  var people = D.people || [];
  var byId = {};

  
  function fold(s) {
    return (s || '').toString().toLowerCase().replace(/\s+/g, '')
      .replace(/[\u30a1-\u30f6]/g, function (c) {
        return String.fromCharCode(c.charCodeAt(0) - 0x60);
      });
  }
  people.forEach(function (p) {
    byId[p.i] = p;
    p._q = fold([p.n, p.s, p.j, p.e, p.k, p.h].join('\u0001'));
  });

  function matches(q) {
    q = fold(q);
    if (!q) { return people; }
    return people.filter(function (p) { return p._q.indexOf(q) >= 0; });
  }

  function el(tag, cls, text) {
    var x = document.createElement(tag);
    if (cls) { x.className = cls; }
    if (text !== undefined && text !== null) { x.textContent = text; }
    return x;
  }

  function Picker(slot) {
    var input = document.getElementById('h2h-' + slot);
    var list = document.getElementById('h2h-' + slot + '-list');
    var box = input.parentNode;
    var me = { id: null, input: input };
    var hits = [];
    var active = -1;

    function isOpen() { return !list.hidden; }
    function open() {
      render();
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }
    function close() {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      active = -1;
    }
    function label(id) { return byId[id] ? byId[id].n : ''; }

    function render() {
      
      var q = (me.id && input.value === label(me.id)) ? '' : input.value;
      hits = matches(q);
      active = -1;
      list.textContent = '';
      if (!hits.length) {
        var none = el('li', 'h2h-none', "該当する力士がいません。");
        none.setAttribute('role', 'presentation');
        list.appendChild(none);
        return;
      }
      hits.forEach(function (p, k) {
        var li = el('li', 'h2h-opt' + (p.i === me.id ? ' is-picked' : ''));
        li.id = 'h2h-' + slot + '-o' + k;
        li.setAttribute('role', 'option');
        li.setAttribute('tabindex', '-1');
        li.setAttribute('aria-selected', p.i === me.id ? 'true' : 'false');
        
        var who = el('span', 'h2h-who');
        who.appendChild(el('span', 'h2h-name', p.n));
        if (p.s) { who.appendChild(el('span', 'h2h-sub', p.s)); }
        li.appendChild(who);
        li.appendChild(el('span', 'h2h-rank', p.r + (p.h ? ' \u00b7 ' + p.h : '')));
        li.addEventListener('click', function () { choose(p); input.focus(); });
        list.appendChild(li);
      });
    }

    function mark(k) {
      var opts = list.querySelectorAll('.h2h-opt');
      if (!opts.length) { return; }
      active = (k + opts.length) % opts.length;
      for (var n = 0; n < opts.length; n++) {
        opts[n].classList.toggle('is-active', n === active);
      }
      input.setAttribute('aria-activedescendant', opts[active].id);
      opts[active].scrollIntoView({ block: 'nearest' });
    }

    function choose(p) {
      me.id = p.i;
      input.value = p.n;
      close();
    }
    me.set = choose;

    
    me.resolve = function () {
      if (me.id && input.value === label(me.id)) { return me.id; }
      var v = input.value.trim();
      if (!v) { return null; }
      var found = matches(v);
      var exact = found.filter(function (p) {
        return fold(p.n) === fold(v) || fold(p.j) === fold(v) ||
               fold(p.e) === fold(v);
      });
      var pick = found.length === 1 ? found[0] : (exact.length === 1 ? exact[0] : null);
      if (pick) { choose(pick); return pick.i; }
      return null;
    };

    input.addEventListener('click', function () {
      if (isOpen()) { close(); } else { open(); }
    });
    input.addEventListener('input', function () { me.id = null; open(); });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        if (!isOpen()) { open(); }
        mark(active + 1);
      } else if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        if (!isOpen()) { open(); }
        mark(active - 1);
      } else if (ev.key === 'Enter') {
        if (isOpen() && active >= 0 && hits[active]) {
          ev.preventDefault();
          choose(hits[active]);
        }
      } else if (ev.key === 'Escape') {
        
        if (isOpen()) { ev.preventDefault(); close(); }
      }
    });
    
    box.addEventListener('focusout', function (ev) {
      if (!ev.relatedTarget || !box.contains(ev.relatedTarget)) { close(); }
    });
    document.addEventListener('pointerdown', function (ev) {
      if (isOpen() && !box.contains(ev.target)) { close(); }
    });
    return me;
  }

  var A = Picker('a');
  var B = Picker('b');

  function say(text) {
    out.textContent = '';
    out.appendChild(el('p', 'search-empty', text));
  }

  var seq = 0;
  function show(a, b, remember) {
    var mine = ++seq;
    if (remember && window.history && history.replaceState) {
      history.replaceState(null, '', '#' + a + '-' + b);
    }
    say("読み込み中…");
    fetch(D.src + encodeURIComponent(a) + '.json')
      .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
      .then(function (all) {
        
        if (mine !== seq) { return; }
        draw(byId[a], byId[b], all[b] || []);
      })
      .catch(function () { if (mine === seq) { say("記録を読み込めませんでした。しばらくしてからもう一度お試しください。"); } });
  }

  function rankOf(rv) { return (rv !== null && D.rank[rv]) || '\u2014'; }

  function draw(pa, pb, bouts) {
    out.textContent = '';
    var won = 0, lost = 0, fusen = 0, next = null, done = [];
    bouts.forEach(function (x) {
      
      if (x[2] === 1) { won++; } else if (x[2] === 0) { lost++; }
      if (x[2] !== null && x[3]) { fusen++; }
      if (x[2] === null && x[0] === D.cur) { next = x; }
      if (x[2] !== null) { done.push(x); }
    });

    var head = el('div', 'h2h-head');
    
    function side(p, n, cls) {
      var a = el('a', 'card h2h-card ' + cls);
      a.href = D.rk + encodeURIComponent(p.i) + '.html';
      a.appendChild(el('div', 't', p.n));
      if (p.s) { a.appendChild(el('div', 'ja', p.s)); }
      a.appendChild(el('div', 'm', p.r + (p.h ? ' \u00b7 ' + p.h : '')));
      a.appendChild(el('div', 'h2h-wins', String(n)));
      return a;
    }
    head.appendChild(side(pa, won, 'l' + (won > lost ? ' lead' : '')));
    head.appendChild(el('div', 'h2h-dash', '\u2013'));
    head.appendChild(side(pb, lost, 'r' + (lost > won ? ' lead' : '')));
    out.appendChild(head);

    var notes = [];
    if (done.length) {
      notes.push("通算{n}回対戦".replace('{n}', done.length));
      notes.push("{a}〜{b}"
        .replace('{a}', D.basho[done[done.length - 1][0]] || done[done.length - 1][0])
        .replace('{b}', D.basho[done[0][0]] || done[0][0]));
      if (fusen) { notes.push("不戦{n}回を含む".replace('{n}', fusen)); }
    }
    if (next) {
      notes.push("{d}に対戦予定".replace('{d}', "{d}日目".replace('{d}', next[1])));
    }
    if (notes.length) { out.appendChild(el('p', 'h2h-sum', notes.join(' \u00b7 '))); }

    if (!done.length && !next) {
      out.appendChild(el('p', 'search-empty', "まだ対戦記録がありません。"));
      return;
    }

    var wrap = el('div', 'table-scroll');
    var table = el('table', 'h2h-table');
    var thead = el('thead');
    var tr = el('tr');
    ["場所", "日目", pa.n, pb.n, "決まり手"].forEach(function (h) {
      tr.appendChild(el('th', '', h));
    });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = el('tbody');

    bouts.forEach(function (x) {
      var row = el('tr', x[2] === null ? 'is-pending' : '');
      row.appendChild(el('td', 'h2h-basho', D.basho[x[0]] || x[0]));
      row.appendChild(el('td', 'num', "{d}日目".replace('{d}', x[1])));
      function cell(rv, win) {
        var td = el('td', 'h2h-cell');
        td.appendChild(el('span', 'h2h-r', rankOf(rv)));
        if (win === true) { td.appendChild(el('span', 'bt-win', "勝")); }
        if (win === false) { td.appendChild(el('span', 'bt-lose', "敗")); }
        return td;
      }
      var r = x[2];
      row.appendChild(cell(x[5], r === 1 ? true : (r === 0 ? false : null)));
      row.appendChild(cell(x[6], r === 0 ? true : (r === 1 ? false : null)));
      var kim = el('td', 'h2h-kim');
      if (r === null) {
        kim.appendChild(el('span', 'bt-pending',
          x[0] === D.cur ? "予定" : "結果なし"));
      } else if (x[3]) {
        kim.textContent = "不戦";
      } else {
        kim.textContent = (x[4] && D.kim[x[4]]) || '';
      }
      row.appendChild(kim);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    out.appendChild(wrap);
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var a = A.resolve();
    var b = B.resolve();
    if (!a || !b) { say("2つの欄の両方で力士を選んでください。"); return; }
    if (a === b) { say("異なる2人の力士を選んでください。"); return; }
    show(a, b, true);
  });

  
  var m = /^#(\w+)-(\w+)$/.exec(window.location.hash || '');
  if (m && byId[m[1]] && byId[m[2]] && m[1] !== m[2]) {
    A.set(byId[m[1]]);
    B.set(byId[m[2]]);
    show(m[1], m[2], false);
  }
})();
