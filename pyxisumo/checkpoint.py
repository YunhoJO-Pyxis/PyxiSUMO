"""초기 적재 체크포인트.

1958년부터 받으면 바쇼가 400개가 넘는다. 중간에 끊기면 처음부터 다시 받는 대신
끝난 단위를 건너뛰고 이어서 받아야 한다. 여기서 그 상태를 관리한다.

    with checkpoint.step(conn, "banzuke", "202609") as done:
        if done.skip:
            ...
        done.rows = ingest_banzuke(...)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

log = logging.getLogger("checkpoint")

MARK_RUNNING = """
INSERT INTO ingest_checkpoint (task, item, status, started_at)
VALUES (%s, %s, 'running', now())
ON CONFLICT (task, item) DO UPDATE SET
  status = 'running', started_at = now(), updated_at = now(), error = NULL
"""

MARK_DONE = """
INSERT INTO ingest_checkpoint (task, item, status, rows_affected, error)
VALUES (%s, %s, 'done', %s, NULL)
ON CONFLICT (task, item) DO UPDATE SET
  status = 'done', rows_affected = EXCLUDED.rows_affected,
  error = NULL, updated_at = now()
"""

MARK_FAILED = """
INSERT INTO ingest_checkpoint (task, item, status, error)
VALUES (%s, %s, 'failed', %s)
ON CONFLICT (task, item) DO UPDATE SET
  status = 'failed', error = EXCLUDED.error, updated_at = now()
"""


def completed(conn: Any, task: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT item FROM ingest_checkpoint WHERE task = %s AND status = 'done'",
            (task,),
        )
        return {r[0] for r in cur.fetchall()}


def failed(conn: Any, task: str | None = None) -> list[tuple[str, str, str]]:
    sql = "SELECT task, item, COALESCE(error,'') FROM ingest_checkpoint WHERE status = 'failed'"
    params: tuple = ()
    if task:
        sql += " AND task = %s"
        params = (task,)
    with conn.cursor() as cur:
        cur.execute(sql + " ORDER BY task, item", params)
        return [tuple(r) for r in cur.fetchall()]


def reset(conn: Any, task: str | None = None, only_failed: bool = False) -> int:
    sql = "DELETE FROM ingest_checkpoint WHERE true"
    params: list = []
    if task:
        sql += " AND task = %s"
        params.append(task)
    if only_failed:
        sql += " AND status = 'failed'"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        n = cur.rowcount
    conn.commit()
    return n


@dataclass
class Step:
    task: str
    item: str
    skip: bool = False
    rows: int = 0


@contextmanager
def step(conn: Any, task: str, item: str, *, force: bool = False) -> Iterator[Step]:
    """한 단위 작업을 체크포인트로 감싼다.

    이미 'done' 이면 skip=True 로 넘어오고, 예외가 나면 'failed' 로 기록한 뒤
    다시 올린다 — 실패를 조용히 삼키면 구멍 난 데이터로 예측을 돌리게 된다.
    """
    s = Step(task=task, item=item)
    if not force:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM ingest_checkpoint WHERE task = %s AND item = %s",
                (task, item),
            )
            row = cur.fetchone()
        if row and row[0] == "done":
            s.skip = True
            yield s
            return

    with conn.cursor() as cur:
        cur.execute(MARK_RUNNING, (task, item))
    conn.commit()

    try:
        yield s
    except Exception as e:                             # noqa: BLE001
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(MARK_FAILED, (task, item, f"{type(e).__name__}: {e}"[:2000]))
        conn.commit()
        log.error("%s/%s 실패: %s", task, item, e)
        raise
    else:
        with conn.cursor() as cur:
            cur.execute(MARK_DONE, (task, item, s.rows))
        conn.commit()
