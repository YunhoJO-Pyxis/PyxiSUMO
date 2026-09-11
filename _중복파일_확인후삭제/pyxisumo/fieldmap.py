"""Sumo-API 응답 필드명 자동 학습.

Sumo-API 는 응답 스키마를 문서화하지 않는다. 그래서 필드명을 손으로
맞추는 대신, 실제 응답을 보고 **논리 필드 → 실제 키** 대응을 학습해 둔다.

학습 결과는 DB의 app_setting 에 저장한다 (로컬 파일이면 GitHub Actions 러너가
공유하지 못한다). DB가 아직 없을 때를 위해 로컬 캐시 파일도 함께 쓴다.

매칭 규칙 (순서대로 시도)
  1) FIELD_ALIASES 에 적힌 후보 키와 정확히 일치
  2) 정규화(소문자·구분자 제거) 후 일치  — rikishiId ≡ rikishi_id ≡ RIKISHI_ID
  3) 정규화된 후보가 실제 키의 접두/접미로 포함되고 값 타입이 맞음
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

SETTING_KEY = "sumoapi_field_map"
CACHE_PATH = os.environ.get("PYXISUMO_FIELDMAP", "field_map.json")

# 논리 필드가 가져야 할 값의 성격. 후보가 여럿일 때 가려내는 데 쓴다.
_EXPECTED_KIND: dict[str, str] = {
    "rikishi_id": "int",
    "east_id": "int",
    "west_id": "int",
    "winner_id": "int",
    "day": "int",
    "match_no": "int",
    "wins": "int",
    "losses": "int",
    "absences": "int",
    "height": "num",
    "weight": "num",
    "rank_value": "int",
}


def normalize(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _kind_of(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "num"
    if isinstance(v, str):
        return "int" if re.fullmatch(r"-?\d+", v.strip()) else "str"
    return "other"


def _kind_ok(logical: str, value: Any) -> bool:
    want = _EXPECTED_KIND.get(logical)
    if want is None:
        return True
    got = _kind_of(value)
    if want == "int":
        return got == "int"
    if want == "num":
        return got in ("int", "num")
    return True


def learn(
    rows: Iterable[dict],
    logical_fields: Iterable[str],
    aliases: dict[str, list[str]],
) -> dict[str, str]:
    """실제 응답 행들에서 논리 필드 → 실제 키 대응을 추론한다."""
    rows = [r for r in rows if isinstance(r, dict)][:50]
    if not rows:
        return {}

    # 키별 대표값 (None 이 아닌 첫 값)
    sample: dict[str, Any] = {}
    for r in rows:
        for k, v in r.items():
            if k not in sample and v is not None:
                sample[k] = v
    for r in rows:
        for k in r:
            sample.setdefault(k, None)

    norm_index: dict[str, list[str]] = {}
    for k in sample:
        norm_index.setdefault(normalize(k), []).append(k)

    found: dict[str, str] = {}
    for logical in logical_fields:
        cands = aliases.get(logical, [logical])

        # 1) 정확 일치
        hit = next((c for c in cands if c in sample), None)

        # 2) 정규화 일치
        if hit is None:
            for c in cands:
                for k in norm_index.get(normalize(c), []):
                    if _kind_ok(logical, sample.get(k)):
                        hit = k
                        break
                if hit:
                    break

        # 3) 부분 일치 + 타입 확인
        if hit is None:
            for c in cands:
                nc = normalize(c)
                if len(nc) < 3:
                    continue
                for nk, keys in norm_index.items():
                    if nk.startswith(nc) or nk.endswith(nc):
                        for k in keys:
                            if _kind_ok(logical, sample.get(k)):
                                hit = k
                                break
                    if hit:
                        break
                if hit:
                    break

        if hit:
            found[logical] = hit
    return found


# ---------------------------------------------------------------------
#  저장 / 로드
# ---------------------------------------------------------------------
def save_local(mapping: dict[str, str], path: str = CACHE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)


def load_local(path: str = CACHE_PATH) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_db(conn: Any, mapping: dict[str, str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_setting (key, value, note) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET "
            "value = EXCLUDED.value, note = EXCLUDED.note, updated_at = now()",
            (SETTING_KEY, json.dumps(mapping, ensure_ascii=False),
             "pyxisumo.probe 가 실제 응답에서 학습한 필드 대응"),
        )
    conn.commit()


def load_db(conn: Any) -> dict[str, str]:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_setting WHERE key = %s", (SETTING_KEY,))
            row = cur.fetchone()
    except Exception:      # noqa: BLE001 — 테이블이 아직 없을 수 있다
        return {}
    if not row or not row[0]:
        return {}
    data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return {str(k): str(v) for k, v in data.items()}


def install(mapping: dict[str, str]) -> int:
    """학습된 대응을 sumoapi.FIELD_ALIASES 맨 앞에 꽂는다."""
    from . import sumoapi

    n = 0
    for logical, key in mapping.items():
        cands = sumoapi.FIELD_ALIASES.setdefault(logical, [])
        if key in cands:
            cands.remove(key)
        cands.insert(0, key)
        n += 1
    return n


def autoload(conn: Any | None = None) -> int:
    """DB → 로컬 파일 순으로 학습 결과를 찾아 적용한다."""
    mapping = load_db(conn) if conn is not None else {}
    if not mapping:
        mapping = load_local()
    return install(mapping) if mapping else 0
