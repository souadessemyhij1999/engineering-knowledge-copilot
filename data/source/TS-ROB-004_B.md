---
doc_no: TS-ROB-004
title: Troubleshooting Guide - Robot Dispensing Cell D2
revision: B
status: current
effective: 2026-03-02
owner: Maintenance
classification: internal
roles: [maintenance, engineering]
type: troubleshooting guide
---
## 1 Scope

This guide helps maintenance technicians to find the cause of the most common alarms of the sealant dispensing cell D2 on line L2. Before entering the cell, apply LOTO according to MP-LOTO-002.

## 2 Alarm codes

| Code | Meaning | Likely cause | Action |
|---|---|---|---|
| E-101 | Sealant pressure low | Cartridge empty or air in the line | Change cartridge, vent the dosing pump |
| E-102 | Sealant pressure high | Nozzle blocked | Replace nozzle 1.2 mm, do not clean with wire |
| E-205 | Vision: bead interrupted | Air bubble, nozzle too far from the part | Check nozzle height 1.5 mm, vent the system |
| E-207 | Vision: bead too wide | Robot speed too low, nozzle worn | Check speed 120 mm/s, replace nozzle |
| E-310 | Robot collision detected | Part not seated in fixture | Check fixture pins, reference the robot |
| E-412 | Safety door open | Door switch faulty or door not closed | Check door switch, never bridge it |

## 3 Venting the dosing pump

1. Put the cell in manual mode.
2. Hold the purge container under the nozzle.
3. Press PURGE on the HMI for at least 20 s until the sealant flows without bubbles.
4. Wipe the nozzle and run one test bead on a test plate.

## 4 Escalation

If the same alarm occurs more than 3 times in one shift, open a maintenance ticket and inform the process engineer. Repeated E-205 alarms were one of the causes in 8D-2026-017.

## 5 Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2025-05-19 | First issue |
| B | 2026-03-02 | E-205 / E-207 vision alarms added |
