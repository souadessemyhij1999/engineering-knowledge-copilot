---
doc_no: TS-EOL-012
title: Test Specification - End-of-Line Test E-Drive ED-150 / ED-210
revision: B
status: current
effective: 2026-01-12
owner: Test Engineering
classification: internal
roles: [quality, engineering, maintenance]
type: test specification
---
## 1 Scope

This specification defines the electrical and functional end-of-line (EOL) tests that every e-drive unit must pass before shipment.

## 2 Electrical safety tests

| Test | Condition | Limit |
|---|---|---|
| Insulation resistance phase to housing | 1000 V DC, 60 s | at least 100 megohm |
| Dielectric strength (hipot) | 2500 V AC, 1 s | leakage current max 5 mA |
| Protective earth resistance | 10 A | max 100 milliohm |

## 3 Functional tests

| Test | Condition | Limit |
|---|---|---|
| No-load speed run | 3000 rpm, 30 s | phase current max 12 A |
| Noise and vibration | run-up 0 to 12000 rpm | order spectrum within master curve +3 dB |
| Resolver offset | at standstill | within +/- 0.5 degrees electrical |
| Oil temperature sensor plausibility | ambient | within +/- 3 degrees C of ambient |

## 4 Retest rules

A unit that fails an electrical safety test must not be retested immediately. It is sent to the analysis station. A unit that fails a functional test may be retested once. If it fails again, it goes to the analysis station.

## 5 Data

All measured values are stored with the serial number for 15 years.

## 6 Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2025-02-03 | First issue |
| B | 2026-01-12 | Hipot voltage 2000 -> 2500 V AC |
