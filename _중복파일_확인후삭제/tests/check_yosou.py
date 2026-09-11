"""예측 페이지가 **두 상태를 모두** 올바로 보여주는지 본다.

    DATABASE_URL=... python tests/check_yosou.py

두 상태
    발표됨  — 예측한 대회의 반즈케가 실제로 나왔다 → 실제 지위 + 차이 + 요약
    발표 전 — 아직 안 나왔다 → '발표 전' 안내, 실제 지위 칸 자체가 없어야 한다

'발표 전' 은 사이트가 대부분의 기간 동안 머무는 상태다. 그런데 개발 중에는
반즈케가 이미 있는 과거 대회로만 확인하게 되어 **정작 평소 화면을 아무도
안 보는** 일이 생긴다. 그래서 여기서 일부러 미래 대회를 예측한 상태를 만들어
확인하고, 확인이 끝나면 지운다.

또 하나 — 데모 자료의 적중률이 터무니없이 낮으면 엔진이 아니라 **자료가
앞뒤가 안 맞는다는 신호**다. (실제로 픽스처를 東→西 순서 그대로 순위로 쓰는
바람에 서 요코즈나가 22번째 선수가 되어 적중률이 17%까지 떨어진 적이 있다.)
그 사고를 다시 놓치지 않도록 하한선을 둔다.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.sqlrunner import Runner, SqlError   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 데모 자료는 '성적이 순위 변동을 설명하도록' 만든다. 그렇게 만든 자료에서
# 엔진이 이 정도도 못 맞히면 자료나 엔진 어느 쪽이 깨진 것이다.
MIN_WITHIN1 = 0.40

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


def build(dsn: str, out: Path) -> str:
    env = dict(os.environ, DATABASE_URL=dsn)
    r = subprocess.run([sys.executable, "-m", "pyxisumo.site.build", "--out", str(out)],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"사이트 생성 실패:\n{r.stdout}\n{r.stderr}")
    return (out / "yosou.html").read_text(encoding="utf-8")


def text_of(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)
    tmp = Path(tempfile.mkdtemp(prefix="yosou-"))

    # ---------- 1. 발표됨 ----------------------------------------------
    print("예측 페이지 검증 — (1) 실제 반즈케 발표됨")
    html = build(dsn, tmp / "published")
    body = text_of(html)

    check("'실제 지위' 칸이 있음", "<th>실제 지위</th>" in html)
    check("'차이' 칸이 있음", "<th>차이</th>" in html)
    check("발표 안내가 보임", "실제 반즈케가 발표되었습니다" in body)
    check("'발표 전' 안내는 없음", "발표 전입니다" not in body)

    moves = re.findall(r"[▲▼]\s*[\d.]+매", body)
    check("차이가 실제로 계산됨", len(moves) >= 10, f"{len(moves)}건")

    m = re.search(r"±1매 이내\s*(\d+)명\s*\(([\d.]+)%\)", body)
    check("요약 숫자가 보임", bool(m), body[:0] if m else "요약을 찾지 못함")
    if m:
        rate = float(m.group(2)) / 100
        check(f"적중률이 상식 범위 (≥{MIN_WITHIN1:.0%})", rate >= MIN_WITHIN1,
              f"±1매 {rate:.1%} — 데모 자료가 앞뒤가 안 맞을 수 있습니다")

    # 표의 '적중' 개수와 요약의 적중 인원이 같아야 한다 (따로 세면 어긋난다)
    n_hit_cells = len(re.findall(r'<span class="hit">적중</span>', html))
    m2 = re.search(r"적중\s*(\d+)명", body)
    check("표의 적중 수 = 요약의 적중 수",
          bool(m2) and int(m2.group(1)) == n_hit_cells,
          f"표 {n_hit_cells}개 · 요약 {m2.group(1) if m2 else '?'}명")

    # ---------- 1b. 표가 읽을 수 있는 모양인가 --------------------------
    #  열이 늘어나면 칸이 좁아지고, 한국어는 글자 단위로 쪼개져 한 글자씩
    #  세로로 늘어선다. 실제로 헤야와 근거 칸이 그렇게 망가진 적이 있다.
    head = re.search(r"<thead>.*?</thead>", html, re.S)
    n_cols = len(re.findall(r"<th[ >]", head.group(0))) if head else 0
    check("예측표 열이 8개 이하", 0 < n_cols <= 8,
          f"{n_cols}열 — 열이 더 늘면 칸이 찌그러집니다")

    check("헤야는 두 줄로 나뉘어 있음",
          '<td class="heya">' in html and 'class="hy-ko"' in html,
          "한 줄로 넣으면 좁은 칸에서 세로로 쪼개집니다")
    check("근거는 지위 밑 한 줄로", '<div class="basis">' in html)

    # ---------- 2. 발표 전 ----------------------------------------------
    print("예측 페이지 검증 — (2) 실제 반즈케 발표 전")
    #  아직 반즈케가 없는 미래 대회를 대상으로 한 예측을 잠깐 넣는다.
    future = "209901"
    try:
        rn.execute("""
            INSERT INTO prediction_run (id, target_basho_id, source_basho_id,
                                        model_version, params)
            SELECT 99, %s, source_basho_id, model_version, params
            FROM prediction_run ORDER BY id LIMIT 1
            ON CONFLICT (id) DO NOTHING
        """, (future,))
        rn.execute("""
            INSERT INTO prediction_entry (run_id, rikishi_id, division,
                                          rank_kind, rank_num, side, confidence, basis)
            SELECT 99, rikishi_id, division, rank_kind, rank_num, side, confidence, basis
            FROM prediction_entry WHERE run_id = (
                SELECT min(run_id) FROM prediction_entry)
            ON CONFLICT DO NOTHING
        """)
        html2 = build(dsn, tmp / "unpublished")
        body2 = text_of(html2)

        check("'발표 전' 안내가 보임", "발표 전입니다" in body2)
        check("'실제 지위' 칸이 없음", "<th>실제 지위</th>" not in html2)
        check("'차이' 칸이 없음", "<th>차이</th>" not in html2)
        check("차이 표시가 새어나오지 않음",
              not re.search(r"[▲▼]\s*[\d.]+매", body2))
        check("예측 표 자체는 그대로 나옴", body2.count("확신도") >= 1)
    finally:
        try:
            rn.execute("DELETE FROM prediction_entry WHERE run_id = 99")
            rn.execute("DELETE FROM prediction_run WHERE id = 99")
        except SqlError as ex:
            print(f"  (정리 실패: {ex})")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("예측 페이지 — 발표됨·발표 전 두 상태 모두 정상")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
