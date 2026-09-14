"""'오늘의 대전' 이 DB와 실제로 같은 말을 하는지 본다.

    DATABASE_URL=... python tests/check_torikumi.py --dir /tmp/site

왜 필요한가
-----------
승패 표시와 역대 전적은 **틀려도 화면이 멀쩡해 보인다.** 승자를 반대로
붙여도, 전적을 뒤집어 적어도 표는 예쁘게 그려진다. 그래서 형식이 아니라
**사실**을 본다: 만들어진 HTML 을 다시 읽어, DB 에서 따로 센 값과 맞춘다.

맞추는 방법도 일부러 다르게 한다. 사이트는 least/greatest 로 쌍을 정규화한
한 번의 집계로 구하고, 여기서는 대전을 한 건씩 세어 올린다. 같은 실수를
양쪽이 함께 하지 않도록 하기 위한 것이다.

--fail-demo 를 주면 일부러 틀린 HTML 을 만들어 이 검사가 실제로 잡아내는지
보여 준다 (검사기 자신을 검사한다).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.sqlrunner import Runner, SqlError   # noqa: E402

FAIL: list[str] = []

ROW = re.compile(r'<div class="tk-row">(.*?)</div></div>\s*(?=<div class="tk-row"|$)',
                 re.S)
SIDE = re.compile(r'<div class="tk-side( w)?" data-side="([東西])">(.*?)(?=<div class="tk-(side|mid)")',
                  re.S)
HREF = re.compile(r'rikishi/(\d+)\.html')
WIN = re.compile(r'class="tk-win"')
H2H = re.compile(r'<span class="tk-h2h">역대 <b>(\d+)</b><i>:</i><b>(\d+)</b></span>')
FIRST = re.compile(r'<span class="tk-h2h first">첫 대전</span>')
PENDING = re.compile(r'class="tk-pending"')


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


def parse_rows(html: str) -> list[dict]:
    """생성된 index.html 에서 대전 줄을 뽑는다."""
    out: list[dict] = []
    chunks = html.split('<div class="tk-row">')[1:]
    for c in chunks:
        c = c.split('<div class="tk-row">')[0]
        # 東 / 西 두 칸으로 자른다
        parts = c.split('<div class="tk-side w"')
        if len(parts) != 2:
            continue
        east_html, west_html = parts[0], parts[1]
        mid = east_html.split('<div class="tk-mid">')
        east_html = mid[0]
        mid_html = mid[1] if len(mid) > 1 else ""

        e_id = HREF.search(east_html)
        w_id = HREF.search(west_html)
        if not (e_id and w_id):
            continue
        h = H2H.search(mid_html)
        out.append({
            "east": int(e_id.group(1)),
            "west": int(w_id.group(1)),
            "east_won": bool(WIN.search(east_html)),
            "west_won": bool(WIN.search(west_html)),
            "pending": bool(PENDING.search(mid_html)),
            "first": bool(FIRST.search(mid_html)),
            "h2h": (int(h.group(1)), int(h.group(2))) if h else None,
        })
    return out


def truth_from_db(rn: Runner, basho: str, day: int) -> dict:
    """대전을 한 건씩 세어 올린 '정답'. 사이트의 집계문과 방법이 다르다."""
    every = rn.query("""
        SELECT east_id, west_id, winner_id
        FROM torikumi
        WHERE east_id IS NOT NULL AND west_id IS NOT NULL
    """)
    tally: dict[tuple[int, int], int] = {}
    for ea, we, win in every:
        if win is None:
            continue
        ea, we, win = int(ea), int(we), int(win)
        lose = we if win == ea else ea
        tally[(win, lose)] = tally.get((win, lose), 0) + 1

    today = rn.query("""
        SELECT east_id, west_id, winner_id
        FROM torikumi
        WHERE basho_id = %s AND day = %s AND division IN ('Makuuchi','Juryo')
    """, (basho, day))
    rows = {}
    for ea, we, win in today:
        ea, we = int(ea), int(we)
        rows[(ea, we)] = {
            "winner": int(win) if win is not None else None,
            "east_wins": tally.get((ea, we), 0),
            "west_wins": tally.get((we, ea), 0),
        }
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="오늘의 대전 검증")
    ap.add_argument("--dir", default="docs")
    ap.add_argument("--fail-demo", action="store_true",
                    help="일부러 틀린 HTML 로 이 검사가 잡는지 보여 준다")
    ap.add_argument("--require", action="store_true",
                    help="대전 기록이 없으면 실패로 본다 (CI 용)")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)

    index = Path(args.dir) / "index.html"
    if not index.exists():
        print(f"{index} 가 없습니다. 먼저 사이트를 만들어 주세요.", file=sys.stderr)
        return 2
    html = index.read_text(encoding="utf-8")

    cur = rn.query("SELECT max(basho_id) FROM banzuke_entry")
    basho = cur[0][0] if cur else None
    day_row = rn.query("SELECT max(day) FROM torikumi WHERE basho_id = %s", (basho,))
    day = int(day_row[0][0]) if day_row and day_row[0][0] else 0

    print("오늘의 대전 검증")
    if not day:
        # 대전이 없으면 화면에도 없어야 한다 — 빈 상자가 남으면 그것도 오류다
        check("대전이 없으면 '오늘의 대전'도 없음", 'class="tk-row"' not in html)
        print()
        if args.require or args.fail_demo:
            # 검증할 것이 없는데 '통과' 라고 말하면 검사가 있으나 마나다
            print("대전 기록이 없어 검증할 수 없습니다 (--require).")
            return 1
        print("대전 기록이 없어 내용 검증은 건너뜁니다.")
        return 1 if FAIL else 0

    if args.fail_demo:
        # 승패 배지를 서로 바꾼다. 표는 여전히 멀쩡해 보인다.
        html = (html.replace('class="tk-win"', 'class="__X__"')
                    .replace('class="tk-lose"', 'class="tk-win"')
                    .replace('class="__X__"', 'class="tk-lose"'))
        # 역대 전적도 좌우를 바꾼다 (숫자가 같은 줄은 티가 안 나므로 남는다)
        html = H2H.sub(
            lambda m: f'<span class="tk-h2h">역대 <b>{m.group(2)}</b>'
                      f'<i>:</i><b>{m.group(1)}</b></span>', html)
        print("  (일부러 승패와 역대 전적을 뒤집었습니다)")

    shown = parse_rows(html)
    truth = truth_from_db(rn, basho, day)

    check("대전 줄을 읽어냄", bool(shown), f"{len(shown)}줄")
    check("경기 수가 DB와 같음", len(shown) == len(truth),
          f"화면 {len(shown)} · DB {len(truth)}")

    bad_pair, bad_win, bad_h2h, bad_pending = [], [], [], []
    for r in shown:
        key = (r["east"], r["west"])
        t = truth.get(key)
        if t is None:
            bad_pair.append(key)
            continue
        if t["winner"] is None:
            if not r["pending"] or r["east_won"] or r["west_won"]:
                bad_pending.append(key)
        else:
            want_e = t["winner"] == r["east"]
            if r["east_won"] != want_e or r["west_won"] == want_e:
                bad_win.append(key)
        want = (t["east_wins"], t["west_wins"])
        got = r["h2h"] if r["h2h"] else (0, 0)
        if r["first"]:
            got = (0, 0)
        if got != want:
            bad_h2h.append((key, got, want))

    check("화면의 대전 짝이 DB에 모두 있음", not bad_pair, str(bad_pair[:3]))
    check("승패 표시가 DB와 일치", not bad_win, str(bad_win[:3]))
    check("결과 없는 대전은 '예정'으로만 표시", not bad_pending, str(bad_pending[:3]))
    check("역대 상대 전적이 DB와 일치", not bad_h2h, str(bad_h2h[:3]))

    print()
    if args.fail_demo:
        if FAIL:
            print(f"의도한 대로 {len(FAIL)}건을 잡아냈습니다: {', '.join(FAIL)}")
            return 0
        print("검사기가 틀린 화면을 통과시켰습니다 — 검사가 고장났습니다.")
        return 1

    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print(f"오늘의 대전 {len(shown)}경기 — 승패·역대 전적이 DB와 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
