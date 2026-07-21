# Runbook: Robots Not Receiving Assignments

## Purpose

Use this runbook when one or more robots remain connected but do not receive new assignments. Protect personnel and follow site safety procedures before any physical inspection. This software lab does not simulate or replace lockout/tagout procedures.

## 1. Establish impact

- Record the incident start time and reporter.
- Determine whether one robot, one zone, or the full fleet is affected.
- Confirm whether robots still send heartbeats.
- Check whether work is delayed or completely stopped.
- Open an incident communication channel for broad or critical impact.

## 2. Check overall service health

```bash
python -m robotics_lab.control health
```

Expected healthy response:

```json
{
  "http": 200,
  "status": "healthy",
  "active_failures": []
}
```

An HTTP 503 means the service has detected a failed dependency or subsystem. An HTTP status of `0` from the CLI indicates that the client could not establish an HTTP connection, suggesting process, host, port, routing, or firewall trouble.

## 3. Inspect fleet scope

```bash
python -m robotics_lab.control robots
```

- All robots offline: investigate the service or shared network path.
- One zone offline: investigate a shared zone network or controller.
- Heartbeats online but assignments fail: focus on the assignment engine or database path.
- One robot offline: focus on that robot's power, network, configuration, or local software.

## 4. Inspect logs

Search server output for:

- `status:500`: internal application failure
- `status:503`: unavailable service or dependency
- High `latency_ms`: slow processing or dependency
- A robot ID or matching `request_id`
- `failure_changed`: lab failure injection event

Preserve relevant logs before restarting the service. Align timestamps between robot output, API logs, and operator actions.

## 5. Isolate the failing layer

Work from broad connectivity toward application dependencies:

```bash
ping <host>
ip route
getent hosts <hostname>
curl -v http://127.0.0.1:8080/health
ss -tulpn | grep 8080
ps aux | grep robotics_lab
df -h
free -h
```

Interpretation:

- No name resolution: investigate DNS.
- No route or packet reachability: investigate IP routing, VLANs, or firewalls.
- Connection refused: verify the API process and listening port.
- Health works but assignments return 500: investigate the assignment code path.
- Database-backed requests return 503: investigate database access and storage.
- Requests succeed but are slow: examine latency logs and resource utilization.

## 6. Mitigate

Use the safest reversible option supported by the environment:

1. Disable or roll back the bad change.
2. Restore the failed dependency.
3. Fail over to a healthy service if redundancy exists.
4. Restart only when evidence has been collected and the action is authorized.

For this lab, disable the active failure:

```bash
python -m robotics_lab.control failure assignment_errors off
```

## 7. Verify recovery

```bash
python -m robotics_lab.control health
python -m robotics_lab.robot_simulator --robots 3 --cycles 4
python -m robotics_lab.control robots
```

Verify that:

- Health returns HTTP 200.
- Heartbeats succeed.
- Robots obtain and complete assignments.
- Latency returns to its normal baseline.
- No new 500 or 503 responses appear.

## 8. Follow-up

- Write an RCA with a timestamped timeline.
- Separate the symptom, immediate cause, root cause, and contributing factors.
- Assign corrective actions with owners and due dates.
- Improve monitoring, tests, deployment safeguards, or documentation.
