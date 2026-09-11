"""사이트 공통 스타일.

요건정의서의 'Modern Traditional Japan' 을 따르되, 가독성을 해치지 않는
선에서만 전통 요소를 쓴다. 스모지(江戸文字)는 웹폰트로 배포할 수 있는
것이 없어 제목에도 쓰지 않고, 굵은 명조(Noto Serif JP 900)로 대신한다.

색: 荒木田土(도효 점토)를 중화한 회백 지면 · 藍色(남색) 기조 · 朱色(주색) 강조
"""

CSS = """
:root {
  --ground:      #F0F2EE;
  --surface:     #FAFBF8;
  --surface-2:   #E7EAE4;
  --rule:        #D3D8CE;
  --rule-strong: #B3BBAD;

  --ink:   #141A20;
  --ink-2: #4E5A63;
  --ink-3: #78848C;

  --indigo:      #1E3A5F;
  --indigo-soft: #E2E8EE;
  --vermilion:   #AE3227;
  --vermilion-soft: #F6E6E3;
  --clay:        #8E6234;
  --clay-soft:   #F3EADE;
  --moss:        #3F6449;
  --moss-soft:   #E3ECE4;
  --purple:      #6B4A7A;

  --shadow: 0 1px 2px rgba(20,26,32,.05), 0 10px 28px -14px rgba(20,26,32,.16);

  --f-display: 'Noto Serif JP', 'Apple SD Gothic Neo', serif;
  --f-body: 'IBM Plex Sans KR', -apple-system, 'Segoe UI', 'Malgun Gothic', sans-serif;
  --f-mono: 'IBM Plex Mono', ui-monospace, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #11151A; --surface: #191E24; --surface-2: #222932;
    --rule: #2C343D; --rule-strong: #3E4853;
    --ink: #E4E8E2; --ink-2: #A2AEB6; --ink-3: #77838C;
    --indigo: #8FB4DA; --indigo-soft: #1C2836;
    --vermilion: #E0786C; --vermilion-soft: #33201D;
    --clay: #C79C6E; --clay-soft: #2C2317;
    --moss: #84B08D; --moss-soft: #1B2820;
    --purple: #B292C2;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 28px -14px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"] {
  --ground: #11151A; --surface: #191E24; --surface-2: #222932;
  --rule: #2C343D; --rule-strong: #3E4853;
  --ink: #E4E8E2; --ink-2: #A2AEB6; --ink-3: #77838C;
  --indigo: #8FB4DA; --indigo-soft: #1C2836;
  --vermilion: #E0786C; --vermilion-soft: #33201D;
  --clay: #C79C6E; --clay-soft: #2C2317;
  --moss: #84B08D; --moss-soft: #1B2820;
  --purple: #B292C2;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 28px -14px rgba(0,0,0,.7);
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--ground); color: var(--ink);
  font-family: var(--f-body); font-size: 16px; line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}
img { max-width: 100%; }

.wrap { max-width: 1000px; margin: 0 auto; padding-inline: 20px; }

/* ── 머리말 ─────────────────────────── */
.site-head {
  background: var(--surface); border-bottom: 1px solid var(--rule);
  position: sticky; top: 0; z-index: 10;
}
.site-head .wrap {
  display: flex; align-items: center; gap: 12px 28px; flex-wrap: wrap;
  padding-block: 14px;
}
.brand { display: flex; align-items: baseline; gap: 10px; text-decoration: none; }
.brand b {
  font-family: var(--f-display); font-weight: 900; font-size: 1.25rem;
  color: var(--ink); letter-spacing: -.01em;
}
.brand span {
  font-family: var(--f-mono); font-size: .66rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--ink-3);
}
.site-nav { display: flex; gap: 4px 18px; flex-wrap: wrap; margin-left: auto; }
.site-nav a {
  color: var(--ink-2); text-decoration: none; font-size: .92rem; font-weight: 500;
  padding: 3px 0; border-bottom: 2px solid transparent;
}
.site-nav a:hover { color: var(--ink); }
.site-nav a[aria-current="page"] {
  color: var(--ink); border-bottom-color: var(--vermilion);
}
a:focus-visible, button:focus-visible, input:focus-visible {
  outline: 2px solid var(--indigo); outline-offset: 2px;
}

/* ── 페이지 제목 ────────────────────── */
.page-head { padding-block: 40px 26px; border-bottom: 2px solid var(--ink); }
.eyebrow {
  font-family: var(--f-mono); font-size: .7rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 12px;
}
.page-head h1 {
  font-family: var(--f-display); font-weight: 900;
  font-size: clamp(1.6rem, 4.5vw, 2.4rem); line-height: 1.25;
  margin: 0; text-wrap: balance;
}
.page-head .sub { margin: 10px 0 0; color: var(--ink-2); max-width: 64ch; }

.status-pill {
  display: inline-block; font-family: var(--f-mono); font-size: .68rem;
  letter-spacing: .1em; text-transform: uppercase;
  padding: 2px 9px; border-radius: 2px; vertical-align: .18em; margin-left: 10px;
}
.st-upcoming { background: var(--indigo-soft); color: var(--indigo); }
.st-ongoing  { background: var(--vermilion-soft); color: var(--vermilion); }
.st-finished { background: var(--surface-2); color: var(--ink-3); }

main { padding-block: 30px 72px; }
h2 {
  font-family: var(--f-display); font-weight: 700; font-size: 1.2rem;
  margin: 40px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--rule);
}
h2:first-child { margin-top: 0; }
p { margin: 0 0 14px; max-width: 68ch; }
a { color: var(--indigo); text-underline-offset: 2px; }

/* ── 반즈케 표 (東西 대칭) ──────────── */
.banzuke { border: 1px solid var(--rule); background: var(--surface); margin: 0 0 26px; }
.bz-head, .bz-row {
  display: grid; grid-template-columns: 1fr 116px 1fr; align-items: stretch;
}
.bz-head > div {
  background: var(--surface-2); border-bottom: 1px solid var(--rule);
  padding: 9px 16px; font-family: var(--f-mono); font-size: .68rem;
  letter-spacing: .14em; text-transform: uppercase; color: var(--ink-2);
}
.bz-head .c { text-align: center; }
.bz-row { border-bottom: 1px solid var(--rule); }
.bz-row:last-child { border-bottom: none; }
.bz-row:hover { background: var(--surface-2); }

.bz-side { padding: 8px 16px; display: flex; flex-direction: column; gap: 0; min-width: 0; }
.bz-side.w { align-items: flex-end; text-align: right; }
.bz-side.empty { opacity: .3; }
.bz-name { font-weight: 600; font-size: .98rem; }
.bz-name a { color: var(--ink); text-decoration: none; }
.bz-name a:hover { text-decoration: underline; }
.bz-ja { font-family: var(--f-display); font-size: .82rem; color: var(--ink-3); }
.bz-heya { font-size: .76rem; color: var(--ink-3); }
.bz-rec {
  font-family: var(--f-mono); font-size: .8rem; font-variant-numeric: tabular-nums;
  color: var(--ink-2); margin-top: 2px;
}
.bz-rec .kachi { color: var(--moss); font-weight: 500; }
.bz-rec .make  { color: var(--vermilion); }

.bz-rank {
  background: var(--surface-2); border-inline: 1px solid var(--rule);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 8px 4px; text-align: center;
}
.bz-rank .k {
  font-family: var(--f-display); font-weight: 700; font-size: .8rem;
  line-height: 1.25; color: var(--ink);
}
.bz-rank .n {
  font-family: var(--f-mono); font-size: .72rem; color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
.rk-yokozuna .k { color: var(--vermilion); }
.rk-ozeki .k    { color: var(--clay); }
.rk-sekiwake .k { color: var(--indigo); }
.rk-komusubi .k { color: var(--moss); }
.rk-juryo .k    { color: var(--purple); }

.div-break {
  background: var(--ink); color: var(--ground);
  font-family: var(--f-display); font-weight: 700; font-size: .82rem;
  letter-spacing: .1em; padding: 7px 16px; text-align: center;
}
:root[data-theme="dark"] .div-break { color: #11151A; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .div-break { color: #11151A; }
}

@media (max-width: 640px) {
  .bz-head { display: none; }
  /* 지위를 맨 위로 올린다. 그리드 순서 그대로 두면
     '東 선수 → 지위 → 西 선수' 가 되어 어느 쪽 지위인지 헷갈린다. */
  .bz-row { display: flex; flex-direction: column; }
  .bz-rank {
    order: -1;
    border-inline: none; border-bottom: 1px solid var(--rule);
    flex-direction: row; gap: 8px; align-items: baseline;
    justify-content: flex-start; padding: 6px 16px;
  }
  .bz-side { padding-block: 7px; }
  .bz-side.w { align-items: flex-start; text-align: left; }
  .bz-side::before {
    content: attr(data-side); font-family: var(--f-mono); font-size: .62rem;
    letter-spacing: .14em; color: var(--ink-3);
  }
  .bz-side.empty { display: none; }
  .bz-row + .bz-row .bz-rank { border-top: 1px solid var(--rule); }
}

/* ── 카드 그리드 ────────────────────── */
.grid {
  display: grid; gap: 1px; background: var(--rule);
  border: 1px solid var(--rule); margin: 0 0 26px;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
}
.grid > * { background: var(--surface); padding: 16px 18px; }
.stat .k {
  font-family: var(--f-mono); font-size: .66rem; letter-spacing: .13em;
  text-transform: uppercase; color: var(--ink-3); display: block;
}
.stat .v {
  font-family: var(--f-display); font-weight: 700; font-size: 1.5rem;
  font-variant-numeric: tabular-nums; line-height: 1.3;
}
.stat .d { font-size: .8rem; color: var(--ink-2); }

/* ── 목록 카드 ──────────────────────── */
.cards { display: grid; gap: 12px; margin: 0 0 26px;
         grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }
.card {
  background: var(--surface); border: 1px solid var(--rule);
  padding: 15px 17px; text-decoration: none; color: inherit; display: block;
}
.card:hover { border-color: var(--rule-strong); box-shadow: var(--shadow); }
.card .t { font-weight: 600; font-size: 1rem; margin-bottom: 2px; }
.card .ja { font-family: var(--f-display); font-size: .84rem; color: var(--ink-3); }
.card .m { font-size: .8rem; color: var(--ink-2); margin-top: 7px; }
.card .links { display: flex; gap: 8px; margin-top: 9px; flex-wrap: wrap; }
.chip {
  font-family: var(--f-mono); font-size: .66rem; letter-spacing: .06em;
  padding: 2px 7px; border: 1px solid var(--rule-strong); border-radius: 2px;
  color: var(--ink-2); text-decoration: none;
}
.chip:hover { border-color: var(--indigo); color: var(--indigo); }

/* ── 표 ─────────────────────────────── */
.table-scroll { overflow-x: auto; border: 1px solid var(--rule); margin: 0 0 26px; }
table { border-collapse: collapse; width: 100%; min-width: 520px;
        background: var(--surface); font-size: .88rem; }
/* 예측표는 열이 9개다. 폭을 억지로 맞추면 칸마다 글자가 쪼개지므로
   최소 폭을 넉넉히 주고, 모자라면 가로로 스크롤시킨다. */
table.wide { min-width: 0; }
/* 열이 많은 표는 좌우 여백을 줄여 한 화면에 들어오게 한다.
   그래도 좁으면 .table-scroll 이 가로로 스크롤한다 (본문은 안 밀린다). */
table.wide th, table.wide td { padding: 9px 10px; }
/* 예측 근거 — 지위 밑에 붙는 한 줄 설명 */
td .basis {
  margin-top: 3px; font-family: var(--f-body); font-size: .74rem;
  font-weight: 400; color: var(--ink-3); white-space: normal; max-width: 160px;
}
th, td { padding: 9px 14px; text-align: left; border-bottom: 1px solid var(--rule);
         vertical-align: top;
         /* 한국어는 어절 단위로 끊는다. 이걸 안 주면 칸이 좁아질 때
            '성 적 기 반 계 산' 처럼 한 글자씩 세로로 쪼개진다. */
         word-break: keep-all; overflow-wrap: normal; }
thead th {
  background: var(--surface-2); font-family: var(--f-mono); font-weight: 500;
  font-size: .68rem; letter-spacing: .1em; text-transform: uppercase;
  color: var(--ink-2); white-space: nowrap;
}
tbody tr:last-child td { border-bottom: none; }
td.num { font-family: var(--f-mono); font-variant-numeric: tabular-nums;
         white-space: nowrap; }
td.name { font-weight: 500; white-space: nowrap; }

/* 헤야 칸 — 한국어 / 한자를 두 줄로. 한 줄로 두면 좁은 표에서 세로로 쪼개진다 */
td.heya { white-space: nowrap; line-height: 1.35; }
td.heya .hy-ko { display: block; }
td.heya .hy-ja {
  display: block; font-family: var(--f-jp, inherit);
  font-size: .78em; color: var(--ink-3);
}
td.name a { color: var(--ink); text-decoration: none; }
td.name a:hover { text-decoration: underline; }

/* ── 검색 ───────────────────────────── */
.search-box { margin: 0 0 20px; }
.search-box input {
  width: 100%; font-family: var(--f-body); font-size: 1rem;
  padding: 12px 15px; border: 1px solid var(--rule-strong);
  background: var(--surface); color: var(--ink); border-radius: 2px;
}
.search-box .hint { font-size: .8rem; color: var(--ink-3); margin-top: 7px; }
.search-empty { color: var(--ink-3); padding: 20px 0; }

/* ── 확신도 막대 ────────────────────── */
.conf { display: flex; align-items: center; gap: 7px; }
.conf-bar {
  width: 42px; height: 5px; background: var(--surface-2);
  border-radius: 3px; overflow: hidden; flex: none;
}
.conf-bar i { display: block; height: 100%; background: var(--indigo); }
.conf span { font-family: var(--f-mono); font-size: .74rem; color: var(--ink-2); }

.move-up   { color: var(--moss); }
.move-down { color: var(--vermilion); }
.hit { color: var(--indigo); font-weight: 600; }

/* 은퇴 표시 — 현역과 한눈에 구분되게 하되, 이름을 가리지는 않는다 */
.tag-retired {
  display: inline-block;
  margin-left: .4em;
  padding: .1em .45em;
  border: 1px solid var(--rule);
  border-radius: 3px;
  background: var(--surface-2);
  color: var(--ink-3);
  font-size: .68em;
  font-weight: 500;
  vertical-align: middle;
  letter-spacing: .02em;
}
.card.is-retired .t { color: var(--ink-2); }
.move-flat { color: var(--ink-3); }

/* ── 알림 ───────────────────────────── */
.note {
  border-left: 3px solid var(--clay); background: var(--clay-soft);
  padding: 13px 17px; margin: 0 0 22px; font-size: .9rem; color: var(--ink-2);
}
.note.go { border-left-color: var(--moss); background: var(--moss-soft); }
.note.ok { border-left-color: var(--indigo); background: var(--indigo-soft); }
.note strong { color: var(--ink); }
.note :last-child { margin-bottom: 0; }

/* ── 꼬리말 ─────────────────────────── */
.site-foot {
  border-top: 1px solid var(--rule); background: var(--surface);
  padding-block: 26px 40px; font-size: .82rem; color: var(--ink-3);
}
.site-foot p { max-width: 70ch; margin-bottom: 8px; }
.site-foot a { color: var(--ink-2); }

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""

SEARCH_JS = """
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
      a.href = 'rikishi/' + encodeURIComponent(r.i) + '.html';
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
"""
