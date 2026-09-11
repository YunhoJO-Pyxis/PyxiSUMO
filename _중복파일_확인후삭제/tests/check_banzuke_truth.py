"""생성된 사이트가 **사실과 맞는지** 본다.

    DATABASE_URL=... python tests/check_banzuke_truth.py --dir docs

왜 필요한가
-----------
기존 검사(check_site.py)는 태그가 닫혔는지, 링크가 살아 있는지, 한국어로
나오는지만 봤다. 그래서 요코즈나 자리에 엉뚱한 사람이 앉아 있어도 **전부
통과했다.** 모양만 보고 내용을 안 본 것이다.

이 검사는 실제 반즈케(tests/fixtures/banzuke_202609.json — 일본상撲협회 공식
반즈케와 같은 내용)를 기준으로 삼아, 화면에 나온 사람이 그 자리의 사람이
맞는지 대조한다.

  1) 요코즈나·오제키·세키와케·코무스비 자리에 앉은 사람이 실제와 같은가
  2) 각 지위의 인원이 실제와 같은가 (오제키 3명, 세키와케 2명 …)
  3) 선수마다 소속 헤야가 실제와 같은가
  4) 이름 음역이 실제 시코나와 이어지는가 (로마자가 남지 않았는가)

DB만 보는 검사가 아니라 **최종 HTML** 을 읽어서 대조한다. DB가 맞아도
표시 단계에서 뒤섞이면 사용자가 보는 것은 틀린 화면이기 때문이다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.heya_names import japanese_for          # noqa: E402
from pyxisumo.romaji import to_hangul                 # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "banzuke_202609.json"

RANK_KO = {"Yokozuna": "요코즈나", "Ozeki": "오제키", "Sekiwake": "세키와케",
           "Komusubi": "코무스비", "Maegashira": "마에가시라", "Numbered": "쥬료"}

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


# HTML 한 칸에서 (이름, 헤야) 를 꺼낸다.
CELL = re.compile(
    r'<div class="bz-side[^"]*" data-side="(?P<side>[東西])">'
    r'(?:(?!</div></div>).)*?'
    r'<div class="bz-name"><a[^>]*>(?P<name>[^<]*)</a></div>'
    r'(?:<div class="bz-ja">(?P<ja>[^<]*)</div>)?'
    r'(?:<div class="bz-heya">(?P<heya>[^<]*)</div>)?',
    re.S,
)
ROW = re.compile(r'<div class="bz-row"[^>]*>(?:(?!<div class="bz-row").)*?'
                 r'(?=<div class="bz-row"|<div class="div-break"|</div></div>\s*$|$)', re.S)
RANK_CELL = re.compile(r'<div class="bz-rank[^"]*">'
                       r'<span class="k">(?P<kind>[^<]*)</span>'
                       r'<span class="n">(?P<num>[^<]*)</span>', re.S)


def parse_site(index: Path) -> dict[tuple[str, int, str], dict]:
    """index.html → {(지위, 매수, 동/서): {이름, 헤야}}"""
    html = index.read_text(encoding="utf-8")
    out: dict[tuple[str, int, str], dict] = {}
    for row in ROW.finditer(html):
        chunk = row.group(0)
        rk = RANK_CELL.search(chunk)
        if not rk:
            continue
        kind = (rk.group("kind") or "").strip()
        # 매수는 일본어 칸에 '前頭 3' / '十両 1' / '大関 2' 꼴로 들어 있다.
        m = re.search(r"(\d+)", rk.group("num") or "")
        num = int(m.group(1)) if m else 1
        for cell in CELL.finditer(chunk):
            side = "E" if cell.group("side") == "東" else "W"
            name = (cell.group("name") or "").strip()
            if not name:
                continue
            out[(kind, num, side)] = {
                "name": name,
                "heya": (cell.group("heya") or "").strip(),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="반즈케 내용이 사실과 맞는지 검증")
    ap.add_argument("--dir", default="docs")
    ap.add_argument("--basho", default=None,
                    help="검사할 바쇼 페이지 (기본: 픽스처의 바쇼)")
    args = ap.parse_args()

    truth = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bid = args.basho or truth["basho_id"]
    root = Path(args.dir)
    page = root / "banzuke" / f"{bid}.html"
    if not page.exists():
        page = root / "index.html"
    if not page.exists():
        print(f"페이지가 없습니다: {page}", file=sys.stderr)
        return 2

    print(f"반즈케 사실 검증 — {page} (기준: {truth['source']})")
    site = parse_site(page)
    if not site:
        print("  FAIL 반즈케 표를 읽지 못했습니다 — 구조가 바뀌었는지 확인하세요")
        return 1

    # --- 1) 산야쿠 인원 -------------------------------------------------
    for kind in ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi"):
        want = sum(1 for e in truth["entries"] if e["kind"] == kind)
        got = sum(1 for (k, _, _) in site if k == RANK_KO[kind])
        check(f"{RANK_KO[kind]} 인원", got == want, f"실제 {want}명 · 화면 {got}명")

    # --- 2) 자리마다 누가 앉았는가 --------------------------------------
    wrong_name: list[str] = []
    wrong_heya: list[str] = []
    missing: list[str] = []
    for e in truth["entries"]:
        key = (RANK_KO[e["kind"]], e["num"], e["side"])
        cell = site.get(key)
        label = f"{RANK_KO[e['kind']]} {e['num']} {'동' if e['side']=='E' else '서'}"
        if not cell:
            missing.append(label)
            continue

        # 이름 — 음역 결과 또는 한자 중 하나와는 반드시 맞아야 한다
        want_ko = to_hangul(e["name_en"])
        if cell["name"] not in (want_ko, e["name_ja"]):
            wrong_name.append(f"{label}: 화면 '{cell['name']}' ≠ 실제 '{want_ko}'")

        # 헤야 — '한국어 (한자)' 중 한자 쪽으로 대조한다 (한자가 사실의 기준)
        want_ja = japanese_for(e["heya_en"])
        if want_ja and want_ja not in cell["heya"]:
            wrong_heya.append(
                f"{label} {cell['name']}: 화면 '{cell['heya']}' ≠ 실제 '{want_ja}'")

    check("모든 자리가 화면에 있음", not missing,
          f"빠진 자리 {len(missing)}개: {', '.join(missing[:4])}")
    check("자리마다 사람이 맞음", not wrong_name,
          f"{len(wrong_name)}건 — " + " / ".join(wrong_name[:3]))
    check("선수마다 헤야가 맞음", not wrong_heya,
          f"{len(wrong_heya)}건 — " + " / ".join(wrong_heya[:3]))

    # --- 3) 가장 눈에 띄는 자리는 따로 못박아 둔다 ----------------------
    #  요코즈나가 틀리면 사이트 전체가 틀린 것으로 보인다.
    for e in truth["entries"]:
        if e["kind"] != "Yokozuna":
            continue
        side_ko = "동" if e["side"] == "E" else "서"
        cell = site.get(("요코즈나", e["num"], e["side"]), {})
        want = to_hangul(e["name_en"])
        check(f"요코즈나 {side_ko} = {want}", cell.get("name") == want,
              f"화면 '{cell.get('name', '없음')}'")

    # --- 4) 로마자가 남지 않았는가 --------------------------------------
    latin = [v["name"] for v in site.values()
             if re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", v["name"] or "")]
    check("이름이 전부 한국어/일본어", not latin,
          f"{len(latin)}건: {', '.join(sorted(set(latin))[:5])}")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print(f"반즈케 {len(truth['entries'])}자리 — 실제 반즈케와 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
