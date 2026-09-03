# Analysis Report: Crouch-Walk Gait Engine (Milestone 1)

## Executive Summary
This report analyzes the gait execution engine in `server.py` and details the exact code modifications required to implement the Crouch-Walk Gait Engine (Milestone 1). When Crouch mode is active (or Crouch slider is set), all gait patterns (Forward, Backward, Spin CW/CCW, Turn Left/Right) will execute with a neutral femur baseline of `-45°` (raw angle `45°`) instead of `0°` (raw angle `90°`), while coxas maintain their zero reference at `0°` (raw angle `90°`) and sweep range of `-45°` to `+45°`.

---

## 1. Investigation Findings

### 1.1 State Management in `SpooderServer`
- **File & Line**: `server.py:139-156`
- **Observation**: `SpooderServer.__init__` tracks gait parameters (`self.gait_active`, `self.gait_speed`, `self.gait_sweep`, `self.gait_lift`, `self.gait_direction`), but does **not** maintain persistent state for `crouch_active` or `crouch_offset`.
- **File & Line**: `server.py:491-508`
- **Observation**: In `cmd == "set_crouch"`, when `active` is set to `True`, the server executes an animation to `-45` for all 12 channels (`targets = {ch: -45 for ch in range(12)}`), but does not save `self.crouch_active` on `self`. Consequently, when `run_gait()` is launched, it has no reference state to determine whether Crouch mode is active.

### 1.2 Current Gait Engine Logic (`run_gait()`)
- **File & Line**: `server.py:308-348`
- **Current Coxa Angle Calculation**:
  ```python
  coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
  sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier
  coxa_angle = 90 + int(sweep)
  self.servo_offsets[coxa_ch] = int(sweep)
  ```
  - Coxas sweep around zero reference `90°` (0° offset) with amplitude `self.gait_sweep` (default 30°, max 45°).
- **Current Femur Angle Calculation**:
  ```python
  lift = max(0.0, math.sin(theta_leg)) * self.gait_lift
  femur_dir = FEMUR_LIFT_DIRS[leg]
  femur_angle = 90 + int(lift * femur_dir)
  self.servo_offsets[femur_ch] = int(lift * femur_dir)
  ```
  - `FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]` (Left legs: +1, Right legs: -1).
  - The neutral stance baseline femur angle is currently hardcoded to `90°` (offset `0°`).

### 1.3 Gait Pattern Coverage Analysis
- `get_coxa_multiplier(leg, direction)` (`server.py:295-306`) handles all 6 directional gait patterns:
  - `"Forward"`: Right side `-1.0`, Left side `+1.0`
  - `"Backward"`: Right side `+1.0`, Left side `-1.0`
  - `"Turn Left"`, `"Spin Anti-Clockwise"`, `"Spin Anti-Clockwise (CCW)"`: All legs `-1.0`
  - `"Turn Right"`, `"Spin Clockwise"`, `"Spin Clockwise (CW)"`: All legs `+1.0`
- Femur lift calculation is independent of gait direction. In all patterns, `lift` applies during swing phase (`sin(theta_leg) > 0`).

---

## 2. Proposed Code Modifications for `server.py`

### Modification 1: Add Crouch State Tracking in `SpooderServer.__init__`
**Target Location**: `server.py:146` (Inside `__init__`)

```python
# State
self.active_motion_profile = "Trapezoidal"
self.pose_speed = 1.0
self.crouch_active = False
self.crouch_offset = 0
self.gait_active = False
```

### Modification 2: Update `set_crouch` Command Handler
**Target Location**: `server.py:491-509`

```python
elif cmd == "set_crouch":
    self.stop_all_motions()
    active = data.get("active", False)
    self.crouch_active = active
    self.crouch_offset = -45 if active else 0
    if active:
        # OFF to ON: Smooth motion profile ramp to -45° for all 12 servos
        targets = {ch: -45 for ch in range(12)}
        asyncio.create_task(self.animate_motion_targets(targets))
    else:
        # Exit Crouch: Rotate all Coxas back to 0° first, then extend Femurs to 0° second
        coxa_targets = {LEG_COXA_CHANNELS[leg]: 0 for leg in range(6)}
        femur_targets = {LEG_FEMUR_CHANNELS[leg]: 0 for leg in range(6)}
        
        async def _exit_crouch():
            await self.animate_motion_targets(coxa_targets)
            await asyncio.sleep(0.05)
            await self.animate_motion_targets(femur_targets)
            
        asyncio.create_task(_exit_crouch())
```

### Modification 3: Update `run_gait()` Femur Calculation
**Target Location**: `server.py:328-339`

```python
femur_baseline = -45 if (self.crouch_active or self.crouch_offset != 0) else 0

for leg in range(6):
    if leg in [0, 4, 2]:
        theta_leg = theta
    else:
        theta_leg = theta + math.pi
    
    coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
    lift = max(0.0, math.sin(theta_leg)) * self.gait_lift
    sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier
    femur_dir = FEMUR_LIFT_DIRS[leg]
    
    coxa_angle = 90 + int(sweep)
    femur_angle = 90 + femur_baseline + int(lift * femur_dir)
    
    coxa_ch = LEG_COXA_CHANNELS[leg]
    femur_ch = LEG_FEMUR_CHANNELS[leg]
    
    self.servo_offsets[coxa_ch] = int(sweep)
    self.servo_offsets[femur_ch] = femur_baseline + int(lift * femur_dir)

    self.send_command(coxa_ch, coxa_angle)
    self.send_command(femur_ch, femur_angle)
```

### Modification 4: Update `set_gait` Stop Gait Handling
**Target Location**: `server.py:445-449`

```python
if self.gait_active:
    asyncio.create_task(self.run_gait())
else:
    if self.crouch_active or self.crouch_offset != 0:
        targets = {ch: -45 for ch in range(12)}
        asyncio.create_task(self.animate_motion_targets(targets))
    else:
        self.center_all()
    await self.broadcast_state()
```

---

## 3. Mathematical Verification of Femur Angles

| Gait State | Crouch Mode | Lift Value | `femur_dir` (Left / Right) | `femur_angle` Formula | `femur_angle` Value | `servo_offset` |
|---|---|---|---|---|---|---|
| Stance (Ground) | Disabled (0°) | 0° | +1 / -1 | 90 + 0 + 0 | **90°** | **0** |
| Stance (Ground) | **Enabled (-45°)** | 0° | +1 / -1 | 90 - 45 + 0 | **45°** | **-45** |
| Peak Swing | Disabled (0°) | +30° | +1 (Left) | 90 + 0 + 30 | **120°** | **+30** |
| Peak Swing | Disabled (0°) | +30° | -1 (Right) | 90 + 0 - 30 | **60°** | **-30** |
| Peak Swing | **Enabled (-45°)** | +30° | +1 (Left) | 90 - 45 + 30 | **75°** | **-15** |
| Peak Swing | **Enabled (-45°)** | +30° | -1 (Right) | 90 - 45 - 30 | **15°** | **-75** |

- **Coxa Zero Reference**: `coxa_angle = 90 + int(sweep)`, center remains exactly `90°` (0° offset), sweep range `[-45°, +45°]`.
