"""헤야 페이지가 DB와 같은 말을 하는지 본다.

    DATABASE_URL=... python tests/check_heya.py --dir /tmp/site

왜 필요한가
-----------
'세키토리 3명' 은 틀려도 화면이 멀쩡하다. 실제로 그런 일이 있었다 —
쥬료에 있다가 마쿠시타로 떨어진 선수(후타고야마 三田: 2025년 11월 쥬료 3매,
2026년 9월 마쿠시타 15매)가 계속 세키토리로 잡혔다. 조회문이
"마쿠우치·쥬료 기록이 **한 번이라도** 있는가" 로 세고 있었기 때문이다.
한 번 관취면 영원히 관취가 되는 셈이었다.

그래서 여기서 세 가지를 본다.
  1) 화면의 세키토리 수 = 최신 반즈케에서 센 수
  2) 명단에 오른 사람은 모두 **지금** 마쿠우치·쥬료에 있다
  3) 일문 단추의 숫자 = 그 일문 카드 수, 그리고 단추와 카드의 일문이 서로 맞다

그리고 --fail-demo 로, 옛 조회문을 되살려 이 검사가 실제로 잡아내는지 본다.
검사기가 잡지 못하는 검사는 없는 것과 같다.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.ichimon import HEYA_ICHIMON, ICHIMON_NAMES, ichimon_for  # noqa: E402
from pyxisumo.site import queries as Q                                 # noqa: E402
from pyxisumo.sqlrunner import Runner                                  # noqa: E402

FAIL: list[str] = []

CARD = re.compile(r'<div class="card" data-ichimon="([^"]*)">(.*?)(?=<div class="card" |$)', re.S)
TITLE = re.compile(r'<div class="t">([^<]*)</div>')
COUNT = re.compile(r'<div class="m">세키토리 (\d+)명([^<]*)</div>')
BUTTON = re.compile(r'<button type="button" class="jump[^"]*" data-filter="([^"]+)">([^<]*)<span>(\d+)</span>')

# 버그를 되살린 옛 조회문 — --fail-demo 에서만 쓴다
OLD_COUNT = """
SELECT h.slug, count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM banzuke_entry be
         WHERE be.rikishi_id = r.id AND be.division IN ('Makuuchi','Juryo')))
FROM heya h JOIN rikishi r ON r.heya_id = h.id
WHERE r.retired_basho IS NULL
GROUP BY h.slug
"""

TRUE_COUNT = """
SELECT h.slug, count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM banzuke_entry be
         WHERE be.rikishi_id = r.id
           AND be.basho_id = (SELECT max(basho_id) FROM banzuke_entry)
           AND be.division IN ('Makuuchi','Juryo')))
FROM heya h JOIN rikishi r ON r.heya_id = h.id
WHERE r.retired_basho IS NULL
GROUP BY h.slug
"""

# 명단에 오른 사람 중, 최신 반즈케에서 세키토리가 아닌 사람
NOT_SEKITORI_NOW = """
SELECT COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       COALESCE(be.division::text, '(반즈케 없음)') AS div
FROM rikishi r
LEFT JOIN banzuke_entry be
       ON be.rikishi_id = r.id
      AND be.basho_id = (SELECT max(basho_id) FROM banzuke_entry)
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = r.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
WHERE r.id IN ({ids})
  AND (be.division IS NULL OR be.division NOT IN ('Makuuchi','Juryo'))
"""


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


def main() -> int:
    ap = argparse.ArgumentParser(description="헤야 페이지 검증")
    ap.add_argument("--dir", default="docs")
    ap.add_argument("--fail-demo", action="store_true",
                    help="옛 조회문(버그)으로 만든 숫자를 넣어 이 검사가 잡는지 본다")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)

    path = Path(args.dir) / "heya" / "index.html"
    if not path.exists():
        print(f"{path} 가 없습니다. 먼저 사이트를 만들어 주세요.", file=sys.stderr)
        return 2
    html = path.read_text(encoding="utf-8")

    print("헤야 페이지 검증")

    # ── 카드 읽기 ──────────────────────────────────────────────
    cards = []
    for mon, block in CARD.findall(html):
        t = TITLE.search(block)
        c = COUNT.search(block)
        cards.append({"ichimon": mon,
                      "title": (t.group(1) if t else "").strip(),
                      "n": int(c.group(1)) if c else None,
                      "names": (c.group(2) if c else "")})
    check("헤야 카드를 읽어냄", bool(cards), f"{len(cards)}장")

    # ── 1. 세키토리 수 ────────────────────────────────────────
    truth = {r[0]: int(r[1]) for r in rn.query(TRUE_COUNT)}
    if args.fail_demo:
        truth = {r[0]: int(r[1]) for r in rn.query(OLD_COUNT)}
        print("  (일부러 옛 조회문의 숫자를 정답 자리에 넣었습니다)")

    # 카드는 slug 를 싣지 않으므로, 헤야 목록 조회문으로 이름 → slug 를 맞춘다
    listed = rn.query(Q.HEYA_LIST)
    by_title = {}
    for r in listed:
        slug, name, name_ja = r[0], r[1], r[2]
        title = f"{name} ({name_ja})" if name_ja and name_ja != name else str(name)
        by_title[title] = (slug, int(r[9]))

    bad_n, unmatched = [], []
    for c in cards:
        hit = by_title.get(c["title"])
        if not hit:
            unmatched.append(c["title"])
            continue
        slug, _ = hit
        want = truth.get(slug, 0)
        if c["n"] != want:
            bad_n.append((c["title"], c["n"], want))

    check("카드 이름이 DB의 헤야와 맞음", not unmatched, str(unmatched[:3]))
    check("세키토리 수가 최신 반즈케 기준과 일치", not bad_n,
          " / ".join(f"{t}: 화면 {g} ≠ DB {w}" for t, g, w in bad_n[:3]))

    # ── 2. 명단에 오른 사람은 지금 세키토리인가 ──────────────
    # id 는 DB 에서 온 정수다 — 문자열로 끼워 넣어도 주입 위험이 없다.
    # (psql 경유 실행기는 배열 파라미터를 다루지 못한다)
    member_ids = [int(r[1]) for r in rn.query(Q.HEYA_MEMBERS_ALL)]
    stale = (rn.query(NOT_SEKITORI_NOW.format(ids=",".join(map(str, member_ids))))
             if member_ids else [])
    check("명단에 지금 세키토리가 아닌 사람이 없음", not stale,
          " / ".join(f"{r[0]}({r[1]})" for r in stale[:4]))

    # ── 3. 일문 ───────────────────────────────────────────────
    buttons = {m[0]: (m[1].strip(), int(m[2])) for m in BUTTON.findall(html)}
    per_card: dict[str, int] = {}
    for c in cards:
        per_card[c["ichimon"]] = per_card.get(c["ichimon"], 0) + 1

    check("'전체' 단추 숫자 = 카드 수",
          buttons.get("all", ("", -1))[1] == len(cards),
          f"단추 {buttons.get('all', ('', '?'))[1]} · 카드 {len(cards)}")

    bad_mon = [(k, v[1], per_card.get(k, 0))
               for k, v in buttons.items() if k != "all" and v[1] != per_card.get(k, 0)]
    check("일문 단추 숫자 = 그 일문 카드 수", not bad_mon,
          " / ".join(f"{k}: 단추 {a} ≠ 카드 {b}" for k, a, b in bad_mon[:3]))

    unknown_codes = [k for k in per_card if k != "unknown" and k not in ICHIMON_NAMES]
    check("카드의 일문 코드가 모두 표에 있는 값", not unknown_codes, str(unknown_codes))

    # DB의 헤야가 일문 표에 있는가 — 없으면 '미상' 으로 정직하게 나와야 한다
    missing = [r[3] for r in listed if r[3] and not ichimon_for(r[3])]
    n_unknown_cards = per_card.get("unknown", 0)
    check("일문을 모르는 헤야 수 = '일문 미상' 카드 수",
          len(missing) == n_unknown_cards,
          f"표에 없는 헤야 {len(missing)}곳 {missing[:5]} · 미상 카드 {n_unknown_cards}장")
    if missing:
        print(f"       → pyxisumo/ichimon.py 에 추가하면 채워집니다: {', '.join(sorted(set(missing)))}")

    # 표 자체의 모양
    check("일문 표의 값이 모두 알려진 일문",
          all(v in ICHIMON_NAMES for v in HEYA_ICHIMON.values()))

    print()
    if args.fail_demo:
        if FAIL:
            print(f"의도한 대로 {len(FAIL)}건을 잡아냈습니다: {', '.join(FAIL)}")
            return 0
        print("검사기가 옛 버그를 통과시켰습니다 — 검사가 고장났습니다.")
        return 1

    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print(f"헤야 {len(cards)}곳 — 세키토리 수·명단·일문이 DB와 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
