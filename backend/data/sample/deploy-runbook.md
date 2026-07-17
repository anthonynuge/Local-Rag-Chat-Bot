# Deploy Runbook

## Overview

Northwind Fleet OS and related services deploy through the `northwind` CLI.
Only engineers on the Platform or Deploy Tools teams with production SSO
groups may push to prod. Staging is open to any engineer who has completed
NorthVPN & Secrets training. This runbook covers environments, the deploy
command, rollback, on-call, and incident paging. Robot firmware flashes are
out of scope here — see the Firmware wiki (separate repo).

## Environments

| Env | Cluster | Purpose | Data |
|-----|---------|---------|------|
| `dev` | laptop Docker Compose | local iteration | synthetic |
| `staging` | `fleet-stage-a` (Boulder DC) | shared integration | anonymized customer fixtures |
| `prod` | `fleet-prod-east` + `fleet-prod-eu` | customer control planes | live |

Staging and prod require NorthVPN. Prod additionally requires a hardware
security key for the SSO step. Never point a local `kubectl` at prod; use
`northwind` which opens a short-lived session. ShipLog records every prod
deploy with the git SHA, operator, and ticket ID.

## Deploy command

From a clean `main` (or a release tag):

```
northwind deploy --env staging --service fleet-os --ref HEAD
northwind deploy --env prod --service fleet-os --ref v2026.07.14
```

Flags:

- `--env` — `staging` or `prod` (required).
- `--service` — `fleet-os`, `shelfsorter-api`, or `docklink-ingest`.
- `--ref` — git SHA or tag. Prod rejects floating branch names.
- `--dry-run` — print the planned rollout without applying.

Staging deploys roll out immediately. Prod uses a canary: 10% of pods for 15
minutes, then the remainder if error rate stays below 1%. Watch `#deploys`
during the canary window. The CLI blocks a second concurrent prod deploy for
the same service.

Always attach a ForgeDesk or GitHub issue ID when prompted; ShipLog stores it
with the release.

## Rollback procedure

If error rate exceeds 1% or a Sev-1/Sev-2 is declared:

1. In Slack `#deploys`, announce `ROLLBACK starting` with service and SHA.
2. Run `northwind rollback --env prod --service <name>`. This redeploys the
   previous ShipLog-recorded SHA. No `--ref` needed.
3. Confirm pod healthy counts in the CLI output and in Fleet OS Console.
4. If rollback itself fails, page the on-call (below) and freeze further
   deploys with `northwind freeze --env prod`.

Staging rollback uses the same command with `--env staging`. Do not hotfix
prod by editing live configs — cut a tagged release and deploy forward or
roll back cleanly. Priya Natarajan (CTO) must approve any freeze lasting more
than four hours.

## On-call rotation

Platform and Firmware share a **weekly** primary/secondary rotation. Shifts
start Monday 10:00 Boulder time and run seven days. The schedule lives in
PagerDuty schedule `fleet-primary`. Secondary is automatically escalated if
primary does not acknowledge within 10 minutes.

Expectations: laptop nearby, NorthVPN connected within 15 minutes of a page,
and availability to join `#oncall`. PTO during a scheduled week requires a
swap in PagerDuty at least 48 hours ahead; see the PTO policy for HubNorth
request timing. New hires are not put on primary until after two shadow
weeks with a secondary mentor.

## Incident paging

Page via PagerDuty service `fleet-os` (or `robot-firmware` for device
Sev-1s). From Slack, `/pd trigger` in `#oncall` also works if you have the
PagerDuty Slack app linked. Severity guide:

- **Sev-1** — customer fleet stuck or control plane down across a region.
- **Sev-2** — single-customer outage or canary failure mid-deploy.
- **Sev-3** — degraded performance; fix in business hours unless worsening.

During a Sev-1, the primary owns the bridge, posts timeline notes every 15
minutes in `#oncall`, and opens a ShipLog incident record. Customer Success
(Lucas Berg's team) handles external status updates; engineers do not email
customers directly from personal accounts. After resolution, file a short
postmortem template in HubNorth within three business days — templates are
under Engineering → Incidents.
