# Handoff Report — Challenger M3-1

## 1. Observation

### 1.1 Initial Phase 1 Pass Rate Verification
- **Command**: `python3 test_suite.py` executed in `/home/smeer/Downloads/Spooder/web_dashboard`.
- **Result**:
  ```text
  Ran 17 tests in 0.107s
  OK
  SUMMARY RESULTS BY TIER:
    Tier 1: Feature Coverage            - 7 Test Cases Passed
    Tier 2: Boundary & Corner Cases     - 5 Test Cases Passed
    Tier 3: Cross-Feature Combinations  - 3 Test Cases Passed
    Tier 4: Real-World Scenarios        - 2 Test Cases Passed
  Total Tests Run: 17
  Errors: 0, Failures: 0
  ```

### 1.2 White-Box Inspection Findings in `server.py`

#### Finding A: Unhandled `ValueError` / `TypeError` on Non-Numeric Crouch Offsets (`server.py:515-516`)
- **Code**:
  ```python
  515: if raw_offset is not None:
  516:     offset = int(raw_offset)
  ```
- **Observed Behavior**:
  Passing `"abc"`, `"12.5"`, `""`, or a list `[1, 2]` causes `int(raw_offset)` to raise `ValueError` or `TypeError`.
  Because `handler` in `server.py` does not wrap message parsing or `set_crouch` in a `try...except` block, the exception bubbles up and terminates the client handler loop.

#### Finding B: Broken Exception Handler Exception Module Import (`server.py:569`)
- **Code**:
  ```python
  569: except websockets.exceptions.ConnectionClosed:
  ```
- **Observed Behavior**:
  `server.py` imports `websockets` via `import websockets`. Under modern `websockets` (e.g. Python 3.12 / websockets 14+), `websockets.exceptions` is not an attribute of `websockets` unless explicitly imported (`from websockets.exceptions import ConnectionClosed` or `import websockets.exceptions`).
  When any unhandled exception occurs in `handler()`, Python executes line 569 and raises:
  ```text
  AttributeError: module 'websockets' has no attribute 'exceptions'
  ```
  This causes the exception handler itself to crash.

#### Finding C: Unhandled `json.JSONDecodeError` on Malformed Payloads (`server.py:438`)
- **Code**:
  ```python
  438: data = json.loads(message)
  ```
- **Observed Behavior**:
  Sending invalid or truncated JSON (e.g., `'{"type": "set_crouch", "'`) causes `json.loads` to raise `json.JSONDecodeError`. No try/except block exists inside the `async for message in websocket:` loop, crashing the connection.

#### Finding D: `IndexError` on Invalid Leg Index in `center_leg` and `set_leg_sweep` (`server.py:542-543, 549`)
- **Code**:
  ```python
  542: elif cmd == "center_leg":
  543:     leg = int(data["leg"])
  544:     coxa_ch = LEG_COXA_CHANNELS[leg]
  ```
- **Observed Behavior**:
  If `data["leg"]` is `10`, `-10`, or `99`, `LEG_COXA_CHANNELS[leg]` raises `IndexError: list index out of range`, terminating the client connection.

#### Finding E: Positive Crouch Slider (+30) Reverses Femur Baseline in `run_gait` (`server.py:328-330`)
- **Code**:
  ```python
  328: femur_baseline = self.crouch_offset if (self.crouch_active or self.crouch_offset != 0) else 0
  329: if self.crouch_active and femur_baseline == 0:
  330:     femur_baseline = -45
  ```
- **Observed Behavior**:
  For positive crouch slider (+30), `set_crouch` sets `self.crouch_offset = 30` (while setting posture target femurs to `-30`).
  In `run_gait`, `femur_baseline` evaluates to `self.crouch_offset` which is `+30`.
  Consequently, during crouch walk with a positive slider value, femurs are elevated UP by `+30°` instead of crouching DOWN by `-30°`.

#### Finding F: Positive Crouch Slider (+30) Reverses Femur Target on Gait Deactivation (`server.py:459-464`)
- **Code**:
  ```python
  459: if self.crouch_active:
  460:     crouch_baseline = self.crouch_offset if self.crouch_offset != 0 else -45
  461:     targets = {}
  462:     for leg in range(6):
  463:         targets[LEG_COXA_CHANNELS[leg]] = 0
  464:         targets[LEG_FEMUR_CHANNELS[leg]] = crouch_baseline
  ```
- **Observed Behavior**:
  Deactivating gait (`set_gait` with `active: false`) when `crouch_active` is True and `crouch_offset = 30` sets `crouch_baseline = +30`.
  Coxa targets are zeroed out (wiping coxa posture), and femur targets are set to `+30` (pushing femurs up instead of down to `-30`).

#### Finding G: Motion Animation Task Collision and Race Condition (`server.py:291-296`)
- **Code**:
  ```python
  291: def stop_all_motions(self):
  292:     self.gait_active = False
  293:     self.sweep_active = False
  294:     self.pose_active = False
  295:     for i in range(6):
  296:         self.leg_sweeps[i] = False
  ```
- **Observed Behavior**:
  `stop_all_motions()` only flips flag booleans. It does not reference, cancel, or await active `asyncio.Task` handles created by `animate_motion_targets()`, `animate_pose()`, or `run_gait()`.
  When posture toggle or crouch commands are sent rapidly back-to-back or during gait, multiple `animate_motion_targets()` tasks run concurrently in the background, writing conflicting values to `self.servo_offsets` on every frame step.

---

## 2. Logic Chain

1. **Input Validation Defect**: `server.py` relies on `int(raw_offset)` and `int(data["leg"])` without type guard checks or `try...except` handlers.
2. **Cascade Failure**: Because `handler()` lacks per-message exception isolation and line 569 references invalid module attribute `websockets.exceptions`, any unexpected client payload triggers an unhandled `ValueError`, `TypeError`, `JSONDecodeError`, or `IndexError`, which then crashes the WebSocket connection handler with an `AttributeError`.
3. **Mathematical Inconsistency**: In `set_crouch`, positive slider values (+30) invert the femur direction (`femur_target = -offset = -30`). However, `run_gait` and `set_gait` (deactivation) read `self.crouch_offset` (+30) directly without applying the negation for femurs, causing positive crouch slider values to produce inverted femur movement (+30 instead of -30) during gait execution and gait deactivation.
4. **Task Concurrency Flaw**: `animate_motion_targets()` runs asynchronously over `max_duration` (up to ~0.3-0.5s). Because `stop_all_motions()` does not cancel existing animation tasks, rapidly issuing posture updates creates overlapping background animation loops that collide over `self.servo_offsets` and servo output channels.

---

## 3. Caveats

- **Hardware vs Simulation**: All empirical tests were conducted in simulation mode (no PCA9685/Serial hardware attached). I2C write errors are caught inside `set_angle()`, so simulation test results accurately reflect state logic.
- **WebSocket Library Versions**: `websockets.exceptions.ConnectionClosed` import issue depends on `websockets` version in the Python environment (present in legacy versions, changed in newer versions).

---

## 4. Conclusion

- **Phase 1 Baseline**: Tiers 1-4 pass 100% (17 out of 17 tests passed).
- **Vulnerabilities Identified**:
  1. Unhandled exception crash on non-numeric offset strings (`ValueError`/`TypeError`).
  2. Malformed JSON payload WebSocket handler crash (`JSONDecodeError` + `AttributeError`).
  3. Out-of-bounds leg index crash (`IndexError`).
  4. Inverted femur baseline for positive crouch slider (+30) in gait loop and gait deactivation.
  5. Concurrency race condition on rapid posture toggles due to unmanaged background `animate_motion_targets` tasks.
- **Actionable Remediation**:
  - Add input sanitization (`try...except (ValueError, TypeError)`) and range checks for `offset` and `leg` parameters.
  - Fix `websockets` exception catch statement to `websockets.ConnectionClosed`.
  - In `run_gait` and `set_gait`, compute femur crouch baseline as `-crouch_offset` when `crouch_offset > 0`.
  - Store and cancel active `self._animation_task` in `stop_all_motions()`.

---

## 5. Verification Method

To independently verify these empirical results and test proposals:

1. **Run 5-Tier Unit Test Suite**:
   ```bash
   python3 test_suite.py
   ```
   *Expected output*: 23 tests run across Tiers 1 to 5.

2. **Run White-Box Backend Adversarial Harness**:
   ```bash
   python3 .agents/challenger_m3_1/backend_adversarial_harness.py
   ```
   *Expected output*: Runs 9 adversarial stress test scenarios against `server.py` and reports specific exposed vulnerabilities and logic bugs.

3. **Inspect Key Files**:
   - `test_suite.py`: Lines 498-570 for `Tier5AdversarialWhiteBoxTests`.
   - `.agents/challenger_m3_1/backend_adversarial_harness.py`: For full stress harness code.
