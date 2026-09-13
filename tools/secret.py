"""GitHub 시크릿에 넣을 값을 **클립보드에 담아** 준다.

    python tools/secret.py

왜 필요한가
-----------
메모장에서 `.env` 한 줄을 손으로 긁어 복사하다가
`...?sslmode=require?sslmode=require` 처럼 끝부분이 겹쳐 들어갔다.
psycopg 는 그걸 "extra key/value separator" 라는 알아볼 수 없는 말로 거절한다.

사람이 드래그하지 않게 만드는 것이 확실한 해결이다. 여기서 값을 꺼내
**검사한 뒤** 클립보드에 넣어 주면, 붙여넣기(Ctrl+V) 한 번으로 끝난다.

비밀번호는 화면에 찍지 않는다 — 캡처해서 보내는 일이 있기 때문이다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.preflight import check_dsn, masked  # noqa: E402


def read_dsn() -> tuple[str | None, str]:
    """(값, 사람에게 보일 설명)."""
    env = ROOT / ".env"
    if not env.exists():
        return None, f"{env} 가 없습니다. 먼저 1_설치하기.bat 을 실행해 주세요."
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        if key.strip().upper() == "DATABASE_URL":
            val = val.strip().strip('"').strip("'")
            if not val:
                return None, ".env 의 DATABASE_URL 이 비어 있습니다."
            return val, ""
    return None, ".env 안에서 DATABASE_URL 줄을 찾지 못했습니다."


def to_clipboard(text: str) -> bool:
    """Windows/macOS/Linux 에서 클립보드에 넣는다. 실패하면 False."""
    candidates: list[list[str]] = []
    if os.name == "nt":
        candidates.append(["clip"])
    else:
        candidates.append(["pbcopy"])
        candidates.append(["xclip", "-selection", "clipboard"])
        candidates.append(["wl-copy"])
    for cmd in candidates:
        try:
            p = subprocess.run(cmd, input=text, text=True,
                               encoding="utf-8", errors="replace")
            if p.returncode == 0:
                return True
        except OSError:
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    dsn, why = read_dsn()
    if not dsn:
        print(f"  [!!] {why}", file=sys.stderr)
        return 1

    # 값 자체가 이미 깨져 있으면 클립보드에 넣기 전에 알려 준다
    problem = check_dsn(dsn)
    if problem:
        # ::error title=제목::본문  → 사람이 읽을 수 있게 푼다
        head, _, body = problem.partition("::")[2].partition("::")
        title = head.removeprefix("error title=")
        print(f"  [!!] .env 의 값에 문제가 있습니다 — {title}")
        print(f"       {body}")
        return 1

    ok = to_clipboard(dsn)
    print("  값의 모양:", masked(dsn))
    print()
    if ok:
        print("  [OK] 클립보드에 담았습니다. 붙여넣기(Ctrl+V) 만 하시면 됩니다.")
        return 0

    # 값은 멀쩡한데 클립보드만 안 되는 경우 — 실패(1)와 구분한다.
    # 부르는 쪽이 "Ctrl+V 하세요" 대신 손으로 복사하는 안내를 내보내야 하기 때문.
    print("  [!] 클립보드에 담지 못했습니다 (값 자체는 정상입니다).")
    print("      .env 파일을 메모장으로 열어 DATABASE_URL= 뒤쪽을 복사해 주세요.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
