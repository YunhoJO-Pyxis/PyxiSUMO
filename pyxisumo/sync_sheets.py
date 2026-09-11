"""스프레드시트 → Postgres 동기화 (한국어 표기·용어집).

설계서 二장의 결론: 메인 DB는 Postgres, 스프레드시트는 **사람이 손으로 채우는
마스터의 입력 UI**. 기계번역이 大の里를 "큰 마을"로 바꾸는 사고를 막기 위해
시코나·헤야·키마리테의 한국어 표기는 사람이 시트에서 채우고 여기서 끌어온다.

시트는 '웹에 게시'(파일 → 공유 → 웹에 게시 → CSV)만 해두면 되고
API 키·서비스 계정이 필요 없다. 읽기 전용이므로 rate limit 문제도 없다.

시트 형식 (첫 행은 헤더):

    shikona 탭 :  name_ja , name_ko
    heya    탭 :  slug    , name_ko
    kimarite 탭:  code    , name_ko , desc_ko

    python -m pyxisumo.sync_sheets --sheet-id <SPREADSHEET_ID>
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import urllib.parse
import urllib.request

from . import db

log = logging.getLogger("sheets")

CSV_URL = ("https://docs.google.com/spreadsheets/d/{sheet_id}"
           "/gviz/tq?tqx=out:csv&sheet={tab}")

UPDATE_HEYA_KO = """
UPDATE heya SET name_ko = %s, updated_at = now()
WHERE slug = %s AND name_ko IS DISTINCT FROM %s
"""

UPDATE_KIMARITE_KO = """
UPDATE kimarite SET name_ko = %s, desc_ko = COALESCE(%s, desc_ko)
WHERE code = %s AND (name_ko IS DISTINCT FROM %s OR desc_ko IS DISTINCT FROM %s)
"""


def fetch_tab(sheet_id: str, tab: str) -> list[dict[str, str]]:
    url = CSV_URL.format(sheet_id=sheet_id, tab=urllib.parse.quote(tab))
    req = urllib.request.Request(url, headers={"User-Agent": "PyxiSumo/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    log.info("시트 '%s': %d행", tab, len(rows))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="스프레드시트 → Postgres 표기 동기화")
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--tabs", default="shikona,heya,kimarite")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    tabs = [t.strip() for t in args.tabs.split(",") if t.strip()]

    with db.connect() as conn:
        if "shikona" in tabs:
            rows = [
                (r["name_ko"].strip(), r["name_ja"].strip(), r["name_ko"].strip())
                for r in fetch_tab(args.sheet_id, "shikona")
                if r.get("name_ja") and r.get("name_ko")
            ]
            n = db.executemany(conn, db.UPDATE_SHIKONA_KO, rows)
            log.info("shikona 한국어 표기 %d행 반영", n)

        if "heya" in tabs:
            rows = [
                (r["name_ko"].strip(), r["slug"].strip(), r["name_ko"].strip())
                for r in fetch_tab(args.sheet_id, "heya")
                if r.get("slug") and r.get("name_ko")
            ]
            db.executemany(conn, UPDATE_HEYA_KO, rows)

        if "kimarite" in tabs:
            rows = []
            for r in fetch_tab(args.sheet_id, "kimarite"):
                if not (r.get("code") and r.get("name_ko")):
                    continue
                ko = r["name_ko"].strip()
                desc = (r.get("desc_ko") or "").strip() or None
                rows.append((ko, desc, r["code"].strip().lower(), ko, desc))
            db.executemany(conn, UPDATE_KIMARITE_KO, rows)

        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
