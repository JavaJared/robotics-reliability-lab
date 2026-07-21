"""Threaded HTTP API for the mini fleet-management service."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .database import FleetDatabase


LOGGER = logging.getLogger("robotics_lab")
ROBOT_PATH = re.compile(r"^/robots/([^/]+)/(heartbeat|assignment|complete)$")
FAILURE_MODES = {"service_down", "database_down", "slow_api", "assignment_errors"}


class FailureState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled: set[str] = set()

    def set(self, mode: str, enabled: bool) -> set[str]:
        with self._lock:
            if enabled:
                self._enabled.add(mode)
            else:
                self._enabled.discard(mode)
            return set(self._enabled)

    def enabled(self, mode: str) -> bool:
        with self._lock:
            return mode in self._enabled

    def all(self) -> list[str]:
        with self._lock:
            return sorted(self._enabled)

    def clear(self) -> None:
        with self._lock:
            self._enabled.clear()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    LOGGER.info(json.dumps(payload, separators=(",", ":")))


def build_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    db_path: str = "data/fleet.db",
    robot_token: str = "demo-robot-token",
    admin_token: str = "demo-admin-token",
    slow_seconds: float = 2.0,
) -> ThreadingHTTPServer:
    database = FleetDatabase(db_path)
    database.seed_assignments()
    failures = FailureState()

    class FleetHandler(BaseHTTPRequestHandler):
        server_version = "RoboticsReliabilityLab/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Request-ID", self.request_id)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, admin: bool = False) -> bool:
            expected = admin_token if admin else robot_token
            provided = self.headers.get("X-Admin-Token" if admin else "X-Robot-Token")
            if provided != expected:
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "invalid or missing token"})
                return False
            return True

        def _begin_request(self) -> bool:
            self.request_id = self.headers.get("X-Request-ID", str(uuid.uuid4()))
            self.started = time.monotonic()
            path = urlparse(self.path).path
            if failures.enabled("slow_api") and not path.startswith("/admin/"):
                time.sleep(slow_seconds)
            if failures.enabled("service_down") and path not in {"/health", "/admin/failures", "/admin/reset"}:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "service unavailable"})
                return False
            return True

        def _finish_request(self, status: int) -> None:
            log_event(
                "request_complete",
                request_id=self.request_id,
                method=self.command,
                path=urlparse(self.path).path,
                status=status,
                latency_ms=round((time.monotonic() - self.started) * 1000, 2),
            )

        def do_GET(self) -> None:
            if not self._begin_request():
                self._finish_request(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            path = urlparse(self.path).path
            status = HTTPStatus.OK
            payload: dict[str, Any]
            try:
                if path == "/health":
                    healthy = not any(
                        failures.enabled(mode)
                        for mode in ("service_down", "database_down", "assignment_errors")
                    )
                    status = HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
                    payload = {
                        "status": "healthy" if healthy else "unhealthy",
                        "active_failures": failures.all(),
                    }
                elif path == "/robots":
                    if not self._authorized(admin=True):
                        self._finish_request(HTTPStatus.UNAUTHORIZED)
                        return
                    if failures.enabled("database_down"):
                        raise sqlite_unavailable()
                    robots = database.list_robots()
                    now = datetime.now(timezone.utc)
                    for robot in robots:
                        last_seen = datetime.fromisoformat(robot["last_seen"])
                        if (now - last_seen).total_seconds() > 10:
                            robot["connectivity"] = "OFFLINE"
                        else:
                            robot["connectivity"] = "ONLINE"
                    payload = {"robots": robots}
                else:
                    match = ROBOT_PATH.match(path)
                    if match and match.group(2) == "assignment":
                        if not self._authorized():
                            self._finish_request(HTTPStatus.UNAUTHORIZED)
                            return
                        if failures.enabled("database_down"):
                            raise sqlite_unavailable()
                        if failures.enabled("assignment_errors"):
                            status = HTTPStatus.INTERNAL_SERVER_ERROR
                            payload = {"error": "assignment engine failed"}
                        else:
                            assignment = database.next_assignment(match.group(1))
                            if assignment:
                                payload = {"assignment": assignment}
                            elif database.get_robot(match.group(1)):
                                status = HTTPStatus.NO_CONTENT
                                payload = {}
                            else:
                                status = HTTPStatus.NOT_FOUND
                                payload = {"error": "robot not registered"}
                    else:
                        status = HTTPStatus.NOT_FOUND
                        payload = {"error": "route not found"}
            except RuntimeError as exc:
                status = HTTPStatus.SERVICE_UNAVAILABLE
                payload = {"error": str(exc)}
            self._send(status, payload)
            self._finish_request(status)

        def do_POST(self) -> None:
            if not self._begin_request():
                self._finish_request(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            path = urlparse(self.path).path
            status = HTTPStatus.OK
            try:
                body = self._json_body()
                if path == "/robots/register":
                    if not self._authorized():
                        self._finish_request(HTTPStatus.UNAUTHORIZED)
                        return
                    if failures.enabled("database_down"):
                        raise sqlite_unavailable()
                    robot_id = str(body.get("robot_id", "")).strip()
                    zone = str(body.get("zone", "")).strip().upper()
                    if not robot_id or zone not in {"A", "B", "C"}:
                        status = HTTPStatus.BAD_REQUEST
                        payload = {"error": "robot_id and zone A, B, or C are required"}
                    else:
                        status = HTTPStatus.CREATED
                        payload = {"robot": database.register_robot(robot_id, zone)}
                elif path == "/admin/failures":
                    if not self._authorized(admin=True):
                        self._finish_request(HTTPStatus.UNAUTHORIZED)
                        return
                    mode = str(body.get("mode", ""))
                    if mode not in FAILURE_MODES:
                        status = HTTPStatus.BAD_REQUEST
                        payload = {"error": f"mode must be one of {sorted(FAILURE_MODES)}"}
                    else:
                        active = failures.set(mode, bool(body.get("enabled", True)))
                        payload = {"active_failures": sorted(active)}
                        log_event("failure_changed", mode=mode, enabled=bool(body.get("enabled", True)))
                elif path == "/admin/reset":
                    if not self._authorized(admin=True):
                        self._finish_request(HTTPStatus.UNAUTHORIZED)
                        return
                    failures.clear()
                    database.reset()
                    payload = {"status": "reset complete"}
                else:
                    match = ROBOT_PATH.match(path)
                    if not match or match.group(2) not in {"heartbeat", "complete"}:
                        status = HTTPStatus.NOT_FOUND
                        payload = {"error": "route not found"}
                    elif not self._authorized():
                        self._finish_request(HTTPStatus.UNAUTHORIZED)
                        return
                    elif failures.enabled("database_down"):
                        raise sqlite_unavailable()
                    elif match.group(2) == "heartbeat":
                        battery = int(body.get("battery", 100))
                        robot_status = str(body.get("status", "IDLE")).upper()
                        if not 0 <= battery <= 100:
                            status = HTTPStatus.BAD_REQUEST
                            payload = {"error": "battery must be between 0 and 100"}
                        else:
                            robot = database.heartbeat(match.group(1), robot_status, battery)
                            if robot:
                                payload = {"robot": robot}
                            else:
                                status = HTTPStatus.NOT_FOUND
                                payload = {"error": "robot not registered"}
                    else:
                        assignment_id = int(body.get("assignment_id", 0))
                        completed = database.complete_assignment(match.group(1), assignment_id)
                        status = HTTPStatus.OK if completed else HTTPStatus.CONFLICT
                        payload = {"completed": completed}
            except (ValueError, json.JSONDecodeError):
                status = HTTPStatus.BAD_REQUEST
                payload = {"error": "invalid JSON or field type"}
            except RuntimeError as exc:
                status = HTTPStatus.SERVICE_UNAVAILABLE
                payload = {"error": str(exc)}
            self._send(status, payload)
            self._finish_request(status)

    return ThreadingHTTPServer((host, port), FleetHandler)


def sqlite_unavailable() -> RuntimeError:
    return RuntimeError("database dependency unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini robotics assignment service")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/fleet.db"))
    args = parser.parse_args()
    configure_logging()
    server = build_server(
        args.host,
        args.port,
        args.db,
        os.getenv("ROBOT_TOKEN", "demo-robot-token"),
        os.getenv("ADMIN_TOKEN", "demo-admin-token"),
    )
    log_event("server_started", host=args.host, port=args.port, database=args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log_event("server_stopped")


if __name__ == "__main__":
    main()
