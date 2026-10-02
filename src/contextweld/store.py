"""이미지 관측·판단·작업자 확인을 보존하는 SQLite 저장소."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import decide, memory_scope


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def memories(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM runs ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            run = json.loads(row["payload"])
            if run.get("review_status") == "approved" and run.get("reviews"):
                review = run["reviews"][-1]
                result.append({"review_id": review["id"], "run_id": run["id"], "note": review["note"],
                               "scope": review["scope"], "confirmed_fields": review["confirmed_fields"]})
        return result

    def create(self, source: dict[str, Any], observations: list[dict[str, Any]],
               context: dict[str, Any], knowledge: dict[str, Any]) -> dict[str, Any]:
        memories = self.memories()
        run = {"id": uuid.uuid4().hex, "created_at": now(), "source": source, "observations": observations,
               "context": context, "rules_version": knowledge["version"], "memory_snapshot": memories,
               "baseline": decide(observations, context, knowledge, use_context=False),
               "contextual": decide(observations, context, knowledge, memories=memories),
               "revision": 0, "review_status": "pending", "reviews": [],
               "schema_version": "contextweld-spike-v1"}
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?)", (run["id"], run["created_at"], encode(run)))
        return run

    def get(self, run_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("분석 기록을 찾을 수 없습니다.")
        return json.loads(row["payload"])

    def history(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def review(self, run_id: str, action: str, note: str, corrections: dict[str, Any],
               revision: int, knowledge: dict[str, Any]) -> dict[str, Any]:
        if action not in {"approve", "hold"}:
            raise ValueError("확인 동작은 approve 또는 hold여야 합니다.")
        if not note.strip():
            raise ValueError("확인·보류 이유를 남겨주세요.")
        with self.connect() as db:
            # 같은 분석을 두 화면에서 확인할 때 오래된 화면의 변경을 거부한다.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("분석 기록을 찾을 수 없습니다.")
            run = json.loads(row["payload"])
            if run["revision"] != revision:
                raise ValueError("다른 화면에서 변경한 기록입니다. 새로 불러온 뒤 확인해주세요.")
            if run["rules_version"] != knowledge["version"]:
                raise ValueError("규칙 버전이 변경됐습니다. 다시 분석해주세요.")
            cumulative = {**run.get("operator_corrections", {}), **corrections}
            decision = decide(run["observations"], run["context"], knowledge,
                              memories=run["memory_snapshot"], corrections=cumulative)
            if action == "approve" and (decision["blockers"] or not decision["recipe"]):
                raise ValueError("해결되지 않은 충돌 또는 누락이 있습니다. 표기를 수정하거나 보류해주세요.")
            review = {"id": uuid.uuid4().hex, "created_at": now(), "action": action, "note": note.strip(),
                      "corrections": corrections, "confirmed_fields": decision["fields"],
                      "scope": memory_scope(run["context"], knowledge["version"]),
                      "meaning": "demo_interpretation_confirmation_not_welding_execution"}
            run["reviews"].append(review)
            run["contextual"] = decision
            run["operator_corrections"] = cumulative
            run["review_status"] = "approved" if action == "approve" else "held"
            run["revision"] += 1
            db.execute("INSERT INTO reviews VALUES (?, ?, ?, ?)",
                       (review["id"], run_id, review["created_at"], encode(review)))
            db.execute("UPDATE runs SET payload=? WHERE id=?", (encode(run), run_id))
        return run
