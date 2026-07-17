# New Hire Onboarding

## Before day one

Your manager submits a hire ticket in HubNorth at least five business days
before start. People Ops (Mira Okonkwo's team) creates your Northwind ID,
which looks like `first.last` and is the login for email, Slack, and HubNorth.
You receive a welcome email from `people@northwind-robotics.example` with a
temporary HubNorth password and a link to book your laptop handoff. If that
email does not arrive 48 hours before day one, ping `#people-help` on Slack —
do not email personal accounts.

Complete the background-check consent form in HubNorth before arrival. US
hires also upload I-9 documents in person on day one; Eindhoven hires follow
the local Dutch onboarding checklist linked from the same HubNorth task list.

## Day-one accounts to request

Open a ForgeDesk ticket (category "New Hire Access") on your first morning and
request the standard bundle:

1. Google Workspace (mail + Drive) — usually already provisioned.
2. Slack workspace `northwind-floor` — invite comes from `#it-help`.
3. GitHub org `northwind-robotics` — Engineering and Deploy Tools only.
4. HubNorth (HR, PTO, org chart) — already live for all hires.
5. NorthVPN client profile — required before any staging or production access.
6. PagerDuty user (on-call eligible roles only) — added by Platform leads.

Contractors get HubNorth + Slack + NorthVPN only unless a manager checks
"extended tool access" on the ForgeDesk ticket. Expect account activation
within four business hours for the standard bundle.

## Laptop setup

Boulder and Austin hires pick up a locked MacBook Pro or ThinkPad T16 at the
front desk; remote hires receive a shipped device via ShipLog tracking. First
boot forces FileVault/BitLocker enrollment — encryption is mandatory before
joining NorthVPN. Install:

- NorthVPN (config profile in the welcome email)
- Slack
- 1Password Business (invite from IT; company vaults live here)
- Homebrew or Chocolatey as appropriate
- For engineers: Docker Desktop, `gh` CLI, and the `northwind` CLI from the
  internal package mirror (`https://pkgs.northwind-robotics.example`)

Run `northwind doctor` after installing the CLI. It checks VPN, SSO, and
Docker. Paste the green output into your ForgeDesk ticket and close it. Do
not store production kubeconfigs on the laptop — those live in Fleet OS via
SSO after VPN is up.

## Who to contact

- Manager — week-one schedule, team norms, first ticket.
- People Ops / Mira Okonkwo — benefits, PTO questions, HubNorth access.
- IT via `#it-help` or ForgeDesk — hardware, VPN, account lockouts.
- Buddy (assigned in HubNorth) — informal questions and cafeteria tours.
- Security inbox `security@northwind-robotics.example` — lost laptop, phish,
  suspected account compromise. Do not use Slack DMs for security incidents.

Boulder front desk: +1-303-555-0140. Austin depot: +1-512-555-0198.

## Required training (week one)

Complete these courses in HubNorth Learning before the end of day five:

1. **Security Essentials** (45 min) — passwords, MFA, data classification.
2. **Fleet Floor Safety** (30 min) — required even for non-field roles;
   covers Robot exclusion zones and e-stop etiquette on customer sites.
3. **Code of Conduct** (20 min).
4. **NorthVPN & Secrets** (20 min) — engineers and anyone with production
   access; others skip.

Managers cannot approve PTO or production deploy rights until Security
Essentials and NorthVPN & Secrets show as complete in HubNorth.

## Internal tools map

- **HubNorth** — HR system of record: PTO, org chart, learning, pay stubs
  (amounts visible only to the employee; managers see status, not figures).
- **ForgeDesk** — IT and facilities ticketing.
- **ShipLog** — deploy and hardware shipment tracking; also used by Field Ops
  for robot unit serials.
- **Fleet OS Console** — customer and staging fleet control (VPN required).
- **Slack** — day-to-day chat; default channels `#general`, `#it-help`,
  `#people-help`, `#deploys`, `#oncall`.
- **PagerDuty** — incident paging for Platform and Firmware on-call.

Bookmark HubNorth and ForgeDesk on day one; everything else flows from those
two plus Slack. Ask your buddy before requesting extra SaaS tools — Shadow
IT gets revoked at the weekly access review Priya Natarajan chairs.
