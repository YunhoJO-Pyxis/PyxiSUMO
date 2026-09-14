"""DB → 정적 HTML 사이트 생성기.

    python -m pyxisumo.site.build --out docs

만들어지는 것
    index.html                현재 반즈케 + 요약
    banzuke/<바쇼>.html        바쇼별 반즈케 (아카이브)
    banzuke/index.html         바쇼 목록
    yosou.html                 차기 반즈케 예측 + 적중률
    rikishi/index.html         검색
    rikishi/<id>.html          프로필 · 성적 이력 · 상대 전적
    heya/index.html            헤야 디렉토리
    assets/style.css, search.js, search-index.json

의존성 없음 — 표준 라이브러리만 쓴다. DB 접근은 sqlrunner 를 통하므로
psycopg 가 있으면 그걸, 없으면 psql 을 쓴다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..romaji import shikona_only
from ..sqlrunner import Runner, SqlError
from . import queries as Q
from .guide import SECTIONS as GUIDE_SECTIONS
from .guide import SOURCES as GUIDE_SOURCES
from .theme import CSS, SEARCH_JS

SITE_NAME = "PyxiSUMO"
SITE_TAGLINE = "스모의 나침반"

# ---------------------------------------------------------------------
#  방문 통계 (선택)
# ---------------------------------------------------------------------
#  정적 사이트에는 서버가 없어 접속 기록이 남지 않는다. 보고 싶으면 방문자
#  브라우저가 집계 서비스에 한 줄을 보내 주어야 한다.
#
#  쿠키를 심지 않고 개인을 식별하지 않는 두 곳만 지원한다. 아무것도 지정하지
#  않으면 **집계 코드가 아예 들어가지 않는다** — 기본이 '추적 없음'이어야 한다.
#
#      PYXISUMO_ANALYTICS=goatcounter:내코드
#      PYXISUMO_ANALYTICS=cloudflare:토큰
ANALYTICS_HOSTS = {
    # 제공자: (스크립트 호스트, 집계를 받는 호스트)
    "goatcounter": ("https://gc.zgo.at", None),
    "cloudflare": ("https://static.cloudflareinsights.com",
                   "https://cloudflareinsights.com"),
}

# 페이지 뼈대가 참고하는 설정. build_site() 가 채운다.
SITE_OPTS: dict[str, Any] = {"analytics": ""}


def analytics_parts(spec: str) -> tuple[str, list[str], list[str]]:
    """집계 설정을 (스크립트 HTML, script-src 호스트, connect-src 호스트) 로.

    모르는 제공자는 조용히 무시한다 — 오타 하나로 사이트 생성이 멈추는 것보다
    통계가 안 잡히는 편이 낫다 (생성 로그에는 남긴다).
    """
    spec = (spec or "").strip()
    if not spec:
        return "", [], []
    provider, _, value = spec.partition(":")
    provider = provider.strip().lower()
    value = value.strip()
    if provider not in ANALYTICS_HOSTS or not value:
        print(f"  (알 수 없는 통계 설정 '{spec}' — 집계 코드를 넣지 않습니다)")
        return "", [], []

    if provider == "goatcounter":
        # 코드에는 영문·숫자·하이픈만 올 수 있다. 그대로 URL 에 넣으면 안 된다.
        code = "".join(c for c in value if c.isalnum() or c == "-")
        if not code:
            return "", [], []
        endpoint = f"https://{code}.goatcounter.com/count"
        html_ = (f'<script data-goatcounter="{e(endpoint)}" async '
                 f'src="https://gc.zgo.at/count.js"></script>')
        return html_, ["https://gc.zgo.at"], [f"https://{code}.goatcounter.com"]

    token = "".join(c for c in value if c.isalnum())
    html_ = ('<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
             f"data-cf-beacon='{{\"token\": \"{token}\"}}'></script>")
    return html_, ["https://static.cloudflareinsights.com"], ["https://cloudflareinsights.com"]


def csp_value(script_hosts: Sequence[str], connect_hosts: Sequence[str]) -> str:
    """콘텐츠 보안 정책.

    기본을 'none' 으로 두고 필요한 것만 연다. 만에 하나 DB 값에 섞인 태그가
    페이지에 새어 나가더라도, 바깥으로 자료를 보내는 코드는 브라우저가 막는다.
    (style 의 'unsafe-inline' 은 확신도 막대 같은 style="" 속성 때문이다.
     인라인 <script> 는 쓰지 않으므로 script 쪽은 열어 두지 않는다.)
    """
    script = " ".join(["'self'", *script_hosts])
    connect = " ".join(["'self'", *connect_hosts])
    return "; ".join([
        "default-src 'none'",
        "base-uri 'self'",
        "form-action 'none'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        f"script-src {script}",
        f"connect-src {connect}",
    ])


ROBOTS_TXT = """# PyxiSUMO
# 사람이 보는 페이지는 모두 공개입니다. 검색 로봇도 환영합니다.
# 다만 자료 파일을 통째로 긁어가는 것은 서버(=GitHub) 에만 부담이 되므로 막습니다.
User-agent: *
Allow: /
Disallow: /rikishi/search-index.json

# 예의 없이 몰아치는 수집기에는 간격을 요청합니다 (강제력은 없습니다).
Crawl-delay: 5
"""

RANK_KO = {
    "Yokozuna": "요코즈나", "Ozeki": "오제키", "Sekiwake": "세키와케",
    "Komusubi": "코무스비", "Maegashira": "마에가시라", "Numbered": "",
}
RANK_JA = {
    "Yokozuna": "横綱", "Ozeki": "大関", "Sekiwake": "関脇",
    "Komusubi": "小結", "Maegashira": "前頭", "Numbered": "",
}
DIV_KO = {"Makuuchi": "마쿠우치", "Juryo": "쥬료", "Makushita": "마쿠시타"}
DIV_JA = {"Makuuchi": "幕内", "Juryo": "十両", "Makushita": "幕下"}
STATUS_KO = {"upcoming": "개막 전", "ongoing": "개최 중",
             "finished": "종료", "unknown": "미정"}

BASIS_KO = {
    "yokozuna_lock": "요코즈나 — 강등 없음 (확정 규칙)",
    "ozeki_art8_hold": "오제키 유지 — 편성요령 8조",
    "ozeki_art8_demotion": "오제키 강등 — 편성요령 8조",
    "ozeki_art8_return": "오제키 특례 복귀 — 10승",
    "ozeki_promotion_signal": "오제키 승격 신호 — 3바쇼 33승 (경험칙)",
    "komusubi_11win_promotion": "코무스비 11승 승격 (경험칙)",
    "east_m1_kachikoshi": "東前頭筆頭 카치코시 (경험칙)",
    "makushita15_zensho": "마쿠시타 15매목 전승 (내규)",
    "sanyaku_fill": "산야쿠 정원 충원",
    "linear": "성적 기반 계산",
}


# ---------------------------------------------------------------------
#  작은 도우미
# ---------------------------------------------------------------------
def e(v: Any) -> str:
    """HTML 이스케이프. 모든 DB 값은 반드시 이걸 통과시킨다."""
    return html.escape("" if v is None else str(v), quote=True)


def i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def basho_label(basho_id: str) -> str:
    s = str(basho_id or "")
    return f"{s[:4]}년 {int(s[4:6])}월" if len(s) >= 6 and s[4:6].isdigit() else s


def rank_display(kind: str, num: Any, division: str) -> tuple[str, str]:
    """(지위 이름, 매수 표시)."""
    if kind and kind != "Numbered":
        return RANK_KO.get(kind, kind), (str(num) if i(num, 1) > 1 or
                                         kind == "Maegashira" else "")
    return DIV_KO.get(division, division), str(num or "")


def rank_ko(kind: str, num: Any, side: str, division: str) -> str:
    """'동 마에가시라 3' 처럼 한국어 한 줄로.

    API 가 주는 'Maegashira 3 East' 를 그대로 쓰면 한국어 페이지에
    영어가 섞인다. 표시는 늘 여기서 만든다.
    """
    if not kind:
        return ""
    head, numtxt = rank_display(kind, num, division)
    s = "동" if side == "E" else ("서" if side == "W" else "")
    return " ".join(x for x in (s, head, numtxt) if x)


def with_ja(ko: Any, ja: Any) -> str:
    """'니쇼노세키 (二所ノ関)' — 한국어 페이지에 일본어를 함께 보인다.

    한자를 모르면 한국어만. 둘이 같으면 (아직 음역 전이면) 하나만.
    """
    k = str(ko or "").strip()
    j = str(ja or "").strip()
    if not k:
        return j
    if not j or j == k:
        return k
    return f"{k} ({j})"


def move_txt(diff_slots: int | None) -> tuple[str, str]:
    """예측 대비 실제가 얼마나 위/아래였는지 → (표시, CSS 클래스).

    1매 = 東西 두 칸이므로 슬롯 차이를 2로 나눈다. 반매(한 칸) 차이는 '0.5매'.
    부호는 **실제 기준**이다 — 실제가 예측보다 위면 ▲.
    """
    if diff_slots is None:
        return "—", ""
    if diff_slots == 0:
        return "적중", "hit"
    maisu = abs(diff_slots) / 2.0
    txt = f"{maisu:.1f}".rstrip("0").rstrip(".")
    return (f"▲ {txt}매", "move-up") if diff_slots > 0 else (f"▼ {txt}매", "move-down")


def heya_cell(ko: Any, ja: Any) -> str:
    """표 안에서 쓰는 헤야 칸 — 한국어 한 줄, 한자 한 줄.

    '니쇼노세키 (二所ノ関)' 을 한 줄로 넣으면 칸이 좁은 표(예측표는 9열이다)에서
    글자가 한 자씩 세로로 쪼개져 읽을 수 없게 된다. 두 줄로 나누면 폭이 절반이
    되고, nowrap 으로 줄바꿈 자체를 막는다.
    """
    k = str(ko or "").strip()
    j = str(ja or "").strip()
    if not k:
        k, j = j, ""
    out = f'<span class="hy-ko">{e(k)}</span>'
    if j and j != k:
        out += f'<span class="hy-ja">{e(j)}</span>'
    return f'<td class="heya">{out}</td>'


def rec_txt(w: Any, l: Any, a: Any) -> str:
    """'12승 3패' — 성적이 아예 없으면 빈 문자열."""
    w, l, a = i(w), i(l), i(a)
    if w + l + a == 0:
        return ""
    return f"{w}승 {l}패" + (f" {a}휴" if a else "")


def record_html(w: Any, l: Any, a: Any) -> str:
    body = rec_txt(w, l, a)
    if not body:
        # 개막 전 대회는 성적 줄을 아예 만들지 않는다 — 빈 줄이 표를 늘린다
        return ""
    cls = "kachi" if i(w) > i(l) + i(a) else ("make" if i(w) < i(l) + i(a) else "")
    return f'<span class="bz-rec"><span class="{cls}">{e(body)}</span></span>'


# ---------------------------------------------------------------------
#  페이지 뼈대
# ---------------------------------------------------------------------
NAV = [
    ("", "현재 반즈케", "index.html"),
    ("yosou", "예측", "yosou.html"),
    ("rikishi", "선수 검색", "rikishi/index.html"),
    ("heya", "헤야", "heya/index.html"),
    ("banzuke", "지난 대회", "banzuke/index.html"),
    ("guide", "스모 기초 지식", "guide.html"),
]


def page(
    *, title: str, body: str, depth: int = 0, current: str = "",
    description: str = "", generated: str = "",
) -> str:
    up = "../" * depth
    nav = "".join(
        f'<a href="{up}{href}"'
        + (' aria-current="page"' if key == current else "")
        + f">{e(label)}</a>"
        for key, label, href in NAV
    )
    desc = description or f"{SITE_NAME} — 일본 스모 반즈케와 예측"
    tag, s_hosts, c_hosts = analytics_parts(SITE_OPTS.get("analytics", ""))
    csp = csp_value(s_hosts, c_hosts)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{e(csp)}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{e(title)} · {SITE_NAME}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)} · {SITE_NAME}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Serif+JP:wght@700;900&display=swap">
<link rel="stylesheet" href="{up}assets/style.css">
</head>
<body>
<header class="site-head"><div class="wrap">
  <a class="brand" href="{up}index.html"><b>{SITE_NAME}</b><span>{e(SITE_TAGLINE)}</span></a>
  <nav class="site-nav">{nav}</nav>
</div></header>
<div class="wrap">
{body}
</div>
<footer class="site-foot"><div class="wrap">
  <p>성적·반즈케 데이터 출처: <a href="https://www.sumo-api.com/">Sumo-API</a>.
     대전 결과와 서열은 사실 정보이며, 이 사이트는 그것을 구조화해 제공합니다.</p>
  <p>예측은 공식 발표가 아닙니다. 반즈케는 일본스모협회(日本相撲協会) 심판부가 편성하며,
     매수 변동의 대부분은 성문 규정이 아닌 관례입니다.</p>
  <p>{e(generated)}</p>
</div></footer>
{tag}
</body>
</html>
"""


# ---------------------------------------------------------------------
#  반즈케 표
# ---------------------------------------------------------------------
def banzuke_table(rows: Sequence[Sequence[Any]], depth: int = 0) -> str:
    """rank_value 기준으로 東/西 를 한 줄에 묶어 그린다."""
    up = "../" * depth
    slots: dict[tuple[str, str, int], dict[str, Any]] = {}
    order: list[tuple[str, str, int]] = []

    for r in rows:
        (rank_value, division, kind, num, side, rank_label,
         w, l, a, net, rid, name, name_ja, name_en, name_kana,
         heya, heya_ja) = r[:17]
        key = (division, kind, i(num, 1))
        if key not in slots:
            slots[key] = {"division": division, "kind": kind, "num": i(num, 1)}
            order.append(key)
        slots[key][side] = {
            "id": rid, "name": name, "ja": name_ja,
            "heya": with_ja(heya, heya_ja),
            "w": w, "l": l, "a": a,
        }

    def side_cell(d: dict | None, side: str) -> str:
        cls = "bz-side" + (" w" if side == "W" else "")
        label = "東" if side == "E" else "西"
        if not d:
            return f'<div class="{cls} empty" data-side="{label}"></div>'
        link = f'{up}rikishi/{e(d["id"])}.html'
        # 반즈케에 적히는 것은 시코나뿐이다. API 가 '照ノ富士　春雄' 처럼
        # 본명까지 주는 경우가 있어, 표에서는 앞부분만 보인다.
        ja = (f'<div class="bz-ja">{e(shikona_only(d["ja"]))}</div>'
              if d.get("ja") else "")
        heya = f'<div class="bz-heya">{e(d["heya"])}</div>' if d.get("heya") else ""
        return (
            f'<div class="{cls}" data-side="{label}">'
            f'<div class="bz-name"><a href="{link}">{e(d["name"])}</a></div>'
            f"{ja}{heya}{record_html(d['w'], d['l'], d['a'])}</div>"
        )

    out: list[str] = ['<div class="banzuke">',
                      '<div class="bz-head"><div>東</div><div class="c">지위</div>'
                      '<div style="text-align:right">西</div></div>']
    seen_div: set[str] = set()
    for key in order:
        s = slots[key]
        div = s["division"]
        if div not in seen_div:
            seen_div.add(div)
            out.append(f'<div class="div-break">{e(DIV_KO.get(div, div))}'
                       f' · {e(DIV_JA.get(div, ""))}</div>')
        ko, numtxt = rank_display(s["kind"], s["num"], div)
        ja = RANK_JA.get(s["kind"], "") or DIV_JA.get(div, "")
        rk_cls = "rk-" + (s["kind"].lower() if s["kind"] != "Numbered"
                          else div.lower())
        out.append(
            f'<div class="bz-row">{side_cell(s.get("E"), "E")}'
            f'<div class="bz-rank {rk_cls}">'
            f'<span class="k">{e(ko)}</span>'
            f'<span class="n">{e(ja)}{(" " + numtxt) if numtxt else ""}</span>'
            f"</div>{side_cell(s.get('W'), 'W')}</div>"
        )
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------------
#  각 페이지
# ---------------------------------------------------------------------
def build_index(rn: Runner, out: Path, basho: Sequence, gen: str) -> None:
    stats = rn.query(Q.SITE_STATS)
    st = stats[0] if stats else (0, 0, 0, 0, "", "")
    cur = basho[0]
    bid, name, name_ja, venue, start, end, status, n_entries, played = cur[:9]
    rows = rn.query(Q.BANZUKE, (bid,))

    pill = f'<span class="status-pill st-{e(status)}">{e(STATUS_KO.get(status, status))}</span>'
    when = f"{start} ~ {end}" if start and end else ""

    body = f"""
<div class="page-head">
  <p class="eyebrow">{e(basho_label(bid))} · {e(venue or "")}</p>
  <h1>{e(with_ja(name, name_ja))} 반즈케{pill}</h1>
  <p class="sub">{e(when)} · 총 {i(n_entries)}명</p>
</div>
<main>
{banzuke_table(rows)}
<h2>수록 현황</h2>
<div class="grid">
  <div class="stat"><span class="k">리키시</span><span class="v">{i(st[0]):,}</span>
    <span class="d">은퇴 선수 포함</span></div>
  <div class="stat"><span class="k">반즈케 기록</span><span class="v">{i(st[1]):,}</span>
    <span class="d">{i(st[3]):,}개 대회</span></div>
  <div class="stat"><span class="k">대전 기록</span><span class="v">{i(st[2]):,}</span>
    <span class="d">{e(basho_label(st[4]))} ~ {e(basho_label(st[5]))}</span></div>
</div>
</main>
"""
    (out / "index.html").write_text(
        page(title=f"{name} 반즈케", body=body, current="", generated=gen,
             description=f"{basho_label(bid)} {name} 반즈케 — 마쿠우치·쥬료 전원의 지위와 성적"),
        encoding="utf-8")


def build_banzuke_pages(rn: Runner, out: Path, basho: Sequence, gen: str) -> None:
    d = out / "banzuke"
    d.mkdir(parents=True, exist_ok=True)

    cards = []
    for b in basho:
        bid, name, name_ja, venue, start, end, status, n, played = b[:9]
        cards.append(
            f'<a class="card" href="{e(bid)}.html">'
            f'<div class="t">{e(basho_label(bid))} {e(with_ja(name, name_ja))}</div>'
            f'<div class="ja">{e(venue or "")}</div>'
            f'<div class="m">{i(n)}명 · '
            f'<span class="status-pill st-{e(status)}">'
            f'{e(STATUS_KO.get(status, status))}</span></div></a>'
        )
    body = f"""
<div class="page-head">
  <p class="eyebrow">아카이브</p>
  <h1>지난 대회</h1>
  <p class="sub">수록된 {len(basho)}개 대회의 반즈케입니다. 대회를 눌러 서열표를 보세요.</p>
</div>
<main><div class="cards">{"".join(cards)}</div></main>
"""
    (d / "index.html").write_text(
        page(title="지난 대회", body=body, depth=1, current="banzuke", generated=gen),
        encoding="utf-8")

    for b in basho:
        bid, name, name_ja, venue, start, end, status, n, played = b[:9]
        rows = rn.query(Q.BANZUKE, (bid,))
        pill = (f'<span class="status-pill st-{e(status)}">'
                f'{e(STATUS_KO.get(status, status))}</span>')
        pbody = f"""
<div class="page-head">
  <p class="eyebrow"><a href="index.html">지난 대회</a> · {e(venue or "")}</p>
  <h1>{e(basho_label(bid))} {e(with_ja(name, name_ja))}{pill}</h1>
  <p class="sub">{e(start or "")} ~ {e(end or "")} · {i(n)}명</p>
</div>
<main>{banzuke_table(rows, depth=1)}</main>
"""
        (d / f"{bid}.html").write_text(
            page(title=f"{basho_label(bid)} {name}", body=pbody, depth=1,
                 current="banzuke", generated=gen,
                 description=f"{basho_label(bid)} {name} 반즈케 전체"),
            encoding="utf-8")


def build_yosou(rn: Runner, out: Path, gen: str) -> None:
    run = rn.query(Q.LATEST_PREDICTION)
    acc = rn.query(Q.ACCURACY_HISTORY)

    if not run:
        body = """
<div class="page-head">
  <p class="eyebrow">반즈케 예측</p>
  <h1>아직 예측이 없습니다</h1>
  <p class="sub">대회가 끝난 다음 날 예측을 만들 수 있습니다.</p>
</div>
<main><div class="note">
  <p><strong>예측은 언제 만드나요?</strong> 대회 마지막 날(千秋楽) 다음 날부터
  다음 반즈케 발표일까지 약 4주간이 예측을 게시할 수 있는 기간입니다.
  <code>4_예측하기</code> 를 실행하면 만들어집니다.</p>
</div></main>
"""
        (out / "yosou.html").write_text(
            page(title="반즈케 예측", body=body, current="yosou", generated=gen),
            encoding="utf-8")
        return

    run_id, target, source, model, created = run[0][:5]
    rows = [r[:25] for r in rn.query(Q.PREDICTION_ENTRIES, (run_id,))]

    # 예측한 대회의 반즈케가 실제로 발표되었는가?
    #   한 명이라도 실제 지위가 들어와 있으면 '발표됨'으로 본다.
    published = any(r[20] for r in rows)

    # 차이는 예측 엔진과 **같은 자를 쓴다.** 슬롯 사다리로 재지 않고 rank_value 를
    # 빼면 지위·디비전 경계에서 값이 튀어, 표의 '차이'와 아래 적중률이 어긋난다.
    ladder: dict = {}
    if published:
        from ..predict import _slot_ladder
        from ..ranks import Rank

        ranks: list[Rank] = []
        for r in rows:
            ranks.append(Rank(r[1], r[2], i(r[3], 1), r[4]))
            if r[20]:
                ranks.append(Rank(r[23], r[20], i(r[21], 1), r[22]))
        ladder = _slot_ladder(ranks)

    def slot(div: Any, kind: Any, num: Any, side: Any):
        return ladder.get((str(div), str(kind), i(num, 1), str(side)))

    trs = []
    tally = {"n": 0, "exact": 0, "within1": 0, "err": 0.0}
    for r in rows:
        (prv, division, kind, num, side, conf, basis, rid, name, name_ja,
         heya, heya_ja, prev_label, w, l, a,
         pkind, pnum, pside, pdiv,
         akind, anum, aside, adiv, alabel) = r
        ko, numtxt = rank_display(kind, num, division)
        side_ko = "동" if side == "E" else "서"
        c = f(conf)

        act_html = ""
        if published:
            if akind:
                p_slot = slot(division, kind, num, side)
                a_slot = slot(adiv, akind, anum, aside)
                diff = (p_slot - a_slot) if (p_slot is not None
                                             and a_slot is not None) else None
                txt, cls = move_txt(diff)
                if diff is not None:
                    tally["n"] += 1
                    tally["err"] += abs(diff) / 2.0
                    if diff == 0:
                        tally["exact"] += 1
                    if abs(diff) / 2.0 <= 1.0:
                        tally["within1"] += 1
                act_html = (
                    f'<td class="num">{e(rank_ko(akind, anum, aside, adiv))}</td>'
                    f'<td class="num"><span class="{cls}">{e(txt)}</span></td>')
            else:
                # 예측에는 있었는데 실제 반즈케에는 없다 — 인퇴·강등으로 빠진 경우
                act_html = ('<td class="num" style="color:var(--ink-3)">명단 없음</td>'
                            '<td class="num">—</td>')

        # 근거를 따로 열로 두면 열이 9개가 되어 표가 화면을 넘고, 다른 칸까지
        # 찌그러진다 (근거 칸이 '성 적 기 반' 처럼 한 글자씩 쪼개졌다).
        # 지위 바로 밑에 작은 글씨로 붙이면 열 하나가 줄어든다.
        basis_ko = BASIS_KO.get(basis, basis or "")
        trs.append(
            f'<tr><td class="num">{e(side_ko)} {e(ko)} {e(numtxt)}'
            + (f'<div class="basis">{e(basis_ko)}</div>' if basis_ko else "")
            + '</td>'
            f'<td class="name"><a href="rikishi/{e(rid)}.html">{e(name)}</a>'
            f'<div class="bz-ja">{e(shikona_only(name_ja))}</div></td>'
            + heya_cell(heya, heya_ja) +
            act_html +
            f'<td class="num">{e(rank_ko(pkind, pnum, pside, pdiv) or "—")}</td>'
            f'<td class="num">{i(w)}-{i(l)}' + (f"-{i(a)}휴" if i(a) else "") + "</td>"
            f'<td><div class="conf"><span class="conf-bar">'
            f'<i style="width:{max(4, min(100, round(c * 100)))}%"></i></span>'
            f"<span>{c:.0%}</span></div></td>"
            '</tr>' 
        )

    # 발표 여부에 따라 머리글과 안내가 달라진다
    if published and tally["n"]:
        n = tally["n"]
        compare_head = "<th>실제 지위</th><th>차이</th>"
        compare_note = f"""
<div class="note ok">
  <p><strong>실제 반즈케가 발표되었습니다.</strong> '실제 지위'는 발표된 반즈케입니다.
  '차이'는 <span class="move-up">▲ 실제가 예측보다 위</span>(=예측이 낮게 봤다) ·
  <span class="move-down">▼ 실제가 예측보다 아래</span>(=예측이 높게 봤다) 입니다.</p>
  <p style="margin-top:.5rem">
    대상 {n}명 중 <strong>적중 {tally['exact']}명</strong>
    ({tally['exact'] / n:.1%}) ·
    <strong>±1매 이내 {tally['within1']}명</strong>
    ({tally['within1'] / n:.1%}) ·
    평균 오차 {tally['err'] / n:.2f}매</p>
</div>"""
    elif published:
        compare_head = "<th>실제 지위</th><th>차이</th>"
        compare_note = ('<div class="note"><p>실제 반즈케는 발표되었지만 '
                        '예측한 선수와 맞춰볼 수 있는 항목이 없습니다.</p></div>')
    else:
        compare_head = ""
        compare_note = f"""
<div class="note">
  <p><strong>실제 반즈케 발표 전입니다.</strong>
  {e(basho_label(target))} 반즈케가 발표되면 이 자리에 실제 지위와 예측과의 차이가
  함께 표시됩니다. 반즈케는 보통 대회 개막 약 2주 전 월요일에 발표됩니다.</p>
</div>"""

    acc_html = ""
    if acc:
        arows = "".join(
            f'<tr><td class="num">{e(basho_label(a0))}</td>'
            f'<td class="num">{f(a3):.1%}</td>'
            f'<td class="num"><strong>{f(a4):.1%}</strong></td>'
            f'<td class="num">{f(a5):.2f}매</td>'
            f'<td class="num">{i(a2)}명</td>'
            f'<td class="num" style="color:var(--ink-3)">{e(a1)}</td></tr>'
            for (a0, a1, a2, a3, a4, a5, a6, a7) in (r[:8] for r in acc)
        )
        acc_html = f"""
<h2>적중률</h2>
<p>발표된 반즈케와 맞춰본 결과입니다. <strong>±1매 이내</strong>가 실제로 체감하는
정확도이고, 완전 일치는 동·서까지 맞아야 하는 가장 엄격한 기준입니다.</p>
<div class="table-scroll"><table>
<thead><tr><th>대회</th><th>완전 일치</th><th>±1매 이내</th><th>평균 오차</th>
<th>대상</th><th>모델</th></tr></thead>
<tbody>{arows}</tbody></table></div>
"""
    else:
        acc_html = """
<h2>적중률</h2>
<div class="note"><p>아직 채점된 예측이 없습니다.
예측한 대회의 반즈케가 실제로 발표되면 자동으로 채점됩니다.</p></div>
"""

    body = f"""
<div class="page-head">
  <p class="eyebrow">반즈케 예측 · {e(model)}</p>
  <h1>{e(basho_label(target))} 예상 반즈케</h1>
  <p class="sub">{e(basho_label(source))} 성적을 근거로 계산했습니다.
     {e(created)} 생성 · 공식 발표가 아닙니다.</p>
</div>
<main>
<div class="note">
  <p><strong>반즈케에는 정확한 규칙이 거의 없습니다.</strong>
  성문 규정은 오제키 강등·복귀(편성요령 8조), 각 단 정원, 산야쿠 최소 정원 정도이고
  매수 변동은 대부분 관례입니다. 그래서 이 예측은 정답이 아니라
  <strong>재현 가능한 계산과 정직한 적중률</strong>을 목표로 합니다.</p>
</div>
{compare_note}
<div class="table-scroll"><table class="{'wide' if compare_head else ''}">
<thead><tr><th>예상 지위</th><th>선수</th><th>헤야</th>{compare_head}<th>직전 지위</th>
<th>직전 성적</th><th>확신도</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>
{acc_html}
</main>
"""
    (out / "yosou.html").write_text(
        page(title=f"{basho_label(target)} 예상 반즈케", body=body,
             current="yosou", generated=gen,
             description=f"{basho_label(target)} 반즈케 예측과 과거 적중률"),
        encoding="utf-8")


def build_rikishi(rn: Runner, out: Path, gen: str) -> int:
    d = out / "rikishi"
    d.mkdir(parents=True, exist_ok=True)
    people = rn.query(Q.PROFILE_RIKISHI)

    # 선수마다 따로 묻지 않는다 — 한 번에 받아 파이썬에서 묶는다.
    # (원격 DB에서는 왕복 한 번이 0.1초쯤이라, 1,500명이면 그것만 5분이다)
    hist_by: dict[Any, list] = {}
    for r in rn.query(Q.RIKISHI_HISTORY_ALL):
        hist_by.setdefault(str(r[0]), []).append(r[1:12])

    opp_by: dict[Any, list] = {}
    for r in rn.query(Q.RIKISHI_OPPONENTS_ALL):
        opp_by.setdefault(str(r[0]), []).append(r[1:6])

    index: list[dict[str, Any]] = []
    for p in people:
        (rid, name, name_ja, name_en, name_kana, heya, heya_ja, heya_slug,
         shusshin, height, weight, birth, debut, retired,
         n_basho, best_rv, best_label, best_kind, best_num, best_side, best_div,
         tw, tl, ta, last_basho) = p[:25]

        hist = hist_by.get(str(rid), [])
        opps = opp_by.get(str(rid), [])[:20]   # 상대 전적은 많이 붙은 순 20명

        hrows = "".join(
            f'<tr><td class="num"><a href="../banzuke/{e(h0)}.html">'
            f'{e(basho_label(h0))}</a></td>'
            f'<td class="name">{e(rank_ko(h8, h9, h10, h4))}</td>'
            f'<td class="num">{rec_txt(h5, h6, h7)}</td></tr>'
            for (h0, h1, h2, h3, h4, h5, h6, h7, h8, h9, h10)
            in (r[:11] for r in hist)
        )

        orows = "".join(
            f'<tr><td class="name"><a href="{e(o0)}.html">{e(o1)}</a></td>'
            f'<td class="num">{i(o2)}</td>'
            f'<td class="num"><span class="move-up">{i(o3)}</span>'
            f' — <span class="move-down">{i(o4)}</span></td></tr>'
            for (o0, o1, o2, o3, o4) in (r[:5] for r in opps)
        ) or '<tr><td colspan="3" style="color:var(--ink-3)">수록된 대전이 없습니다</td></tr>'

        meta = []
        if heya:
            meta.append(f"{e(with_ja(heya, heya_ja))} 소속")
        if shusshin:
            meta.append(e(shusshin))
        if height and weight:
            meta.append(f"{f(height):.0f}cm · {f(weight):.0f}kg")
        if retired:
            meta.append(f"{e(basho_label(retired))} 은퇴")

        body = f"""
<div class="page-head">
  <p class="eyebrow"><a href="index.html">선수 검색</a></p>
  <h1>{e(name)} <span class="bz-ja" style="font-size:1.1rem">{e(name_ja or "")}</span>{'<span class="tag-retired">은퇴</span>' if retired else ""}</h1>
  <p class="sub">{" · ".join(meta)}</p>
</div>
<main>
<div class="grid">
  <div class="stat"><span class="k">최고 지위</span>
    <span class="v" style="font-size:1.15rem">
      {e(rank_ko(best_kind, best_num, best_side, best_div) or "—")}</span></div>
  <div class="stat"><span class="k">세키토리 재적</span>
    <span class="v">{i(n_basho)}</span><span class="d">개 대회</span></div>
  <div class="stat"><span class="k">통산 (수록분)</span>
    <span class="v" style="font-size:1.15rem">{i(tw)}승 {i(tl)}패</span>
    <span class="d">{i(ta)}휴</span></div>
</div>
<h2>대회별 성적</h2>
<div class="table-scroll"><table>
<thead><tr><th>대회</th><th>지위</th><th>성적</th></tr></thead>
<tbody>{hrows}</tbody></table></div>
<h2>상대 전적</h2>
<p>2번 이상 맞붙은 상대입니다. 수록된 대전 기록 범위 안에서만 집계됩니다.</p>
<div class="table-scroll"><table>
<thead><tr><th>상대</th><th>대전</th><th>승 — 패</th></tr></thead>
<tbody>{orows}</tbody></table></div>
</main>
"""
        (d / f"{rid}.html").write_text(
            page(title=str(name), body=body, depth=1, current="rikishi", generated=gen,
                 description=f"{name} ({name_ja or ''}) 프로필 · 성적 이력 · 상대 전적"),
            encoding="utf-8")

        index.append({
            "i": rid, "n": name, "j": shikona_only(name_ja), "e": name_en or "",
            "k": name_kana or "", "h": heya or "", "r": best_label or "",
            # 은퇴 여부. 현역과 섞여 나오면 지금 뛰는 선수인 줄 알게 된다.
            "x": 1 if retired else 0,
        })

    index_json = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    (d / "search-index.json").write_text(index_json, encoding="utf-8")

    # 페이지 안에 직접 심는다 — 파일을 더블클릭해서 열어도 검색이 되게.
    # </script> 가 자료에 섞여 들어가 스크립트를 끊는 사고만 막으면 된다.
    inline_json = index_json.replace("</", "<\\/")

    sbody = f"""
<div class="page-head">
  <p class="eyebrow">선수 검색</p>
  <h1>리키시 찾기</h1>
  <p class="sub">반즈케에 오른 적이 있는 {len(index):,}명을 수록했습니다.</p>
</div>
<main>
<div class="search-box">
  <label for="q" class="visually-hidden"></label>
  <input id="q" type="search" placeholder="이름을 입력하세요 — 大の里 / Onosato / 오노사토"
         autocomplete="off" autocapitalize="off" spellcheck="false">
  <p class="hint">한국어·일본어·영어·가나 어느 쪽으로 쳐도 찾습니다. 헤야 이름도 됩니다.</p>
</div>
<div id="results"></div>
</main>
<script id="search-data" type="application/json">{inline_json}</script>
<script src="../assets/search.js"></script>
"""
    (d / "index.html").write_text(
        page(title="리키시 찾기", body=sbody, depth=1, current="rikishi", generated=gen,
             description="시코나를 한국어·일본어·영어로 검색"),
        encoding="utf-8")
    return len(index)


def build_heya(rn: Runner, out: Path, gen: str) -> int:
    d = out / "heya"
    d.mkdir(parents=True, exist_ok=True)
    rows = rn.query(Q.HEYA_LIST)

    # 헤야마다 따로 묻지 않는다 (위와 같은 이유)
    members_by: dict[str, list] = {}
    for r in rn.query(Q.HEYA_MEMBERS_ALL):
        members_by.setdefault(str(r[0]), []).append(r[1:10])

    cards = []
    for r in rows:
        (slug, name, name_ja, name_en, yt, x, ig, url, n_active, n_sekitori) = r[:10]
        links = []
        if yt:
            links.append(f'<a class="chip" href="https://www.youtube.com/channel/{e(yt)}"'
                         f' target="_blank" rel="noopener">YouTube</a>')
        if x:
            links.append(f'<a class="chip" href="https://x.com/{e(x)}"'
                         f' target="_blank" rel="noopener">X</a>')
        if ig:
            links.append(f'<a class="chip" href="https://instagram.com/{e(ig)}"'
                         f' target="_blank" rel="noopener">Instagram</a>')
        if url:
            links.append(f'<a class="chip" href="{e(url)}"'
                         f' target="_blank" rel="noopener">공식</a>')

        members = members_by.get(str(slug), [])
        mnames = " · ".join(e(m[1]) for m in members[:6])  # 이름만
        if len(members) > 6:
            mnames += f" 외 {len(members) - 6}명"

        cards.append(
            f'<div class="card"><div class="t">{e(with_ja(name, name_ja))}</div>'
            f'<div class="ja">{e(name_en or "")}</div>'
            f'<div class="m">세키토리 {i(n_sekitori)}명'
            + (f" · {mnames}" if mnames else "")
            + "</div>"
            + (f'<div class="links">{"".join(links)}</div>' if links else "")
            + "</div>"
        )

    body = f"""
<div class="page-head">
  <p class="eyebrow">헤야 디렉토리</p>
  <h1>스모 헤야</h1>
  <p class="sub">{len(rows)}개 헤야. 공식 YouTube·SNS 가 확인된 곳은 링크를 붙였습니다.</p>
</div>
<main>
<div class="note">
  <p>협회가 2025년 4월 통달로 헤야 SNS 를 규제하면서,
  <strong>본대회 기간 중에는 새 영상이 올라오지 않습니다.</strong>
  홀수 달에 채널이 조용한 것은 정상입니다.</p>
</div>
<div class="cards">{"".join(cards)}</div>
</main>
"""
    (d / "index.html").write_text(
        page(title="스모 헤야", body=body, depth=1, current="heya", generated=gen,
             description="헤야별 소속 세키토리와 공식 YouTube·SNS 링크"),
        encoding="utf-8")
    return len(rows)


def build_guide(out: Path, gen: str) -> int:
    """스모 기초 지식 — DB 를 보지 않는 유일한 페이지.

    내용은 guide.py 에 있다. 여기서는 블록을 HTML 로 옮기기만 한다.
    글에도 사용자 입력은 없지만 e() 를 그대로 통과시킨다 — 예외를 만들면
    나중에 누가 DB 값을 여기에 끼워 넣었을 때 그 구멍이 조용히 열린다.
    """
    def render(kind: str, data: Any) -> str:
        if kind == "p":
            return f"<p>{e(data)}</p>"
        if kind == "note":
            return f'<div class="note"><p>{e(data)}</p></div>'
        if kind == "table":
            head = "".join(f"<th>{e(h)}</th>" for h in data["head"])
            rows = "".join(
                "<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>"
                for r in data["rows"]
            )
            foot = (f'<p class="g-foot">{e(data["foot"])}</p>'
                    if data.get("foot") else "")
            return (f'<div class="table-scroll"><table class="g-table">'
                    f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody>"
                    f"</table></div>{foot}")
        if kind == "dl":
            items = "".join(
                f"<dt>{e(ko)}"
                + (f'<span class="g-ja">{e(ja)}</span>' if ja and ja != "—" else "")
                + f"</dt><dd>{e(desc)}</dd>"
                for ko, ja, desc in data
            )
            return f'<dl class="g-dl">{items}</dl>'
        raise ValueError(f"알 수 없는 블록 종류: {kind}")

    toc = "".join(
        f'<a class="chip" href="#{e(s["id"])}">{e(s["title"])}</a>'
        for s in GUIDE_SECTIONS
    )
    parts = []
    for s in GUIDE_SECTIONS:
        inner = "".join(render(k, d) for k, d in s["blocks"])
        parts.append(
            f'<section class="g-sec" id="{e(s["id"])}">'
            f'<h2>{e(s["title"])}</h2>{inner}</section>'
        )
    srcs = "".join(
        f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(t)}</a></li>'
        for t, u in GUIDE_SOURCES
    )

    body = f"""
<div class="page-head">
  <p class="eyebrow">처음 보는 사람을 위한 안내</p>
  <h1>스모 기초 지식</h1>
  <p class="sub">마쿠우치·마에가시라·쥬료가 무엇인지, 이 사이트의 표를 읽는 데
     필요한 만큼만 정리했습니다.</p>
</div>
<main>
<nav class="g-toc" aria-label="목차">{toc}</nav>
{"".join(parts)}
<section class="g-sec" id="sources">
  <h2>출처</h2>
  <p>정원과 내규는 아래 자료를 확인하고 적었습니다. 정원은 바뀌는 일이
     있으므로 본문에 '언제부터'를 함께 적어 두었습니다.</p>
  <ul class="g-src">{srcs}</ul>
</section>
</main>
"""
    (out / "guide.html").write_text(
        page(title="스모 기초 지식", body=body, current="guide", generated=gen,
             description="마쿠우치·쥬료·마에가시라 등 스모 반즈케를 읽는 데 "
                         "필요한 기본 용어 정리"),
        encoding="utf-8")
    return len(GUIDE_SECTIONS)


# ---------------------------------------------------------------------
#  진입점
# ---------------------------------------------------------------------
def build_site(dsn: str, outdir: str | Path, *, quiet: bool = False,
               analytics: str | None = None) -> dict[str, int]:
    SITE_OPTS["analytics"] = (
        analytics if analytics is not None
        else os.environ.get("PYXISUMO_ANALYTICS", ""))
    out = Path(outdir)
    if out.exists():
        for child in out.iterdir():
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    out.mkdir(parents=True, exist_ok=True)

    rn = Runner(dsn)
    gen = "생성 " + datetime.now().strftime("%Y-%m-%d %H:%M")

    basho = rn.query(Q.BASHO_LIST)
    if not basho:
        raise SqlError(
            "반즈케가 들어 있는 대회가 없습니다. 먼저 데이터를 받아 주세요 "
            "(1_설치하기 또는 3_이어받기)."
        )

    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "style.css").write_text(CSS, encoding="utf-8")
    (assets / "search.js").write_text(SEARCH_JS, encoding="utf-8")
    # GitHub Pages 가 Jekyll 로 처리하지 않도록
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "robots.txt").write_text(ROBOTS_TXT, encoding="utf-8")

    stats = {"basho": len(basho)}
    build_index(rn, out, basho, gen)
    build_banzuke_pages(rn, out, basho, gen)
    build_yosou(rn, out, gen)
    stats["rikishi"] = build_rikishi(rn, out, gen)
    stats["heya"] = build_heya(rn, out, gen)
    build_guide(out, gen)
    stats["files"] = sum(1 for _ in out.rglob("*") if _.is_file())

    if not quiet:
        print(f"  대회 {stats['basho']}개 · 선수 {stats['rikishi']}명 · "
              f"헤야 {stats['heya']}개 · 파일 {stats['files']}개")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="정적 사이트 생성")
    ap.add_argument("--out", default="docs",
                    help="출력 폴더 (GitHub Pages 는 docs 를 씁니다)")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--analytics", default=None,
                    help="방문 통계 (예: goatcounter:내코드). 비워 두면 넣지 않습니다")
    args = ap.parse_args(argv)

    if not args.dsn:
        print("DATABASE_URL 이 없습니다.", file=sys.stderr)
        return 2
    try:
        build_site(args.dsn, args.out, analytics=args.analytics)
    except SqlError as e_:
        print(f"오류: {e_}", file=sys.stderr)
        return 1
    print(f"  완성 — {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
