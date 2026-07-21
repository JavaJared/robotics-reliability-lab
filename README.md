# Robotics Systems Reliability Lab

A dependency-free Python simulation of robots communicating with a central assignment service. The lab is designed as a Technical Support Engineer portfolio project: it provides realistic health checks, structured logs, authentication, heartbeats, controllable failures, recovery procedures, automated tests, and a sample root cause analysis.

## What this demonstrates

- Python scripting and HTTP/JSON web services
- Distributed-system concepts: heartbeats, partial failures, timeouts, and service dependencies
- SQLite persistence and basic concurrency
- Operational monitoring and structured logging
- Incident mitigation, root cause analysis, and runbook writing
- Docker packaging and environment-based configuration

## Architecture

```text
Simulated robots ──HTTP──> Assignment API ──> SQLite
      │                         │
      └── heartbeats            ├── JSON logs
                                ├── health endpoint
Operator CLI ──HTTP─────────────└── failure controls
```

The system intentionally separates robot operations from administrator operations. Robots authenticate with `X-Robot-Token`; administrative endpoints use `X-Admin-Token`.

## Quick start

Requires Python 3.10 or newer. No third-party Python packages are needed.

Terminal 1:

```bash
python -m robotics_lab.server
```

Terminal 2:

```bash
python -m robotics_lab.robot_simulator --robots 3 --cycles 8
```

Terminal 3:

```bash
python -m robotics_lab.control health
python -m robotics_lab.control robots
```

The API listens on `http://127.0.0.1:8080` by default. Server logs are emitted as one JSON object per line and include request IDs, HTTP status codes, and latency.

## Run a failure scenario

Turn on an assignment-engine failure:

```bash
python -m robotics_lab.control failure assignment_errors on
python -m robotics_lab.control health
python -m robotics_lab.robot_simulator --robots 3 --cycles 4
```

Observe that robot heartbeats still succeed while assignment requests fail. This is a partial failure: the fleet remains connected, but it cannot receive work.

Recover the system:

```bash
python -m robotics_lab.control failure assignment_errors off
python -m robotics_lab.control health
```

Available failure modes:

| Mode | Simulated behavior |
| --- | --- |
| `assignment_errors` | Assignment requests return HTTP 500; heartbeats continue |
| `database_down` | Database-backed operations return HTTP 503 |
| `service_down` | Most API operations return HTTP 503 |
| `slow_api` | Non-administrative requests are delayed |

Reset the database and clear every failure:

```bash
python -m robotics_lab.control reset
```

## Monitor health and latency

```bash
python -m robotics_lab.control monitor --count 10 --interval 1
```

The monitor exits with code `1` if any health check fails, which makes it usable in scripts or a basic deployment pipeline.

## Run the tests

```bash
python -m unittest discover -v
```

The tests launch the service on an ephemeral port and verify the robot assignment lifecycle, authentication, database outages, and partial assignment failures.

## Docker

```bash
docker compose up --build
```

In another terminal:

```bash
docker compose run --rm simulator
```

Change the demo credentials in any environment that is not an isolated local lab:

```bash
export ROBOT_TOKEN='replace-me'
export ADMIN_TOKEN='replace-me-too'
```

## API summary

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Report health and active failures |
| `POST` | `/robots/register` | Register or reconnect a robot |
| `POST` | `/robots/{id}/heartbeat` | Update status, battery, and last-seen time |
| `GET` | `/robots/{id}/assignment` | Obtain the robot's current or next assignment |
| `POST` | `/robots/{id}/complete` | Complete an assigned task |
| `GET` | `/robots` | List fleet state; admin only |
| `POST` | `/admin/failures` | Enable or disable a failure; admin only |
| `POST` | `/admin/reset` | Clear failures and reset lab data; admin only |

See [docs/runbook.md](docs/runbook.md) for investigation procedures and [docs/sample-rca.md](docs/sample-rca.md) for a blameless incident report.
