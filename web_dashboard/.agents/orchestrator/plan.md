# Execution Plan: Spooder Crouch-Walk & Linear Crouch Slider

## Overview
Decomposition into 3 core implementation milestones and 1 parallel E2E testing track.

## Milestones & Iterations

### Track 1: E2E Testing Track
- Subagent: E2E Test Architect
- Objective: Create requirement-driven test infrastructure (`test_suite.py` or similar runner), covering:
  - Tier 1: Feature Coverage (Crouch walk baseline, linear slider ranges, toggle dynamic sync)
  - Tier 2: Boundary & Corner cases (-45, 0, +45 limits, out of bounds, toggle rapid switches)
  - Tier 3: Cross-Feature Combinations (Gait execution while moving crouch slider, profile transitions)
  - Tier 4: Real-World Scenarios (Full E2E user workflow sequence)
- Artifact: `TEST_INFRA.md` & `TEST_READY.md`

### Milestone 1: Crouch-Walk Gait Engine (R1)
- Scope: Backend gait logic in `server.py`.
- Objectives:
  1. Modify `run_gait()` in `server.py` so crouch mode / crouch slider offset uses `-45°` neutral femur baseline instead of `0°`.
  2. Femur lift formula: `femur_angle = 90 - 45 + int(lift * femur_dir)`.
  3. Coxa sweep range centered at 0° (-45° to +45°).
- Iteration Cycle: Explorer -> Worker -> Reviewer -> Challenger -> Forensic Auditor -> Gate.

### Milestone 2: Linear Crouch Slider & Dynamic Twist (R2)
- Scope: `public/index.html`, `public/app.js`, `server.py`.
- Objectives:
  1. Add `#slider-crouch` under Crouch button in `index.html` (-45 to +45, default 0).
  2. Sync `crouch-toggle` in `app.js` and `server.py` with Crouch slider (Crouch ON -> -45, Crouch OFF -> 0).
  3. Negative range (0 to -45): All 12 joints adjust linearly from 0° down to -45°.
  4. Positive range (0 to +45): Coxas spin positive linearly 0° to +45°; Femurs move toward -45°.
  5. Smooth motion profiles (Trapezoidal, S-Curve, Sinusoidal) preserved across all transitions.
- Iteration Cycle: Explorer -> Worker -> Reviewer -> Challenger -> Forensic Auditor -> Gate.

### Milestone 3: Final E2E Test & Coverage Hardening
- Phase 1: Run complete Tier 1-4 E2E test suite.
- Phase 2: Tier 5 White-box Adversarial Coverage Hardening (Challenger -> Worker -> Reviewer -> Auditor).
