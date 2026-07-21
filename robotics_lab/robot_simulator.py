"""Simulated robots that register, heartbeat, request, and complete work."""

from __future__ import annotations

import argparse
import json
import random
import threading
import time

from .client import request_json


def run_robot(base_url: str, token: str, robot_id: str, zone: str, cycles: int, interval: float) -> None:
    status, payload = request_json(
        base_url, "POST", "/robots/register", {"robot_id": robot_id, "zone": zone}, token
    )
    print(json.dumps({"robot": robot_id, "action": "register", "http": status, "result": payload}))
    if status != 201:
        return

    battery = random.randint(75, 100)
    active_assignment: int | None = None
    for cycle in range(cycles):
        robot_status = "WORKING" if active_assignment else "IDLE"
        status, payload = request_json(
            base_url,
            "POST",
            f"/robots/{robot_id}/heartbeat",
            {"status": robot_status, "battery": battery},
            token,
        )
        print(json.dumps({"robot": robot_id, "action": "heartbeat", "http": status}))

        if active_assignment is None:
            status, payload = request_json(
                base_url, "GET", f"/robots/{robot_id}/assignment", token=token
            )
            assignment = payload.get("assignment")
            if status == 200 and assignment:
                active_assignment = assignment["assignment_id"]
                print(json.dumps({"robot": robot_id, "action": "accepted", "assignment": assignment}))
            elif status not in {200, 204}:
                print(json.dumps({"robot": robot_id, "action": "assignment_error", "http": status, "result": payload}))
        elif cycle % 2 == 1:
            status, payload = request_json(
                base_url,
                "POST",
                f"/robots/{robot_id}/complete",
                {"assignment_id": active_assignment},
                token,
            )
            print(json.dumps({"robot": robot_id, "action": "complete", "http": status, "assignment_id": active_assignment}))
            if status == 200:
                active_assignment = None
        battery = max(0, battery - random.randint(1, 3))
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simulated robot clients")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--token", default="demo-robot-token")
    parser.add_argument("--robots", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=8)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    threads = []
    zones = ["A", "B", "C"]
    for index in range(args.robots):
        thread = threading.Thread(
            target=run_robot,
            args=(args.url, args.token, f"robot-{index + 1:02d}", zones[index % 3], args.cycles, args.interval),
        )
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
