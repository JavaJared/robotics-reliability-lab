"""SQLite persistence for robots and assignments."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FleetDatabase:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS robots (
                    robot_id TEXT PRIMARY KEY,
                    zone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    battery INTEGER NOT NULL,
                    last_seen TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zone TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    robot_id TEXT,
                    assigned_at TEXT,
                    completed_at TEXT
                );
                """
            )

    def seed_assignments(self) -> None:
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
            if count == 0:
                connection.executemany(
                    "INSERT INTO assignments(zone, description) VALUES (?, ?)",
                    [
                        ("A", "Move tote A-101 to packing"),
                        ("A", "Retrieve pod A-204"),
                        ("B", "Move tote B-110 to sorting"),
                        ("B", "Return pod B-305 to storage"),
                        ("C", "Deliver empty tote to station C-4"),
                        ("C", "Retrieve pod C-119"),
                    ],
                )

    def register_robot(self, robot_id: str, zone: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO robots(robot_id, zone, status, battery, last_seen)
                VALUES (?, ?, 'IDLE', 100, ?)
                ON CONFLICT(robot_id) DO UPDATE SET zone=excluded.zone, last_seen=excluded.last_seen
                """,
                (robot_id, zone, now),
            )
        return self.get_robot(robot_id)

    def heartbeat(self, robot_id: str, status: str, battery: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE robots SET status=?, battery=?, last_seen=? WHERE robot_id=?",
                (status, battery, utc_now(), robot_id),
            )
            if result.rowcount == 0:
                return None
        return self.get_robot(robot_id)

    def get_robot(self, robot_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM robots WHERE robot_id=?", (robot_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_robots(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM robots ORDER BY robot_id").fetchall()
        return [dict(row) for row in rows]

    def next_assignment(self, robot_id: str) -> dict[str, Any] | None:
        robot = self.get_robot(robot_id)
        if not robot:
            return None
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM assignments WHERE robot_id=? AND status='ASSIGNED'",
                (robot_id,),
            ).fetchone()
            if existing:
                return dict(existing)

            queued = connection.execute(
                """
                SELECT * FROM assignments
                WHERE status='QUEUED' AND zone=?
                ORDER BY assignment_id LIMIT 1
                """,
                (robot["zone"],),
            ).fetchone()
            if not queued:
                return None
            claim = connection.execute(
                """
                UPDATE assignments SET status='ASSIGNED', robot_id=?, assigned_at=?
                WHERE assignment_id=? AND status='QUEUED'
                """,
                (robot_id, utc_now(), queued["assignment_id"]),
            )
            assigned = None
            if claim.rowcount == 1:
                assigned = connection.execute(
                    "SELECT * FROM assignments WHERE assignment_id=?",
                    (queued["assignment_id"],),
                ).fetchone()
        # Another robot may have claimed the same queued row between SELECT and
        # UPDATE. Retry so concurrent clients never receive the same assignment.
        return dict(assigned) if assigned else self.next_assignment(robot_id)

    def complete_assignment(self, robot_id: str, assignment_id: int) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE assignments SET status='COMPLETED', completed_at=?
                WHERE assignment_id=? AND robot_id=? AND status='ASSIGNED'
                """,
                (utc_now(), assignment_id, robot_id),
            )
        return result.rowcount == 1

    def reset(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM assignments")
            connection.execute("DELETE FROM robots")
        self.seed_assignments()
