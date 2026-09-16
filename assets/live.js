
/* 본대회 중 화면을 스스로 새로 고친다.

   정적 사이트라 페이지 자체는 배치가 다시 만들어야 바뀐다. 그래서 여기서는
   **아주 작은 파일(live.json)만 주기적으로 확인**하고, 그 안의 표시가 내가
   보고 있는 것과 달라졌을 때만 페이지를 다시 읽는다.
   화면을 자바스크립트로 고쳐 그리지 않는 이유는, 그러면 같은 것을 두 군데서
   그리게 되어 언젠가 둘이 어긋나기 때문이다. 정답은 늘 서버가 만든 HTML 하나다.

   읽는 중에 갑자기 화면이 바뀌면 성가시므로, 최근에 스크롤·클릭한 사람에게는
   먼저 띠를 보여 주고 누를 때 바꾼다. */
(function () {
  var box = document.getElementById('live-stamp');
  if (!box) return;                       // 본대회 중이 아닌 페이지
  var mine = document.documentElement.getAttribute('data-stamp') || '';
  var EVERY = 60000;                      // 1분마다 확인 (자료는 5분마다 바뀐다)
  var QUIET = 30000;                      // 30초 이상 가만히 있으면 바로 새로고침
  var touched = Date.now();
  var pending = false;

  /* 한 번 새로 고쳤는데도 표시가 그대로면 **다시 조르지 않는다.**
     배포 도중에는 live.json 만 먼저 새것이 되는 순간이 있는데, 그때 그냥
     다시 고치면 '새 결과 → 새로고침 → 또 새 결과' 로 끝없이 돈다.
     (실제로 시험 중에 이 고리가 나왔다) */
  function alreadyTried(stamp) {
    try { return sessionStorage.getItem('pyxi-reload') === stamp; }
    catch (err) { return false; }
  }
  function remember(stamp) {
    try { sessionStorage.setItem('pyxi-reload', stamp); } catch (err) { /* 무시 */ }
  }
  function refresh(stamp) {
    remember(stamp);
    location.reload();
  }

  ['scroll', 'click', 'keydown', 'touchstart'].forEach(function (ev) {
    window.addEventListener(ev, function () { touched = Date.now(); },
                            { passive: true });
  });

  function banner(stamp) {
    if (document.getElementById('live-reload')) return;
    var b = document.createElement('button');
    b.id = 'live-reload';
    b.type = 'button';
    b.className = 'live-reload';
    b.textContent = '새 결과가 들어왔습니다 — 지금 보기';
    b.addEventListener('click', function () { refresh(stamp); });
    document.body.appendChild(b);
  }

  function look() {
    if (document.hidden) return;
    fetch('live.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.stamp) return;
        if (d.stamp === mine) {
          if (d.day) box.textContent = d.day + '일째 · ' + d.updated + ' 기준 (자동 갱신)';
          return;
        }
        if (alreadyTried(d.stamp)) return;   // 이미 시도했다 — 조용히 둔다
        pending = d.stamp;
        if (Date.now() - touched > QUIET) { refresh(d.stamp); } else { banner(d.stamp); }
      })
      .catch(function () { /* 한 번 실패해도 다음에 다시 본다 */ });
  }

  setInterval(look, EVERY);
  // 가만히 있다가 조용해지면 그때 바꾼다
  setInterval(function () {
    if (pending && Date.now() - touched > QUIET) refresh(pending);
  }, 5000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) look();
  });
  look();
})();
