# Spooder E2E Test Infrastructure & Specification Document

## Executive Summary
This document defines the 4-tier requirement-driven End-to-End (E2E) testing framework for the Spooder Hexapod Web Dashboard and Gait Engine. The test suite (`test_suite.py`) provides automated verification across feature coverage, boundary conditions, cross-feature interaction, and complete user workflow scenarios.

---

## 1. Testing Methodology
The test suite is structured around a 4-tier requirement-driven validation model:

1. **Tier 1: Feature Coverage**
   - Validates individual core functional requirements against specification contracts.
   - Verifies Crouch-Walk baseline femur offset (-45°), coxa sweep zero reference, slider range math (-45 to +45), Crouch ON/OFF toggle dynamic sync, and Motion Profile generators.

2. **Tier 2: Boundary & Corner Cases**
   - Stresses extreme inputs, out-of-bounds slider values, invalid data types, and rapid toggle/command bursts.
   - Ensures clamping logic and error handling prevent task crashes or state corruption.

3. **Tier 3: Cross-Feature Combinations**
   - Validates concurrent feature execution and state transitions.
   - Verifies gait engine behavior during live posture adjustments, motion profile switching during active posture animations, and mutual exclusion interlocks (`stop_all_motions()`).

4. **Tier 4: Real-World Scenarios**
   - Simulates complete end-to-end user session workflows and multi-client WebSocket state synchronization broadcasts.

---

## 2. Test Cases Inventory

### Tier 1: Feature Coverage (7 Test Cases)
| Test Case ID | Test Name | Target Requirement | Description |
|---|---|---|---|
| T1-01 | `test_01_crouch_walk_gait_baseline_femur` | R1 Crouch-Walk Gait Engine | Verifies neutral femur baseline is -45° (`90 - 45 + int(lift * femur_dir)`) across all 6 legs and 6 directions. |
| T1-02 | `test_02_coxa_sweep_range_and_zero_reference` | R1 Coxa Sweep Range | Confirms coxa sweep remains centered at 0° (-45° to +45°) and zero reference is invariant. |
| T1-03 | `test_03_crouch_slider_ui_markup_contract` | R2 UI Markup Contract | Inspects `index.html` and `app.js` contracts for `#crouch-toggle` and `#slider-crouch`. |
| T1-04 | `test_04_crouch_slider_api_mechanics_negative_range` | R2 Negative Slider Range | Verifies negative slider values (0 to -45) lower coxas and femurs linearly (0° down to -45°). |
| T1-05 | `test_05_crouch_slider_api_mechanics_positive_range` | R2 Positive Slider Range | Verifies positive slider values (0 to +45) spin coxas positive (0° up to +45°) while femurs move toward -45°. |
| T1-06 | `test_06_crouch_toggle_dynamic_sync` | R2 Crouch Toggle Dynamic Sync | Confirms Crouch ON snaps slider/targets to -45° and Crouch OFF snaps to 0°. |
| T1-07 | `test_07_motion_profiles_interpolation` | R2 Motion Profile Generator | Tests trajectory interpolation for Trapezoidal, S-Curve, Sinusoidal, and Instant profiles. |

### Tier 2: Boundary & Corner Cases (5 Test Cases)
| Test Case ID | Test Name | Target Requirement | Description |
|---|---|---|---|
| T2-01 | `test_01_slider_boundary_values_exact` | Boundary Values (-45, 0, +45) | Asserts exact joint target outputs at slider boundaries -45, 0, and +45. |
| T2-02 | `test_02_slider_out_of_bounds_clamping` | Input Range Clamping | Confirms slider values < -45 or > +45 are clamped strictly within [-45, +45]. |
| T2-03 | `test_03_slider_invalid_data_type_handling` | Error & Type Robustness | Tests handling of `None`, empty string, non-numeric strings, and invalid payloads. |
| T2-04 | `test_04_rapid_crouch_toggle_switching` | Rapid Command Stress | Simulates 50 rapid toggle switches to verify stability and absence of race conditions. |
| T2-05 | `test_05_rapid_gait_and_pose_commands` | Command Interruption Stress | Rapidly alternates gait, crouch, and pose commands to verify interlock behavior. |

### Tier 3: Cross-Feature Combinations (3 Test Cases)
| Test Case ID | Test Name | Target Requirement | Description |
|---|---|---|---|
| T3-01 | `test_01_gait_execution_during_posture_slider_movement` | Gait + Slider Interaction | Verifies gait loop calculates correct joint offsets while crouch posture is adjusted live. |
| T3-02 | `test_02_motion_profile_change_during_active_pose_animation` | Profile Switching | Confirms dynamic switching of motion profiles mid-animation handles scale update cleanly. |
| T3-03 | `test_03_sweep_and_crouch_interlock` | Feature Interlock | Confirms `stop_all_motions()` stops active leg/global sweeps before starting crouch posture. |

### Tier 4: Real-World Scenarios (2 Test Cases)
| Test Case ID | Test Name | Target Requirement | Description |
|---|---|---|---|
| T4-01 | `test_01_complete_e2e_workflow` | End-to-End User Session | Simulates an entire session from connection -> profile selection -> crouch slider -> gait run -> stop -> center. |
| T4-02 | `test_02_multiclient_broadcast_sync` | WebSocket Broadcast | Verifies multiple connected WebSocket clients receive state updates when any client modifies posture. |

---

## 3. Feature Coverage Matrix

| Feature / Requirement | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|:---:|:---:|:---:|:---:|
| **R1: Crouch Walk Baseline (-45° Femur)** | ✅ T1-01 | - | ✅ T3-01 | ✅ T4-01 |
| **R1: Coxa Sweep Range (-45° to +45°)** | ✅ T1-02 | - | - | ✅ T4-01 |
| **R2: Slider Range Mechanics (0..-45 & 0..+45)** | ✅ T1-04, T1-05 | ✅ T2-01 | - | ✅ T4-01 |
| **R2: Out-of-Bounds & Type Clamping** | - | ✅ T2-02, T2-03 | - | - |
| **R2: Crouch ON/OFF Dynamic Sync** | ✅ T1-06 | ✅ T2-04 | - | ✅ T4-01 |
| **R2: UI Contract & Markup** | ✅ T1-03 | - | - | - |
| **Motion Profile Generator (Smoothing)** | ✅ T1-07 | - | ✅ T3-02 | ✅ T4-01 |
| **Interlock & Motion Cancellation** | - | ✅ T2-05 | ✅ T3-03 | ✅ T4-01 |
| **WebSocket Multi-Client Broadcast** | - | - | - | ✅ T4-02 |

---

## 4. Test Suite Execution Guide

### Command
```bash
python3 test_suite.py
```

### Exit Codes
- `0`: All 17 tests executed successfully with zero errors or failures.
- `1`: One or more tests failed or raised unhandled exceptions.
