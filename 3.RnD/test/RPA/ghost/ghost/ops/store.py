# -*- coding: utf-8 -*-
"""운영 기록 저장소 (SQLite, 표준 라이브러리). 작업(job)·예약(schedule)·운영 이벤트.

작업 상태: queued → running → ok | failed | error(장치) | stopped | cancelled | interrupted
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scenario TEXT NOT NULL, params TEXT, source TEXT, status TEXT NOT NULL,
  created REAL, started REAL, finished REAL,
  attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 2,
  run_dir TEXT, error TEXT, vals TEXT, steps INTEGER, watch INTEGER, duration REAL, schedule_id INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, scenario TEXT NOT NULL, params TEXT,
  kind TEXT NOT NULL, every_min REAL, times TEXT, days TEXT,
  enabled INTEGER DEFAULT 1, last_run REAL, created REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, kind TEXT, detail TEXT
);
"""
DONE = ("ok", "failed", "error", "stopped", "cancelled", "interrupted")


def _row(cur, r) -> dict:
    d = {c[0]: r[i] for i, c in enumerate(cur.description)}
    for k in ("params", "vals", "times", "days"):
        if k in d and d[k]:
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _q(self, sql: str, args=(), one=False):
        with self._lock:
            cur = self.db.execute(sql, args)
            rows = [_row(cur, r) for r in cur.fetchall()] if cur.description else []
            self.db.commit()
            if one:
                return rows[0] if rows else None
            return rows if cur.description else cur.lastrowid

    # ---------------------------------------------------------------- 작업
    def add_job(self, scenario: str, params: Optional[dict] = None, source: str = "manual",
                max_attempts: int = 2, schedule_id: Optional[int] = None) -> int:
        return self._q("INSERT INTO jobs(scenario, params, source, status, created, max_attempts, schedule_id) "
                       "VALUES (?,?,?,?,?,?,?)",
                       (scenario, json.dumps(params or {}, ensure_ascii=False), source, "queued", time.time(),
                        max_attempts, schedule_id))

    def claim_next(self) -> Optional[dict]:
        """가장 오래된 대기 작업을 running 으로 바꾸고 반환."""
        with self._lock:
            cur = self.db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1")
            r = cur.fetchone()
            if r is None:
                return None
            job = _row(cur, r)
            self.db.execute("UPDATE jobs SET status='running', started=?, attempts=attempts+1 WHERE id=?",
                            (time.time(), job["id"]))
            self.db.commit()
        job["status"], job["attempts"] = "running", job["attempts"] + 1
        return job

    def finish_job(self, job_id: int, status: str, **f) -> None:
        cols = {"status": status, "finished": time.time()}
        for k in ("run_dir", "error", "steps", "watch", "duration"):
            if k in f:
                cols[k] = f[k]
        if "vals" in f:
            cols["vals"] = json.dumps(f["vals"], ensure_ascii=False, default=str)
        sets = ", ".join(f"{k}=?" for k in cols)
        self._q(f"UPDATE jobs SET {sets} WHERE id=?", (*cols.values(), job_id))

    def requeue(self, job_id: int, error: str = "") -> None:
        self._q("UPDATE jobs SET status='queued', error=? WHERE id=?", (error, job_id))

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            n = self.db.execute("UPDATE jobs SET status='cancelled', finished=? WHERE id=? AND status='queued'",
                                (time.time(), job_id)).rowcount
            self.db.commit()
        return n > 0

    def job(self, job_id: int) -> Optional[dict]:
        return self._q("SELECT * FROM jobs WHERE id=?", (job_id,), one=True)

    def jobs(self, limit: int = 100, status: Optional[str] = None, since: Optional[float] = None) -> List[dict]:
        sql, args = "SELECT * FROM jobs WHERE 1=1", []
        if status:
            sql += " AND status=?"
            args.append(status)
        if since:
            sql += " AND created>=?"
            args.append(since)
        return self._q(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))

    def pending_for_schedule(self, schedule_id: int) -> bool:
        return bool(self._q("SELECT id FROM jobs WHERE schedule_id=? AND status IN ('queued','running') LIMIT 1",
                            (schedule_id,)))

    def recover_interrupted(self) -> int:
        """시작 시: 이전 프로세스가 실행 중에 끝난 작업을 interrupted 로 기록."""
        with self._lock:
            n = self.db.execute("UPDATE jobs SET status='interrupted', finished=?, error='프로그램 종료로 중단' "
                                "WHERE status='running'", (time.time(),)).rowcount
            self.db.commit()
        return n

    def counts(self) -> dict:
        rows = self._q("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    # ---------------------------------------------------------------- 예약
    def add_schedule(self, name: str, scenario: str, kind: str, params: Optional[dict] = None,
                     every_min: Optional[float] = None, times: Optional[list] = None,
                     days: Optional[list] = None, enabled: bool = True) -> int:
        return self._q("INSERT INTO schedules(name, scenario, params, kind, every_min, times, days, enabled, created) "
                       "VALUES (?,?,?,?,?,?,?,?,?)",
                       (name, scenario, json.dumps(params or {}, ensure_ascii=False), kind, every_min,
                        json.dumps(times or []), json.dumps(days or []), 1 if enabled else 0, time.time()))

    def schedules(self, enabled_only: bool = False) -> List[dict]:
        return self._q("SELECT * FROM schedules" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY id")

    def schedule(self, sid: int) -> Optional[dict]:
        return self._q("SELECT * FROM schedules WHERE id=?", (sid,), one=True)

    def set_schedule(self, sid: int, **f) -> None:
        if not f:
            return
        f = {k: (json.dumps(v) if k in ("times", "days", "params") else v) for k, v in f.items()}
        sets = ", ".join(f"{k}=?" for k in f)
        self._q(f"UPDATE schedules SET {sets} WHERE id=?", (*f.values(), sid))

    def delete_schedule(self, sid: int) -> None:
        self._q("DELETE FROM schedules WHERE id=?", (sid,))

    # ---------------------------------------------------------------- 이벤트
    def add_event(self, kind: str, detail: str = "") -> None:
        self._q("INSERT INTO events(t, kind, detail) VALUES (?,?,?)", (time.time(), kind, detail))

    def events(self, limit: int = 100, since: Optional[float] = None) -> List[dict]:
        if since:
            return self._q("SELECT * FROM events WHERE t>=? ORDER BY id DESC LIMIT ?", (since, limit))
        return self._q("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    def close(self) -> None:
        with self._lock:
            self.db.close()
