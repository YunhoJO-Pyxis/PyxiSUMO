"""생성된 사이트를 점검한다.

정적 사이트는 조용히 망가진다 — 링크가 깨져도, 한국어 페이지에 영어가
섞여도, 따옴표가 안 막혀도 에러가 나지 않는다. 그래서 기계로 본다.

    $ python tests/check_site.py --dir docs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

# 한국어 페이지에 그대로 나오면 안 되는 영어 지위명
ENGLISH_RANKS = re.compile(
    r"\b(Yokozuna|Ozeki|Sekiwake|Komusubi|Maegashira|Juryo|Makuuchi|Makushita)\s+\d",
)

# 화면에 보이는 이름 칸 — 여기에 로마자만 들어 있으면 음역이 빠진 것이다
NAME_SLOTS = (
    re.compile(r'<div class="bz-name"><a[^>]*>([^<]+)</a>'),
    re.compile(r'<div class="bz-heya">([^<]+)</div>'),
    re.compile(r'<div class="card"><div class="t">([^<]+)</div>'),
)
ROMAJI_ONLY = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class Checker(HTMLParser):
    """태그 균형과 링크를 본다. 완전한 검증기는 아니지만 흔한 실수는 잡는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.links: list[str] = []
        self.problems: list[str] = []
        self.titles = 0
        self.h1 = 0
        self.has_lang = False
        self.has_viewport = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "html" and d.get("lang"):
            self.has_lang = True
        if tag == "meta" and d.get("name") == "viewport":
            self.has_viewport = True
        if tag == "title":
            self.titles += 1
        if tag == "h1":
            self.h1 += 1
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag == "link" and d.get("href"):
            self.links.append(d["href"])
        if tag == "script" and d.get("src"):
            self.links.append(d["src"])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag not in self.stack:
            self.problems.append(f"닫는 태그 </{tag}> 에 맞는 여는 태그가 없음")
            return
        while self.stack and self.stack[-1] != tag:
            bad = self.stack.pop()
            self.problems.append(f"<{bad}> 가 닫히지 않음")
        if self.stack:
            self.stack.pop()


def check_file(path: Path, root: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root)

    c = Checker()
    try:
        c.feed(text)
    except Exception as ex:                            # noqa: BLE001
        problems.append(f"{rel}: 파싱 실패 {ex}")
        return problems

    problems += [f"{rel}: {p}" for p in c.problems]
    if c.stack:
        problems.append(f"{rel}: 닫히지 않은 태그 {c.stack}")
    if c.titles != 1:
        problems.append(f"{rel}: <title> 이 {c.titles}개")
    if c.h1 != 1:
        problems.append(f"{rel}: <h1> 이 {c.h1}개")
    if not c.has_lang:
        problems.append(f"{rel}: <html lang> 없음")
    if not c.has_viewport:
        problems.append(f"{rel}: viewport meta 없음 — 모바일에서 깨진다")

    # 내부 링크가 실제로 존재하는가
    for href in c.links:
        u = urlparse(href)
        if u.scheme or href.startswith("//") or href.startswith("#"):
            continue
        target = (path.parent / unquote(u.path)).resolve()
        if not target.exists():
            problems.append(f"{rel}: 깨진 링크 → {href}")

    # 한국어 페이지에 영어 지위가 새어나오지 않았는가
    body = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    for m in ENGLISH_RANKS.finditer(body):
        problems.append(f"{rel}: 영어 지위 표기가 보임 — '{m.group(0)}'")
        break

    # 이름 칸에 로마자가 그대로 남아 있지 않은가
    #
    # 한국어 사이트인데 'Hoshoryu' / 'Nishonoseki' 가 그대로 보이던 문제를
    # 다시 놓치지 않기 위한 검사다. 표기 채우기(setup names)가 빠지면 여기서 걸린다.
    romaji: list[str] = []
    for pat in NAME_SLOTS:
        for m in pat.finditer(body):
            txt = m.group(1).strip()
            if txt and ROMAJI_ONLY.match(txt):
                romaji.append(txt)
    if romaji:
        uniq = sorted(set(romaji))
        problems.append(
            f"{rel}: 이름이 로마자로 남아 있음 {len(uniq)}건 — "
            f"{', '.join(uniq[:5])}"
            + (" …" if len(uniq) > 5 else "")
            + "  (python -m pyxisumo.setup names 로 채웁니다)")

    # 한국어를 글자 단위로 쪼개는 CSS 가 섞이지 않았는가
    #  break-all / anywhere 를 주면 좁은 칸에서 '성 적 기 반' 처럼 늘어선다.
    if "break-all" in text or "overflow-wrap: anywhere" in text:
        problems.append(f"{rel}: 글자 단위 줄바꿈(break-all)이 들어 있음 — "
                        "좁은 칸에서 한국어가 세로로 쪼개집니다")

    # 이스케이프 사고 (< > 가 그대로 들어간 텍스트)
    if "<script>alert" in text.lower():
        problems.append(f"{rel}: 이스케이프되지 않은 스크립트")

    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="생성된 사이트 점검")
    ap.add_argument("--dir", default="docs")
    # 공개 워크플로에서 쓰는 두 가지.
    #  --github   : 걸린 항목을 GitHub Annotations 상자에 그대로 적는다.
    #               (실행 로그는 로그인해야 보이므로, 안 적으면 원인을 알 수 없다)
    #  --warn-only: 걸려도 실패로 만들지 않는다. 사람이 보는 사이트를 통째로
    #               못 올리게 하는 것보다, 올리고 문제를 알려주는 편이 낫다.
    #               품질을 지키는 쪽은 tests 워크플로(데모 데이터)가 맡는다.
    ap.add_argument("--github", action="store_true")
    ap.add_argument("--warn-only", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"폴더가 없습니다: {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("*.html"))
    if not files:
        print("HTML 파일이 없습니다.", file=sys.stderr)
        return 1

    problems: list[str] = []
    for p in files:
        problems += check_file(p, root)

    # 필수 파일
    for need in ("index.html", "yosou.html", "assets/style.css",
                 "assets/search.js", "rikishi/index.html",
                 "rikishi/search-index.json", "heya/index.html",
                 "banzuke/index.html", ".nojekyll"):
        if not (root / need).exists():
            problems.append(f"필수 파일 없음: {need}")

    # 검색 인덱스가 실제로 쓸 수 있는 모양인가
    idx_path = root / "rikishi" / "search-index.json"
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            if not isinstance(idx, list) or not idx:
                problems.append("검색 인덱스가 비어 있음")
            else:
                need_keys = {"i", "n", "j", "e", "k", "h", "r", "x"}
                miss = need_keys - set(idx[0])
                if miss:
                    problems.append(f"검색 인덱스에 없는 항목: {sorted(miss)}")
                broken = [r for r in idx
                          if not (root / "rikishi" / f"{r['i']}.html").exists()]
                if broken:
                    problems.append(
                        f"검색 인덱스가 가리키는 페이지 {len(broken)}개가 없음")

                # 은퇴 표시 — 검색 결과와 프로필이 같은 사람을 가리켜야 한다.
                # 한쪽만 붙으면 검색에서는 현역처럼 보인다.
                flagged = {r["i"] for r in idx if r.get("x")}
                tagged = {
                    r["i"] for r in idx
                    if 'class="tag-retired"' in
                    (root / "rikishi" / f"{r['i']}.html").read_text(encoding="utf-8")
                }
                if flagged != tagged:
                    problems.append(
                        f"은퇴 표시 불일치 — 검색 {len(flagged)}명 · "
                        f"프로필 {len(tagged)}명 "
                        f"(검색만: {sorted(flagged - tagged)[:3]} / "
                        f"프로필만: {sorted(tagged - flagged)[:3]})")
        except json.JSONDecodeError as ex:
            problems.append(f"검색 인덱스 JSON 오류: {ex}")

    total_kb = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) / 1024

    if problems:
        print(f"FAIL — {len(problems)}건")
        for p in problems[:40]:
            print(f"  ✗ {p}")
        if len(problems) > 40:
            print(f"  … 외 {len(problems) - 40}건")

        if args.github:
            level = "warning" if args.warn_only else "error"
            # 한 줄로 눌러 적는다 — 줄바꿈이 있으면 상자에서 잘린다.
            for p in problems[:10]:
                one = " ".join(str(p).split())
                print(f"::{level} title=페이지 점검::{one}")
            if len(problems) > 10:
                print(f"::{level} title=페이지 점검::외 {len(problems) - 10}건 "
                      "더 있습니다.")

        if args.warn_only:
            print("(--warn-only: 문제를 알리기만 하고 계속 진행합니다)")
            return 0
        return 1

    print(f"OK — HTML {len(files)}개 · 전체 {total_kb:,.0f}KB · "
          f"링크·태그·표기 점검 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
