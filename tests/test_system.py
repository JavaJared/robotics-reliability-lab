from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from robotics_lab.client import request_json
from robotics_lab.server import build_server


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.server = build_server("127.0.0.1", 0, str(Path(cls.tempdir.name) / "test.db"), slow_seconds=0.02)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        request_json(self.url, "POST", "/admin/reset", {}, "demo-admin-token", True)

    def test_robot_assignment_lifecycle(self) -> None:
        status, _ = request_json(
            self.url, "POST", "/robots/register", {"robot_id": "r-1", "zone": "A"}
        )
        self.assertEqual(status, 201)

        status, payload = request_json(self.url, "GET", "/robots/r-1/assignment")
        self.assertEqual(status, 200)
        assignment_id = payload["assignment"]["assignment_id"]

        status, payload = request_json(
            self.url, "POST", "/robots/r-1/complete", {"assignment_id": assignment_id}
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["completed"])

    def test_authentication_is_required(self) -> None:
        status, payload = request_json(
            self.url,
            "POST",
            "/robots/register",
            {"robot_id": "r-2", "zone": "B"},
            token="wrong",
        )
        self.assertEqual(status, 401)
        self.assertIn("token", payload["error"])

    def test_database_failure_is_visible_in_health_and_requests(self) -> None:
        status, _ = request_json(
            self.url,
            "POST",
            "/admin/failures",
            {"mode": "database_down", "enabled": True},
            "demo-admin-token",
            True,
        )
        self.assertEqual(status, 200)
        status, payload = request_json(self.url, "GET", "/health")
        self.assertEqual(status, 503)
        self.assertIn("database_down", payload["active_failures"])

        status, payload = request_json(
            self.url, "POST", "/robots/register", {"robot_id": "r-3", "zone": "C"}
        )
        self.assertEqual(status, 503)
        self.assertIn("database", payload["error"])

    def test_assignment_failure_isolated_from_heartbeat(self) -> None:
        request_json(self.url, "POST", "/robots/register", {"robot_id": "r-4", "zone": "A"})
        request_json(
            self.url,
            "POST",
            "/admin/failures",
            {"mode": "assignment_errors", "enabled": True},
            "demo-admin-token",
            True,
        )
        status, _ = request_json(
            self.url, "POST", "/robots/r-4/heartbeat", {"status": "IDLE", "battery": 90}
        )
        self.assertEqual(status, 200)
        status, _ = request_json(self.url, "GET", "/robots/r-4/assignment")
        self.assertEqual(status, 500)


if __name__ == "__main__":
    unittest.main()
