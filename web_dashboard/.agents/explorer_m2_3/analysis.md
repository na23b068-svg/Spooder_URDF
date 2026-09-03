# Analysis: Crouch Posture Math & Motion Profile Integration (`server.py`)

## Executive Summary
This report presents the read-only architectural and mathematical investigation of the backend crouch posture handler (`set_crouch`) and motion profile generator (`animate_motion_targets`) in `server.py` for Milestone 2.

---

## 1. Codebase Component Inspection

### 1.1 `server.py` - WebSocket Handler (`set_crouch`)
- **Location**: `server.py` lines 505–527
- **Current Behavior**:
  When receiving `{"type": "set_crouch", "active": true, "offset": v}`, the server stops all current motion routines, sets `self.crouch_active = active`, updates `self.crouch_offset = offset`, and currently constructs targets as:
  `targets = {ch: offset for ch in range(12)}`
- **Issue Identified**:
  Setting all 12 channels directly to `offset` assumes negative range symmetry (`v <= 0`), but fails for the positive twist range (`v > 0`). When `v > 0`, Coxas must spin positive (`+v`), whereas Femurs must lower to `-v` (toward -45°).

### 1.2 `server.py` - Motion Profile Animator (`animate_motion_targets`)
- **Location**: `server.py` lines 230–285
- **Behavior**:
  - Accepts `target_offsets_dict` (mapping channel indices to target offset angles).
  - Inspects `self.active_motion_profile` ("Trapezoidal", "S-Curve", "Sinusoidal", or "Instant") and `self.pose_speed` multiplier.
  - Instantiates `MotionProfileGenerator` for each servo from its current position `self.servo_offsets[ch]` to `target_off`.
  - Synchronizes durations so all servos complete their profile move concurrently.
  - Iterates at `dt = 0.015`s, calculating smooth position steps, writing hardware commands (`send_command(ch, 90 + current_off)`), and broadcasting state updates (`broadcast_state()`).

---

## 2. Mathematical Formulation for Slider Input $v \in [-45, +45]$

Given slider input $v$ clamped to range $[-45, +45]$:

### 2.1 Negative Range ($v \le 0$, Range $0^\circ \to -45^\circ$)
- **Coxa Target Offset**: $v$ (linearly from $0^\circ$ down to $-45^\circ$)
- **Femur Target Offset**: $v$ (linearly from $0^\circ$ down to $-45^\circ$)

### 2.2 Positive Range ($v > 0$, Range $0^\circ \to +45^\circ$)
- **Coxa Target Offset**: $v$ (linearly from $0^\circ$ up to $+45^\circ$)
- **Femur Target Offset**: $-v$ (linearly from $0^\circ$ down to $-45^\circ$)

### 2.3 Unified Piecewise & Closed-Form Offsets

$$\text{coxa\_offset}(v) = v$$

$$\text{femur\_offset}(v) = \begin{cases} v & \text{if } v \le 0 \\ -v & \text{if } v > 0 \end{cases} = -\vert v \vert$$

---

## 3. Joint Channel Target Mapping

Using channel layout constants from `server.py` (lines 12–13):
- `LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10]`
- `LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4]`

Target dictionary structure for `animate_motion_targets()`:
```python
offset = max(-45, min(45, int(data.get("offset", -45))))
coxa_off = offset
femur_off = offset if offset <= 0 else -offset

targets = {}
for ch in LEG_COXA_CHANNELS:
    targets[ch] = coxa_off
for ch in LEG_FEMUR_CHANNELS:
    targets[ch] = femur_off
```

---

## 4. Proposed Code Snippet for Implementation

```python
# In server.py under elif cmd == "set_crouch":
elif cmd == "set_crouch":
    self.stop_all_motions()
    active = data.get("active", False)
    self.crouch_active = active
    if active:
        offset = int(data.get("offset", -45))
        offset = max(-45, min(45, offset))
        self.crouch_offset = offset
        
        coxa_offset = offset
        femur_offset = offset if offset <= 0 else -offset
        
        targets = {}
        for ch in LEG_COXA_CHANNELS:
            targets[ch] = coxa_offset
        for ch in LEG_FEMUR_CHANNELS:
            targets[ch] = femur_offset
            
        asyncio.create_task(self.animate_motion_targets(targets))
    else:
        self.crouch_offset = 0
        coxa_targets = {LEG_COXA_CHANNELS[leg]: 0 for leg in range(6)}
        femur_targets = {LEG_FEMUR_CHANNELS[leg]: 0 for leg in range(6)}
        
        async def _exit_crouch():
            await self.animate_motion_targets(coxa_targets)
            await asyncio.sleep(0.05)
            await self.animate_motion_targets(femur_targets)
            
        asyncio.create_task(_exit_crouch())
```

---

## 5. Verification Plan
1. Run E2E test suite `python3 test_suite.py` to verify all 17 tests pass.
2. Specifically test `test_04_crouch_slider_api_mechanics_negative_range` and `test_05_crouch_slider_api_mechanics_positive_range`.
3. Verify that changing active motion profile to "S-Curve", "Sinusoidal", or "Trapezoidal" results in smooth trajectory updates via `animate_motion_targets()`.
