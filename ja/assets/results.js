

(function () {
  'use strict';
  var bar = document.querySelector('.tb-refresh');
  if (!bar) return;
  var btn = bar.querySelector('.tb-refresh-btn');
  var msg = bar.querySelector('.tb-refresh-msg');
  var basho = bar.getAttribute('data-basho');
  var api = bar.getAttribute('data-api');
  var kim = {};
  try { kim = JSON.parse(document.getElementById('kim-data').textContent) || {}; } catch (e) { kim = {}; }
  var T_WIN = "勝", T_LOSE = "敗", T_FUSEN = "不戦";
  var T_LOADING = "取得中…", T_FAIL = "結果を取得できませんでした。少し待ってからもう一度押してください。";
  var T_NEW = "{t} 確認 · 新しい結果 {n}番", T_NONE = "{t} 確認 · 新しい結果はまだありません", T_ALL = "{t} 確認 · この画面の取組はすべて終わりました", T_REC = "対戦 {a}–{b}";
  var T_DONE_SOME = "{n}番中{done}番終了", T_DONE_ALL = "全{n}番終了";

  function pendingRows(box) {
    return [].slice.call(box.querySelectorAll('.tb-row[data-ea]')).filter(function (r) {
      return !!r.querySelector('.bt-pending');
    });
  }

  function mark(row, winKey, how, fusen) {
    ['e', 'w'].forEach(function (k) {
      var side = row.querySelector('.tb-side.' + k);
      if (!side) return;
      var top = side.querySelector('.tb-top');
      var old = top && top.querySelector('.bt-win, .bt-lose');
      if (old) old.parentNode.removeChild(old);
      var s = document.createElement('span');
      s.className = k === winKey ? 'bt-win' : 'bt-lose';
      s.textContent = k === winKey ? T_WIN : T_LOSE;
      if (top) top.appendChild(s);
      if (k === winKey) side.classList.add('is-win');
    });
    var pend = row.querySelector('.bt-pending');
    if (pend) {
      var m = document.createElement('span');
      m.className = 'tb-kim';
      m.textContent = fusen ? T_FUSEN : how;
      pend.parentNode.replaceChild(m, pend);
    }
    var ew = parseInt(row.getAttribute('data-ew'), 10) || 0;
    var ww = parseInt(row.getAttribute('data-ww'), 10) || 0;
    if (winKey === 'e') ew++; else ww++;
    var rec = row.querySelector('.tb-rec a') || row.querySelector('.tb-rec');
    if (rec) rec.textContent = T_REC.replace('{a}', ew).replace('{b}', ww);
    row.classList.add('is-fresh');
    row.removeAttribute('data-ea');
  }

  function apply(day, list) {
    var box = document.querySelector('.tb-day[data-day="' + day + '"]');
    if (!box) return 0;
    var n = 0;
    (list || []).forEach(function (b) {
      var e = String(b.eastId), w = String(b.westId), win = String(b.winnerId || '');
      if (!win || win === '0' || (win !== e && win !== w)) return;
      var raw = String(b.kimarite || '').toLowerCase();
      var fusen = raw.indexOf('fusen') === 0;
      var how = kim[raw] || raw;
      var hit = false;
      pendingRows(box).forEach(function (row) {
        var ea = row.getAttribute('data-ea'), wa = row.getAttribute('data-wa');
        if (ea === e && wa === w) { mark(row, win === e ? 'e' : 'w', how, fusen); hit = true; }
        else if (ea === w && wa === e) { mark(row, win === w ? 'e' : 'w', how, fusen); hit = true; }
      });
      if (hit) n++;
    });
    if (n) recount(box);
    return n;
  }

  function recount(box) {
    var cnt = box.querySelector('h2 .tb-count');
    if (!cnt) return;
    var rows = box.querySelectorAll('.tb-list:not(.tb-feat) .tb-row');
    var left = box.querySelectorAll('.tb-list:not(.tb-feat) .tb-row .bt-pending').length;
    var done = rows.length - left;
    cnt.textContent = (left === 0 ? T_DONE_ALL : T_DONE_SOME)
      .replace('{n}', rows.length).replace('{done}', done);
  }

  btn.addEventListener('click', function () {
    var jobs = [];
    [].slice.call(document.querySelectorAll('.tb-day[data-day]')).forEach(function (box) {
      var day = box.getAttribute('data-day');
      var divs = {};
      pendingRows(box).forEach(function (r) { divs[r.getAttribute('data-div')] = true; });
      Object.keys(divs).forEach(function (dv) {
        var url = api + '/api/basho/' + encodeURIComponent(basho) + '/torikumi/' +
                  encodeURIComponent(dv) + '/' + encodeURIComponent(day);
        jobs.push(fetch(url, { cache: 'no-store' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }).then(function (j) { return apply(day, j && j.torikumi); }));
      });
    });
    var now = new Date();
    var hm = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2);
    if (!jobs.length) { msg.textContent = T_ALL.replace('{t}', hm); return; }
    btn.disabled = true;
    msg.textContent = T_LOADING;
    Promise.all(jobs).then(function (counts) {
      var n = counts.reduce(function (a, b) { return a + b; }, 0);
      var left = document.querySelectorAll('.tb-row[data-ea] .bt-pending').length;
      msg.textContent = (left === 0 ? T_ALL : n ? T_NEW : T_NONE)
        .replace('{t}', hm).replace('{n}', n);
    }).catch(function () {
      msg.textContent = T_FAIL;
    }).then(function () { btn.disabled = false; });
  });
})();
