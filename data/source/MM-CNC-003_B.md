---
doc_no: MM-CNC-003
title: Preventive Maintenance of Machining Centre MC-500
revision: B
status: current
effective: 2026-01-20
owner: Maintenance
classification: internal
roles: [maintenance, engineering]
type: maintenance manual
---
## 1 Scope

This manual lists the preventive maintenance tasks for the machining centres MC-500 (asset numbers MC-501 to MC-506). Before any work inside the machine, the machine must be locked out according to MP-LOTO-002.

## 2 Maintenance intervals

| Task | Interval | Responsible |
|---|---|---|
| Clean chip conveyor and coolant filter | weekly | operator |
| Check way lube oil level | weekly | operator |
| Check spindle drawbar clamping force | every 500 operating hours | maintenance |
| Change hydraulic oil (HLP 46, 40 l) | every 4000 operating hours | maintenance |
| Clean and inspect axis covers | every 1000 operating hours | maintenance |
| Geometry check (ballbar test) | every 6 months | maintenance |
| Replace coolant completely and clean tank | every 3 months | maintenance |

## 3 Spindle drawbar clamping force

The nominal clamping force of the HSK-A63 drawbar is 18 kN. Measure it with the clamping force gauge. If the force is below 15 kN, the disc springs must be replaced. Do not run the machine with a clamping force below 15 kN, the tool can be pulled out during heavy cuts.

## 4 Spindle warm-up

After a standstill of more than 8 hours, run warm-up program O9001. The program runs the spindle for 10 minutes in steps of 2000, 6000 and 10000 rpm. Without warm-up, thermal growth of the spindle can cause dimensional errors of up to 0.015 mm in the first parts.

## 5 Ballbar test

Run the ballbar test in the XY plane with radius 150 mm at feed 1000 mm/min. The circularity must be below 12 um. If it is higher, inform the machine supplier service.

## 6 Spare parts

| Part | Order number | Minimum stock |
|---|---|---|
| Disc spring set drawbar | MC5-SP-118 | 2 |
| Coolant filter cartridge | MC5-FL-020 | 6 |
| Way lube oil 5 l | LUB-068-5 | 4 |

## 7 Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2024-11-04 | First issue |
| B | 2026-01-20 | Coolant change interval 6 -> 3 months |
