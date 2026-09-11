"""다른 프로그램의 출력을 읽을 때 **인코딩을 못박았는가**.

    python tests/check_encoding.py

왜 필요한가
-----------
`subprocess.run(..., text=True)` 는 인코딩을 지정하지 않으면 **그 컴퓨터의
로케일 인코딩**으로 읽는다. 개발한 리눅스에서는 UTF-8 이라 아무 일도 없지만,
Windows 한국어판에서는 cp949 다.

git 은 파일명을 UTF-8 로 내보낸다. 그래서 사용자의 PC에서 `1_설치하기.bat`
한 줄을 읽다가 이렇게 죽었다:

    UnicodeDecodeError: 'cp949' codec can't decode byte 0xec ...
    AttributeError: 'NoneType' object has no attribute 'splitlines'

(읽기 스레드가 죽으면서 stdout 이 None 이 된다 — 엉뚱한 곳에서 터진다.)

이 사고는 **개발 환경에서 절대 재현되지 않는다.** 로케일이 UTF-8 이기 때문이다.
그래서 실행해서 잡는 대신, 코드를 읽어서 규칙을 강제한다:

    출력을 잡아 문자열로 읽는 subprocess 호출은 encoding= 을 반드시 준다.

psql 로 시코나(한자)를 읽어 오는 sqlrunner 도 같은 이유로 해당된다.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ("pyxisumo", "tools")

FAIL: list[str] = []


def kw(call: ast.Call, name: str) -> ast.expr | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def captures_text(call: ast.Call) -> bool:
    """출력을 잡아서 **문자열로** 읽는 호출인가."""
    text_mode = is_true(kw(call, "text")) or is_true(kw(call, "universal_newlines"))
    if not text_mode:
        return False
    if is_true(kw(call, "capture_output")):
        return True
    return any(kw(call, s) is not None for s in ("stdout", "stderr"))


def func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}" if base else f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def scan(path: Path) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as ex:
        return [f"{path}: 파싱 실패 {ex}"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = func_name(node)
        if name not in ("subprocess.run", "subprocess.Popen",
                        "subprocess.check_output", "run", "Popen"):
            continue
        if not captures_text(node):
            continue
        if kw(node, "encoding") is None:
            rel = path.relative_to(ROOT)
            out.append(
                f"{rel}:{node.lineno} — 출력을 읽으면서 encoding= 을 주지 않았습니다. "
                'encoding="utf-8", errors="replace" 를 넣어 주세요.')
    return out


def main() -> int:
    print("외부 프로그램 출력 인코딩 검증")
    files = sorted(
        f for d in SCAN for f in (ROOT / d).rglob("*.py")
        if "__pycache__" not in f.parts)
    for f in files:
        FAIL.extend(scan(f))

    for msg in FAIL:
        print(f"  FAIL {msg}")
    if not FAIL:
        print(f"  OK   검사한 파일 {len(files)}개 — 전부 인코딩을 못박았습니다")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건")
        print("  (이 사고는 Windows 한국어판에서만 납니다 — 개발 환경에서는 "
              "재현되지 않으니 여기서 막아야 합니다)")
        return 1
    print("외부 프로그램 출력 — 어느 나라 Windows 에서도 같은 결과가 나옵니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
