---
doc_no: WI-PNT-005
title: Leak Test of Gearbox Housing
revision: D
status: current
effective: 2026-06-01
owner: Quality Engineering
classification: internal
roles: [operator, maintenance, quality, engineering]
type: work instruction
---
## 1 Purpose

Every assembled gearbox housing is leak tested with the pressure decay method on leak test bench LT-2 before it goes to the end-of-line test.

## 2 Preconditions

The leak test may only be started after the sealant has cured for at least 30 minutes (see WI-ASM-014). The housing temperature must be between 15 and 35 degrees C. Warm parts give false results.

## 3 Daily master part check

At the start of every shift, test the master part with the calibrated test leak of 1.5 cm3/min. The bench must show a leak rate between 1.3 and 1.7 cm3/min. If not, the bench is blocked and maintenance has to be called. Record the result in the MES.

## 4 Test parameters

| Parameter | Value |
|---|---|
| Test medium | Dry compressed air |
| Test pressure | 500 mbar (0.5 bar) |
| Fill time | 5 s |
| Settle time | 10 s |
| Measuring time | 8 s |
| Reject limit | 2.0 cm3/min |

## 5 Procedure

1. Place the housing on the fixture and close the sealing adapters.
2. Start the test with the two-hand switch.
3. Green light: the part passed. Remove it and put it on the conveyor to the end-of-line test.
4. Red light: the part failed. Check the sealing adapters for damage or dirt and test the part once more.
5. If the part fails a second time, attach a red tag, put it in the quarantine area and create a nonconformity report (QM-NCR-001). Do not test it a third time.

## 6 Records

The bench saves pressure curve and leak rate of every part with the serial number in the MES.

## 7 Revision history

| Rev | Date | Change |
|---|---|---|
| C | 2025-03-10 | Settle time 8 -> 10 s |
| D | 2026-06-01 | Cure time before test 20 -> 30 min (ECN-2026-044) |
