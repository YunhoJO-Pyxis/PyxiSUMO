"""Sumo-API (www.sumo-api.com) 클라이언트.

왜 '별칭 해석기' 구조인가
-------------------------
Sumo-API 는 무료·무인증으로 쓸 수 있지만 **응답 스키마를 문서화하지 않는다**.
api-guide 페이지는 엔드포인트 목록만 싣고, webhooks 페이지는 아예
"Execute tests to see the formats" 라고 안내한다.

그래서 필드명을 하드코딩하는 대신, 논리 필드마다 후보 키 목록을 두고
실제 응답에서 해석한다. 후보에 없으면 **조용히 None 을 넣지 않고 예외를 던지며
실제로 관찰된 키 목록을 함께 보여준다** — 최초 1회 실행에서 고쳐야 할 곳이
한 군데로 모인다.

  $ python -m pyxisumo.probe        # 실제 응답 키를 덤프
  $ python -m pyxisumo.ingest ...   # 덤프에 맞춰 FIELD_ALIASES 를 조정한 뒤 실행
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

log = logging.getLogger(__name__)

BASE_URL = "https://www.sumo-api.com/api"
USER_AGENT = "PyxiSumo/0.1 (+https://example.invalid; contact: you@example.com)"

DIVISION_PARAM = {
    "Makuuchi": "Makuuchi",
    "Juryo": "Juryo",
    "Makushita": "Makushita",
    "Sandanme": "Sandanme",
    "Jonidan": "Jonidan",
    "Jonokuchi": "Jonokuchi",
}


class SumoApiError(RuntimeError):
    pass


class FieldResolveError(KeyError):
    """논리 필드를 실제 응답에서 찾지 못했다. 관찰된 키를 함께 보고한다."""

    def __init__(self, logical: str, observed: list[str], tried: list[str]):
        self.logical, self.observed, self.tried = logical, observed, tried
        super().__init__(
            f"'{logical}' 을(를) 응답에서 찾지 못했습니다.\n"
            f"  시도한 키 : {tried}\n"
            f"  실제 키   : {sorted(observed)}\n"
            f"  → pyxisumo/sumoapi.py 의 FIELD_ALIASES['{logical}'] 에 실제 키를 추가하세요."
        )


# ---------------------------------------------------------------------
#  논리 필드 → 후보 키.  앞쪽이 우선.
#  probe.py 결과를 보고 여기만 고치면 전체가 맞는다.
# ---------------------------------------------------------------------
FIELD_ALIASES: dict[str, list[str]] = {
    # rikishi
    "rikishi_id":   ["id", "rikishiId", "rikishi_id"],
    "shikona_en":   ["shikonaEn", "shikona_en", "shikonaEng", "nameEn"],
    "shikona_ja":   ["shikonaJp", "shikonaJa", "shikona_jp", "shikona", "nameJp"],
    "heya":         ["heya", "stable", "heyaEn"],
    "birth_date":   ["birthDate", "birthdate", "dob"],
    "shusshin":     ["shusshin", "birthPlace", "origin"],
    "height":       ["height", "heightCm", "height_cm"],
    "weight":       ["weight", "weightKg", "weight_kg"],
    "debut":        ["debut", "debutBasho", "firstBasho"],
    "retired":      ["intai", "retired", "retiredBasho", "lastBasho"],
    # banzuke entry
    "rank":         ["rank", "rankName", "rankLabel"],
    "rank_value":   ["rankValue", "rank_value"],
    "wins":         ["wins", "win", "w"],
    "losses":       ["losses", "loss", "l"],
    "absences":     ["absences", "absence", "kyujo", "a"],
    "record":       ["record", "results"],
    # torikumi
    "day":          ["day", "matchDay"],
    "match_no":     ["matchNo", "match_no", "matchNumber", "bout"],
    # 타입 가드(정수여야 함)가 있어 'east' 같은 짧은 후보를 넣어도
    # 시코나 문자열을 잘못 집지 않는다.
    "east_id":      ["eastId", "east_id", "eastRikishiId", "eastRikishiID",
                     "eastRikishi", "east"],
    "west_id":      ["westId", "west_id", "westRikishiId", "westRikishiID",
                     "westRikishi", "west"],
    "winner_id":    ["winnerId", "winner_id"],
    "kimarite":     ["kimarite", "winningTechnique"],
    # basho
    "basho_id":     ["bashoId", "date", "id"],
    "start_date":   ["startDate", "start_date"],
    "end_date":     ["endDate", "end_date"],
}


def normalize(key: str) -> str:
    """대소문자·구분자를 지운 비교용 이름. rikishiID ≡ rikishiId ≡ rikishi_id"""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _choose(present: list[str], obj: dict[str, Any]) -> str:
    """후보가 여럿이면 더 구체적인(긴) 이름을 택한다.

    반즈케 행에 'id'(행 고유번호)와 'rikishiId'(리키시 번호)가 함께 있을 때
    'id' 를 집으면 조용히 엉뚱한 리키시가 들어간다 — 에러도 나지 않는다.
    """
    if len(present) == 1:
        return present[0]
    shortest = min(len(x) for x in present)
    specific = [k for k in present if len(k) > shortest]
    return (specific or present)[0]


def pick(obj: dict[str, Any], logical: str, *, required: bool = True) -> Any:
    """논리 필드를 실제 응답 dict 에서 꺼낸다.

    **학습된 전역 대응에 의존하지 않는다.** 엔드포인트마다 키가 다르기 때문이다.
    실제로 리키시 목록은 'id', 반즈케는 'rikishiID' 를 쓴다 — 전역 대응 하나로
    묶으면 한쪽이 조용히 비어버린다. 그래서 매번 이 응답의 키와 직접 맞춘다.

      1) 후보 이름과 정확히 일치
      2) 대소문자·구분자를 무시하고 일치  (rikishiID ≡ rikishiId)
    """
    tried = FIELD_ALIASES.get(logical, [logical])
    norm_wanted = {normalize(c) for c in tried}

    # 정확 일치와 정규화 일치를 한 번에 모은 뒤 가장 구체적인 것을 고른다.
    # 나눠서 보면 'id' 가 'rikishiID' 보다 먼저 잡혀 엉뚱한 값이 들어간다.
    matched = [k for k in obj if k in tried or normalize(k) in norm_wanted]
    if matched:
        return obj[_choose(matched, obj)]

    if required:
        raise FieldResolveError(logical, list(obj.keys()), tried)
    return None


# ---------------------------------------------------------------------
#  HTTP
# ---------------------------------------------------------------------
class SumoApi:
    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        timeout: float = 30.0,
        min_interval: float = 0.6,   # 무료 API에 대한 예의. 초당 2회 미만.
        max_retries: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_call = 0.0

    # -- low level ----------------------------------------------------
    def get(self, path: str, **params: Any) -> Any:
        qs = {k: v for k, v in params.items() if v is not None}
        url = f"{self.base_url}/{path.lstrip('/')}"
        if qs:
            url += "?" + urllib.parse.urlencode(qs)

        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self._last_call = time.monotonic()
                    raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as e:
                self._last_call = time.monotonic()
                if e.code == 404:
                    return None
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    backoff = 2 ** attempt
                    log.warning("HTTP %s on %s — %ss 후 재시도 (%d/%d)",
                                e.code, url, backoff, attempt, self.max_retries)
                    time.sleep(backoff)
                    continue
                raise SumoApiError(f"HTTP {e.code} for {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                self._last_call = time.monotonic()
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise SumoApiError(f"network error for {url}: {e}") from e
        raise SumoApiError(f"giving up on {url}")

    # -- endpoints ----------------------------------------------------
    def rikishis(self, *, limit: int = 1000, skip: int = 0, **kw: Any) -> Any:
        """하드 리밋 1000. iter_rikishis() 로 전량 순회할 것."""
        return self.get("rikishis", limit=limit, skip=skip, **kw)

    def iter_rikishis(self, *, page: int = 1000, **kw: Any) -> Iterator[dict]:
        skip = 0
        while True:
            data = self.rikishis(limit=page, skip=skip, **kw)
            rows = _rows_of(data)
            if not rows:
                return
            yield from rows
            if len(rows) < page:
                return
            skip += page

    def rikishi(self, rikishi_id: int) -> Any:
        return self.get(f"rikishi/{rikishi_id}")

    def rikishi_stats(self, rikishi_id: int) -> Any:
        return self.get(f"rikishi/{rikishi_id}/stats")

    def basho(self, basho_id: str) -> Any:
        return self.get(f"basho/{basho_id}")

    def banzuke(self, basho_id: str, division: str) -> Any:
        return self.get(f"basho/{basho_id}/banzuke/{DIVISION_PARAM[division]}")

    def torikumi(self, basho_id: str, division: str, day: int) -> Any:
        return self.get(f"basho/{basho_id}/torikumi/{DIVISION_PARAM[division]}/{day}")

    # /api/kimarite 는 매개변수 없이 부르면 HTTP 400 을 돌려준다(2026-09 확인).
    # 어떤 조합을 원하는지 문서에 없으므로 유력한 순서대로 시도한다.
    KIMARITE_PARAM_SETS = (
        {"limit": 1000, "skip": 0},
        {"sortField": "count", "sortOrder": "desc", "limit": 1000, "skip": 0},
        {"sortField": "kimarite", "sortOrder": "asc", "limit": 1000, "skip": 0},
        {},
    )

    def kimarite(self) -> Any:
        last: Exception | None = None
        for params in self.KIMARITE_PARAM_SETS:
            try:
                data = self.get("kimarite", **params)
            except SumoApiError as e:
                last = e
                if "HTTP 400" not in str(e) and "HTTP 422" not in str(e):
                    raise          # 400/422 가 아니면 매개변수 문제가 아니다
                log.debug("kimarite %s → %s, 다음 조합 시도", params, e)
                continue
            if data is not None:
                if params:
                    log.info("kimarite: 매개변수 %s 로 성공", params)
                return data
        if last:
            raise last
        return None

    def ranks(self, rikishi_id: int | None = None) -> Any:
        return self.get("ranks", rikishiId=rikishi_id)

    def shikonas(self, rikishi_id: int | None = None) -> Any:
        return self.get("shikonas", rikishiId=rikishi_id)


def _rows_of(data: Any) -> list[dict]:
    """리스트를 직접 주는 응답과, 한 겹 감싸서 주는 응답을 모두 흡수한다.

    이 API 는 엔드포인트마다 모양이 다르다. 실제로 확인된 것만 해도
      [ {...}, {...} ]                          리스트 직접
      { "records": [ ... ] }                    이름표 붙은 봉투
      { "east": [...], "west": [...] }          반즈케의 동/서 분리
      { "bashoId":.., "torikumi": [ ... ] }     메타데이터 + 목록
    봉투 이름을 다 열거할 수는 없으므로, **딕셔너리 안에 dict 리스트가
    하나뿐이면 그것을 내용물로 본다.** 이러면 새 이름이 나와도 통한다.
    """
    if data is None:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return []

    # 1) 동/서를 나눠 주는 반즈케 형태 — 어느 쪽인지 표시를 남겨야 한다
    if isinstance(data.get("east"), list) or isinstance(data.get("west"), list):
        rows: list[dict] = []
        for side_key, side in (("east", "E"), ("west", "W")):
            for r in data.get(side_key) or []:
                if isinstance(r, dict):
                    rows.append({**r, "_side": side})
        if rows:
            return rows

    # 2) 잘 알려진 봉투 이름
    for key in ("records", "results", "data", "items", "rikishis",
                "torikumi", "banzuke", "matches", "bouts", "kimarite"):
        v = data.get(key)
        if isinstance(v, list) and any(isinstance(r, dict) for r in v):
            return [r for r in v if isinstance(r, dict)]

    # 3) 이름을 모르는 봉투 — dict 리스트가 딱 하나면 그게 내용물이다
    candidates = [
        v for v in data.values()
        if isinstance(v, list) and v and all(isinstance(r, dict) for r in v)
    ]
    if len(candidates) == 1:
        return candidates[0]

    return []


rows_of = _rows_of
