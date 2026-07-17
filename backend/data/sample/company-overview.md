# Northwind Robotics — Company Overview

## What we do

Northwind Robotics designs and builds warehouse automation robots for mid-size
distribution centers. Founded in 2014 in Boulder, Colorado by Marcus Chen and
Priya Natarajan, the company ships autonomous mobile robots (AMRs) and the
software that orchestrates them on the warehouse floor. Customers are typically
3PLs and regional retailers operating facilities between 50,000 and 400,000
square feet. Northwind does not sell industrial arms or outdoor AGVs; the
product line stays inside the four walls of a warehouse.

## Mission

Move goods from receiving to ship dock with fewer stops and fewer walks. The
stated mission is: "Every pallet, every aisle, on schedule." Practically that
means reducing average pick-path time by deploying AMRs that ferry totes to
stationary pickers rather than sending people to every bin. Internal OKRs track
fleet uptime (target ≥ 97%) and mean time to recover a stuck robot
(target ≤ 12 minutes).

## Product lines

Three shipping products sit under the "Northwind Floor" umbrella:

- **Warehouse Pilot** — the primary AMR. Carries up to 180 kg, max speed
  1.4 m/s, navigates with lidar + floor markers. Units ship as WP-200 or
  WP-400 depending on battery capacity.
- **ShelfSorter** — a conveyor-integrated sorter that receives totes from
  Warehouse Pilot robots and routes them to outbound lanes. Controlled by the
  same Northwind Fleet OS as the AMRs.
- **DockLink** — a dock-door sensor kit that publishes door status and trailer
  presence into Fleet OS so Pilot robots queue correctly at staging.

Fleet OS, the on-prem control plane, is required for all three products and
runs on a customer-owned cluster of three Linux hosts.

## Org structure

Marcus Chen is CEO. Priya Natarajan is CTO and owns Engineering, Fleet
Software, and Field Ops tooling. Mira Okonkwo leads People & Ops. Lucas Berg
heads Customer Success. Engineering is split into Platform (Fleet OS), Robot
Firmware, and Deploy Tools — about 85 people total company-wide as of Q1 2026.
Field Ops and Support report to Customer Success and staff the on-call
rotations described in the deploy runbook.

## Offices

Headquarters is at 1400 Walnut Street, Boulder, CO. A regional office in
Austin, TX (Suite 400, 900 Congress Ave) houses Customer Success and a spare
parts depot. A small R&D satellite in Eindhoven, Netherlands (High Tech Campus
12) focuses on lidar perception. Most Platform engineers are Boulder-based;
Firmware splits Boulder/Eindhoven. Remote work is allowed up to three days per
week for roles marked "flex" in HubNorth.
