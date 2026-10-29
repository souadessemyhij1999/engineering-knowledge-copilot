---
doc_no: WI-ASM-014
title: Gearbox Housing Assembly - Cover and Flange Bolting
revision: C
status: current
effective: 2026-06-01
owner: Production Engineering
classification: internal
roles: [operator, maintenance, quality, engineering]
type: work instruction
---
## 1 Purpose

This work instruction describes how the gearbox housing cover is sealed and bolted to the housing on assembly line L2. It applies to all e-drive variants ED-150 and ED-210.

## 2 Safety

Wear cut-resistant gloves when handling the housing cover. The flange edges are sharp. Wear nitrile gloves when working with the sealant (see HSE-POL-003). The EC screwdriver may only be used with the reaction arm fitted.

## 3 Tools and materials

| Item | Specification |
|---|---|
| EC screwdriver | Station S4, program P-14 |
| Sealant | Anaerobic flange sealant, type S-2 |
| Dispensing unit | Robot dispenser D2 with nozzle 1.2 mm |
| Torque analyser | For the shift start check |

## 4 Tightening torques

All torques are final torques. Tolerance is the value given in the table. Bolts with pre-applied threadlocker must not be reused (see ES-TOR-001).

| Joint | Thread | Torque | Tolerance |
|---|---|---|---|
| Housing cover bolts | M8 | 25 Nm | +/- 2.5 Nm |
| Flange bolts to motor housing | M10 | 45 Nm | +/- 4.5 Nm |
| Speed sensor bracket | M6 | 9 Nm | +/- 0.9 Nm |
| Oil drain plug | M14x1.5 | 30 Nm | +/- 3 Nm |

The M10 flange torque was raised from 40 Nm to 45 Nm with ECN-2026-044.

## 5 Procedure

1. Check the torque of the EC screwdriver with the torque analyser at the start of every shift. Record the result in the MES. If the measured value is outside the tolerance, do not start production and inform the shift leader.
2. Clean the flange surfaces with a lint-free cloth and cleaning agent C-1. The surfaces must be dry and free of oil.
3. Start the dispensing program. The sealant bead must be 3.0 mm +/- 0.5 mm wide and continuous, without gaps or interruptions.
4. Check the bead on the camera screen. If the vision check shows an interruption, remove the sealant completely and apply it again.
5. Fit the cover within 10 minutes of applying the sealant (open time). If the open time is exceeded, remove the sealant and start again at step 2.
6. Tighten the bolts in a cross pattern in two stages: stage 1 at 50 % of the final torque, stage 2 at 100 %.
7. Mark each bolt with the yellow paint pen after stage 2.
8. Let the sealant cure for at least 30 minutes before the leak test (WI-PNT-005).

## 6 Deviations

If a bolt cannot be tightened, the screwdriver reports an error or the cover does not sit flat, stop the line, place the unit in the red box and call the shift leader. Nonconforming parts are handled according to QM-NCR-001.

## 7 Records

The screwdriver sends torque and angle of every bolt to the MES. The operator confirms the visual bead check in the MES.

## 8 Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2024-09-02 | First issue |
| B | 2025-03-10 | Drain plug added |
| C | 2026-06-01 | M10 flange torque 40 -> 45 Nm, sealant bead 2.5 -> 3.0 mm, open time 15 -> 10 min, vision check added (ECN-2026-044, 8D-2026-017) |
