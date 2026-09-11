"""실제 DB에 붙여 표기 채우기를 검증한다.

    DATABASE_URL=... python tests/check_names.py

확인하는 것
  1) 비어 있던 한국어 표기가 채워진다
  2) **사람이 넣은 값은 덮어쓰지 않는다** — 이게 가장 중요하다.
     스프레드시트로 고친 표기가 기계 음역에 지워지면 신뢰를 잃는다
  3) 한자를 모르는 헤야에는 한자를 지어내지 않는다
  4) 두 번 돌려도 결과가 같다 (멱등)
  5) 채운 뒤 사이트 조회문이 영문 이름을 내놓지 않는다
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.fill_names import fill              # noqa: E402
from pyxisumo.sqlrunner import Runner, SqlError   # noqa: E402

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


SETUP = """
BEGIN;

INSERT INTO heya (slug, name_en, name_ja, name_ko) VALUES
  ('t_nishonoseki', 'Nishonoseki', NULL, NULL),
  ('t_tatsunami',   'Tatsunami',   NULL, '내가 고친 타츠나미'),
  ('t_unknownbeya', 'Zzzunknown',  NULL, NULL)
ON CONFLICT (slug) DO UPDATE
  SET name_en = EXCLUDED.name_en,
      name_ja = EXCLUDED.name_ja,
      name_ko = EXCLUDED.name_ko;

INSERT INTO rikishi (id) VALUES (990001), (990002)
ON CONFLICT (id) DO NOTHING;

INSERT INTO shikona (rikishi_id, from_basho, name_en, name_ja, name_ko) VALUES
  (990001, '202601', 'Hoshoryu', '豊昇龍', NULL),
  (990002, '202601', 'Kotozakura', '琴櫻', '내가 고친 코토자쿠라')
ON CONFLICT (rikishi_id, from_basho) DO UPDATE
  SET name_en = EXCLUDED.name_en,
      name_ja = EXCLUDED.name_ja,
      name_ko = EXCLUDED.name_ko;

COMMIT;
"""

CLEANUP = """
DELETE FROM shikona WHERE rikishi_id IN (990001, 990002);
DELETE FROM rikishi WHERE id IN (990001, 990002);
DELETE FROM heya WHERE slug LIKE 't\\_%';
"""


def one(rn: Runner, sql: str):
    rows = rn.query(sql)
    return rows[0] if rows else None


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)

    print("표기 채우기 검증")
    try:
        rn.execute(CLEANUP)
    except SqlError:
        pass
    rn.execute(SETUP)

    try:
        st = fill(rn, verbose=False)
        print(f"  (1회차: {st})")

        ko = one(rn, "SELECT name_ko FROM heya WHERE slug='t_nishonoseki'")
        ja = one(rn, "SELECT name_ja FROM heya WHERE slug='t_nishonoseki'")
        check("빈 헤야 한국어가 채워짐", ko and ko[0] == "니쇼노세키", str(ko))
        check("빈 헤야 한자가 채워짐", ja and ja[0] == "二所ノ関", str(ja))

        kept = one(rn, "SELECT name_ko FROM heya WHERE slug='t_tatsunami'")
        check("사람이 넣은 헤야 표기는 그대로",
              kept and kept[0] == "내가 고친 타츠나미", str(kept))

        unk = one(rn, "SELECT name_ja, name_ko FROM heya WHERE slug='t_unknownbeya'")
        check("모르는 헤야 한자는 비워 둠 (추측 금지)",
              unk and unk[0] is None, str(unk))
        check("모르는 헤야도 한국어는 음역됨", unk and unk[1], str(unk))

        s1 = one(rn, "SELECT name_ko FROM shikona WHERE rikishi_id=990001")
        check("빈 시코나 한국어가 채워짐", s1 and s1[0] == "호쇼류", str(s1))

        s2 = one(rn, "SELECT name_ko FROM shikona WHERE rikishi_id=990002")
        check("사람이 넣은 시코나 표기는 그대로",
              s2 and s2[0] == "내가 고친 코토자쿠라", str(s2))

        # 멱등성 — 두 번째 실행은 아무것도 바꾸지 않아야 한다
        st2 = fill(rn, verbose=False)
        check("두 번째 실행은 변경 없음",
              st2["shikona_ko"] == 0 and st2["heya_ko"] == 0 and st2["heya_ja"] == 0,
              str(st2))

        # 전체 DB에 영문만 남은 표시가 없는지
        left = one(rn, """
            SELECT count(*) FROM shikona
            WHERE name_ko IS NULL AND name_ja IS NULL AND name_en IS NOT NULL
        """)
        check("한국어·일본어 둘 다 없는 시코나 없음", left and int(left[0]) == 0,
              f"{left[0] if left else '?'}건 남음")

        left_h = one(rn, """
            SELECT count(*) FROM heya
            WHERE name_ko IS NULL AND name_ja IS NULL AND name_en IS NOT NULL
        """)
        check("한국어·일본어 둘 다 없는 헤야 없음", left_h and int(left_h[0]) == 0,
              f"{left_h[0] if left_h else '?'}건 남음")
    finally:
        rn.execute(CLEANUP)

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("표기 채우기 — 모두 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
