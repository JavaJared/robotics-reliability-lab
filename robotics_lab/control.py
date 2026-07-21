"""Operator CLI for health checks and controlled failure injection."""

from __future__ import annotations

import argparse
import json
import sys
import time

from .client import request_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Operate the robotics reliability lab")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--admin-token", default="demo-admin-token")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("robots")
    subparsers.add_parser("reset")
    monitor = subparsers.add_parser("monitor")
    monitor.add_argument("--count", type=int, default=10)
    monitor.add_argument("--interval", type=float, default=2)
    failure = subparsers.add_parser("failure")
    failure.add_argument("mode", choices=["service_down", "database_down", "slow_api", "assignment_errors"])
    failure.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()

    if args.command == "health":
        status, payload = request_json(args.url, "GET", "/health")
    elif args.command == "robots":
        status, payload = request_json(args.url, "GET", "/robots", token=args.admin_token, admin=True)
    elif args.command == "reset":
        status, payload = request_json(args.url, "POST", "/admin/reset", {}, args.admin_token, True)
    elif args.command == "failure":
        status, payload = request_json(
            args.url,
            "POST",
            "/admin/failures",
            {"mode": args.mode, "enabled": args.state == "on"},
            args.admin_token,
            True,
        )
    else:
        failures = 0
        for _ in range(args.count):
            started = time.monotonic()
            status, payload = request_json(args.url, "GET", "/health")
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            print(json.dumps({"http": status, "latency_ms": latency_ms, **payload}))
            failures += status != 200
            time.sleep(args.interval)
        sys.exit(1 if failures else 0)

    print(json.dumps({"http": status, **payload}, indent=2))
    sys.exit(0 if 200 <= status < 300 else 1)


if __name__ == "__main__":
    main()
