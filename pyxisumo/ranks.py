"""지위(番付) 파싱과 인코딩.

DB의 rank_value() 함수와 **반드시 같은 규칙**을 구현한다.
여기 상수를 바꾸면 db/001_schema.sql 의 rank_value() 도 같이 바꿀 것.
tests/test_ranks.py 가 두 구현의 일치를 검증한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# --- 디비전 -----------------------------------------------------------
DIVISIONS = (
    "Makuuchi",
    "Juryo",
    "Makushita",
    "Sandanme",
    "Jonidan",
    "Jonokuchi",
    "Banzukegai",
)

DIVISION_BASE = {
    "Makuuchi": 0,
    "Juryo": 10_000,
    "Makushita": 20_000,
    "Sandanme": 40_000,
    "Jonidan": 60_000,
    "Jonokuchi": 80_000,
    "Banzukegai": 99_000,
}

# 정원. 마쿠우치 42 / 쥬료 28 은 2004년 1월 장소 이후 고정(확정 규칙).
# 산단메 이하는 정원이 없다 → None.
DIVISION_CAPACITY = {
    "Makuuchi": 42,
    "Juryo": 28,
    "Makushita": 120,
    "Sandanme": None,
    "Jonidan": None,
    "Jonokuchi": None,
}

# --- 지위 종류 --------------------------------------------------------
RANK_KINDS = ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi", "Maegashira", "Numbered")

RANK_KIND_OFFSET = {
    "Yokozuna": 0,
    "Ozeki": 100,
    "Sekiwake": 200,
    "Komusubi": 300,
    "Maegashira": 400,
    "Numbered": 0,
}

SANYAKU = ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi")

# 세키와케·코무스비는 각각 최소 2명(동서 1명씩). 상한은 없다. [확정]
SANYAKU_MIN_SLOTS = {"Sekiwake": 2, "Komusubi": 2}

_ALIASES = {
    # 표기 흔들림 흡수
    "makuuchi": "Makuuchi",
    "makunouchi": "Makuuchi",
    "幕内": "Makuuchi",
    "juryo": "Juryo",
    "jūryō": "Juryo",
    "十両": "Juryo",
    "makushita": "Makushita",
    "幕下": "Makushita",
    "sandanme": "Sandanme",
    "三段目": "Sandanme",
    "jonidan": "Jonidan",
    "序二段": "Jonidan",
    "jonokuchi": "Jonokuchi",
    "序ノ口": "Jonokuchi",
    "banzukegai": "Banzukegai",
    "banzuke-gai": "Banzukegai",
    "番付外": "Banzukegai",
}

_KIND_ALIASES = {
    "yokozuna": "Yokozuna",
    "横綱": "Yokozuna",
    # 横綱大関(요코즈나가 오제키를 겸임)은 요코즈나로 취급한다
    "yokozuna-ozeki": "Yokozuna",
    "yokozunaozeki": "Yokozuna",
    "横綱大関": "Yokozuna",
    "ozeki": "Ozeki",
    "大関": "Ozeki",
    "sekiwake": "Sekiwake",
    "関脇": "Sekiwake",
    "komusubi": "Komusubi",
    "小結": "Komusubi",
    "maegashira": "Maegashira",
    "前頭": "Maegashira",
}

_SIDE_ALIASES = {
    "e": "E", "east": "E", "東": "E", "higashi": "E",
    "w": "W", "west": "W", "西": "W", "nishi": "W",
}


class RankParseError(ValueError):
    """지위 문자열을 해석하지 못했을 때. 조용히 넘기지 않는다."""


@dataclass(frozen=True, slots=True)
class Rank:
    division: str      # 'Makuuchi'
    kind: str          # 'Maegashira' | 'Numbered' | ...
    num: int | None    # 매수. 마에가시라 3매목 → 3
    side: str          # 'E' | 'W'

    @property
    def value(self) -> int:
        return rank_value(self.division, self.kind, self.num, self.side)

    def label(self, lang: str = "en") -> str:
        if lang == "ja":
            kind_ja = {
                "Yokozuna": "横綱", "Ozeki": "大関", "Sekiwake": "関脇",
                "Komusubi": "小結", "Maegashira": "前頭",
            }
            div_ja = {
                "Juryo": "十両", "Makushita": "幕下", "Sandanme": "三段目",
                "Jonidan": "序二段", "Jonokuchi": "序ノ口",
            }
            head = kind_ja.get(self.kind) or div_ja.get(self.division, self.division)
            side = "東" if self.side == "E" else "西"
            return f"{side}{head}{self.num or 1}枚目" if self.kind in ("Maegashira", "Numbered") \
                else f"{side}{head}" + (f"{self.num}" if (self.num or 1) > 1 else "")
        head = self.kind if self.kind != "Numbered" else self.division
        side = "East" if self.side == "E" else "West"
        return f"{head} {self.num or 1} {side}"

    def __lt__(self, other: "Rank") -> bool:   # 상위가 작다
        return self.value < other.value


def rank_value(division: str, kind: str, num: int | None, side: str) -> int:
    """전 서열을 단일 정수로. 낮을수록 상위. DB의 rank_value() 와 동일해야 한다."""
    if division not in DIVISION_BASE:
        raise RankParseError(f"unknown division: {division!r}")
    if kind not in RANK_KIND_OFFSET:
        raise RankParseError(f"unknown rank kind: {kind!r}")
    if side not in ("E", "W"):
        raise RankParseError(f"unknown side: {side!r}")
    if division == "Makuuchi" and kind == "Numbered":
        raise RankParseError("Makuuchi 에는 'Numbered' 를 쓰지 않는다 (Yokozuna 와 충돌)")
    if division != "Makuuchi" and kind != "Numbered":
        raise RankParseError(f"{division} 에는 'Numbered' 만 쓴다 (got {kind!r})")
    return (
        DIVISION_BASE[division]
        + RANK_KIND_OFFSET[kind]
        + (max(int(num or 1), 1) - 1) * 2
        + (0 if side == "E" else 1)
    )


def normalize_division(raw: str) -> str:
    key = str(raw).strip().lower().replace(" ", "")
    if raw in DIVISION_BASE:
        return raw
    if key in _ALIASES:
        return _ALIASES[key]
    cap = str(raw).strip().capitalize()
    if cap in DIVISION_BASE:
        return cap
    raise RankParseError(f"unknown division: {raw!r}")


def normalize_side(raw: str) -> str:
    key = str(raw).strip().lower()
    if key in _SIDE_ALIASES:
        return _SIDE_ALIASES[key]
    raise RankParseError(f"unknown side: {raw!r}")


_RANK_RE = re.compile(
    r"^\s*(?P<kind>[A-Za-z぀-ヿ一-鿿\-]+?)\s*"
    r"(?P<num>\d+)?\s*"
    r"(?P<side>East|West|E|W|東|西)?\s*$",
    re.IGNORECASE,
)


def parse_rank(raw: str, division_hint: str | None = None) -> Rank:
    """'Maegashira 5 West', 'Juryo 3 East', '東前頭五枚目' 류를 Rank 로.

    division_hint 는 반즈케 엔드포인트처럼 디비전을 이미 아는 경우에 넘긴다.
    해석 실패는 예외로 올린다 — 조용히 기본값을 넣으면 반즈케가 통째로 망가진다.
    """
    if raw is None:
        raise RankParseError("rank string is None")
    s = str(raw).strip()
    if not s:
        raise RankParseError("rank string is empty")

    # 선행 동/서 표기 ('東前頭1', 'East Maegashira 1')
    lead_side = None
    for pref, val in (("東", "E"), ("西", "W")):
        if s.startswith(pref):
            lead_side, s = val, s[len(pref):].strip()
    m_lead = re.match(r"^(east|west)\b\s*", s, re.IGNORECASE)
    if m_lead:
        lead_side = _SIDE_ALIASES[m_lead.group(1).lower()]
        s = s[m_lead.end():]

    s = s.replace("枚目", "").strip()

    # 지위명 없이 매수만 온 경우 ('3 East') — division_hint 가 있어야 해석 가능
    m_bare = re.match(r"^(?P<num>\d+)\s*(?P<side>East|West|E|W|東|西)?$", s, re.IGNORECASE)
    if m_bare:
        if not division_hint:
            raise RankParseError(f"디비전을 알 수 없어 해석 불가: {raw!r}")
        side_b = normalize_side(m_bare.group("side")) if m_bare.group("side") else lead_side
        if side_b is None:
            raise RankParseError(f"rank has no side (East/West): {raw!r}")
        div_b = normalize_division(division_hint)
        kind_b = "Maegashira" if div_b == "Makuuchi" else "Numbered"
        return Rank(div_b, kind_b, int(m_bare.group("num")), side_b)

    m = _RANK_RE.match(s)
    if not m:
        raise RankParseError(f"cannot parse rank: {raw!r}")

    kind_raw = (m.group("kind") or "").strip()
    num = int(m.group("num")) if m.group("num") else None
    side_raw = m.group("side")

    side = normalize_side(side_raw) if side_raw else lead_side
    if side is None:
        raise RankParseError(f"rank has no side (East/West): {raw!r}")

    key = kind_raw.lower().replace(" ", "").replace("-", "")
    if key in _KIND_ALIASES or kind_raw in _KIND_ALIASES:
        kind = _KIND_ALIASES.get(key) or _KIND_ALIASES[kind_raw]
        division = "Makuuchi"
    else:
        # 지위명이 아니라 디비전명이 온 경우 ('Juryo 3 East')
        division = normalize_division(kind_raw)
        kind = "Numbered"

    if division_hint:
        hint = normalize_division(division_hint)
        if hint != division:
            # 힌트를 신뢰하되, 마쿠우치 지위명이 왔다면 그쪽이 더 구체적이다
            if division != "Makuuchi":
                division, kind = hint, "Numbered"

    if division == "Makuuchi" and kind == "Numbered":
        raise RankParseError(f"Makuuchi 지위명을 찾지 못했다: {raw!r}")

    return Rank(division=division, kind=kind, num=num, side=side)


def slots_for(division: str, count: int) -> Iterable[tuple[int, str]]:
    """디비전 안에서 count 명을 채울 (매수, 동/서) 슬롯을 상위부터 생성."""
    i = 0
    num = 1
    while i < count:
        for side in ("E", "W"):
            if i >= count:
                break
            yield num, side
            i += 1
        num += 1
