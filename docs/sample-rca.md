# Sample RCA: Fleet Assignment Interruption

## Executive summary

On July 21, 2026, simulated robots remained connected to the fleet service but could not retrieve new assignments for approximately 12 minutes. Heartbeat requests continued to succeed, while assignment requests returned HTTP 500. The incident was mitigated by disabling the faulty assignment-engine configuration. No assignment data was lost.

## Impact

- Three simulated robots across zones A, B, and C were affected.
- Robots already processing assignments could finish their current work.
- No robots could obtain new work during the incident.
- Heartbeat and fleet-connectivity information remained available.

## Detection

The health monitor detected HTTP 503 from `/health`. Robot logs separately showed HTTP 500 responses from assignment requests.

## Timeline

| Time (ET) | Event |
| --- | --- |
| 10:00 | Faulty assignment configuration enabled |
| 10:01 | First robot assignment request returned HTTP 500 |
| 10:02 | Health monitor reported the service as unhealthy |
| 10:04 | Operator confirmed heartbeats still succeeded |
| 10:06 | Logs isolated failures to the assignment request path |
| 10:09 | Operator disabled the faulty configuration |
| 10:10 | Health returned to HTTP 200 |
| 10:12 | All three robots successfully obtained assignments |

## Root cause

A configuration change enabled an invalid assignment-engine mode. The assignment endpoint encountered the condition and returned HTTP 500 for every assignment request.

## Contributing factors

- Pre-deployment validation did not exercise the assignment endpoint.
- The deployment did not include an automatic rollback based on endpoint health.
- The broad health alert detected the failure, but no dedicated assignment-success-rate alarm existed.

## Mitigation and recovery

The operator first confirmed that heartbeats were healthy, reducing the likelihood of a general network or service outage. Request logs showed failures isolated to the assignment path. The operator disabled the configuration, verified HTTP 200 health, and ran robot clients to confirm assignment retrieval and completion.

## Corrective actions

| Action | Owner | Verification |
| --- | --- | --- |
| Add an assignment endpoint integration test | Service team | Test runs in the deployment pipeline |
| Alert on assignment request error rate | Operations | Simulated errors trigger an alarm |
| Add configuration schema validation | Service team | Invalid modes are rejected before deployment |
| Add automated rollback criteria | Platform team | Failed health checks trigger rollback in staging |
| Update the assignment failure runbook | Support lead | On-call review and tabletop exercise completed |

## Lessons learned

Successful heartbeats did not prove the entire system was healthy. They proved that robot-to-service connectivity and the heartbeat code path were operating, which helped isolate the incident to the assignment subsystem. Monitoring should therefore cover critical business operations rather than relying on process-level availability alone.
