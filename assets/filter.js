
/* 목록을 단추로 걸러 낸다.
   헤야 페이지(일문)와 반즈케 페이지(단)가 같은 장치를 쓴다. 한쪽에서 익힌
   조작이 다른 쪽에서도 그대로 통해야 하기 때문이다.

   설정은 전부 HTML 에 들어 있다:
     data-filter-for   걸러 낼 것들이 들어 있는 상자 (선택자)
     data-filter-attr  각 항목이 달고 있는 표시 속성 (예: data-division)
     data-hash-prefix  주소창에 남길 접두사 (없으면 안 남긴다)
     data-empty        하나도 안 남았을 때 보여 줄 문구 (선택자, 없어도 된다)
   서버도 fetch 도 필요 없고, 파일을 직접 열어도(file://) 그대로 동작한다. */
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
      // 주소창에도 남겨 둔다 — 링크로 공유하거나 새로고침해도 같은 화면이 나온다
      try {
        var url = new URL(window.location.href);
        url.hash = which === 'all' ? '' : prefix + which;
        history.replaceState(null, '', url.toString());
      } catch (err) { /* file:// 에서는 막힐 수 있다 — 걸러내기는 계속 된다 */ }
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
