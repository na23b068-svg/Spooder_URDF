# Crouch-Walk Gait Engine Analysis Report (Milestone 1)

**Target Component**: Backend Gait Engine (`server.py`)  
**Investigator**: Explorer 2 (Milestone 1)  
**Date**: 2026-09-03  

---

## 1. Executive Summary

This report provides a detailed technical analysis of the gait engine in `server.py` and its interaction with the Crouch posture state. Currently, starting any gait pattern while the robot is crouched causes an immediate posture jump: the gait loop overwrites femur servo angles using a `0°` neutral baseline (`90°` servo position), ignoring the crouch state.

To ensure continuous tripod gait functions smoothly centered at a `-45°` neutral femur baseline, `server.py` requires:
1. Persistent crouch state tracking (`self.crouch_active` and `self.crouch_offset`) on the `SpooderServer` instance.
2. Modification of `run_gait()` to calculate femur angles using `femur_angle = 90 + femur_baseline + int(lift * femur_dir)` where `femur_baseline = -45` when crouched.
3. Preservation of Coxa zero-reference (`90°`) and sweep range (`-45°` to `+45°`) across all 6 directional gaits.
4. Smooth termination handling in `set_gait` so that stopping gait returns to the crouch baseline when crouched rather than calling `center_all()` (which resets to `0°`).

---

## 2. Investigation of Current `server.py` Implementation

### 2.1 Hardware and Channel Layout (`server.py:10-15`)
```python
LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10]
LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4]
FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]
```
- **Leg Mapping**:
  - `0`: Left Front (LF) — Coxa Ch `0`, Femur Ch `1`, `femur_dir = 1`
  - `1`: Left Middle (LM) — Coxa Ch `2`, Femur Ch `3`, `femur_dir = 1`
  - `2`: Left Back (LB) — Coxa Ch `11`, Femur Ch `5`, `femur_dir = 1`
  - `3`: Right Front (RF) — Coxa Ch `6`, Femur Ch `7`, `femur_dir = -1`
  - `4`: Right Middle (RM) — Coxa Ch `8`, Femur Ch `9`, `femur_dir = -1`
  - `5`: Right Back (RB) — Coxa Ch `10`, Femur Ch `4`, `femur_dir = -1`

### 2.2 Coxa Multipliers Across Gait Directions (`server.py:295-306`)
`get_coxa_multiplier(leg_index, direction)` handles all directional gaits:
- `"Forward"`: Left legs `+1.0`, Right legs `-1.0`
- `"Backward"`: Left legs `-1.0`, Right legs `+1.0`
- `"Turn Left"`, `"Spin Anti-Clockwise"`, `"Spin Anti-Clockwise (CCW)"`: All legs `-1.0`
- `"Turn Right"`, `"Spin Clockwise"`, `"Spin Clockwise (CW)"`: All legs `+1.0`

### 2.3 Existing `run_gait()` Loop (`server.py:308-347`)
```python
async def run_gait(self):
    t = 0.0
    last_time = time.time()
    while self.gait_active:
        ...
        omega = 2.0 * math.pi * self.gait_speed
        t += dt
        theta = (omega * t) % (2.0 * math.pi)
        
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
            femur_angle = 90 + int(lift * femur_dir)  # <-- Line 333: HARDCODED 90° BASELINE
            
            coxa_ch = LEG_COXA_CHANNELS[leg]
            femur_ch = LEG_FEMUR_CHANNELS[leg]
            
            self.servo_offsets[coxa_ch] = int(sweep)
            self.servo_offsets[femur_ch] = int(lift * femur_dir)  # <-- Line 339: HARDCODED 0 OFFSET BASELINE
```

### 2.4 Existing `set_crouch` and State Deficiency (`server.py:138-153`, `491-508`)
Currently:
1. `SpooderServer.__init__` does **not** define `self.crouch_active` or `self.crouch_offset`.
2. When `cmd == "set_crouch"` is called (`server.py:491`), `self.stop_all_motions()` is executed and servos are animated to `-45` offset. However, no flag is saved on `self`.
3. When `cmd == "set_gait"` is called while crouched:
   - `self.stop_all_motions()` is called.
   - `run_gait()` starts.
   - Line 333 sets `femur_angle = 90 + int(lift * femur_dir)`, which immediately forces the neutral stance to 90° (0° offset), causing the robot to jump out of crouch posture into full height standing stance!

---

## 3. Gait Pattern Loop Verification

All 6 directional gait patterns (Forward, Backward, Spin CW, Spin CCW, Turn Left, Turn Right) use the same tripod phase oscillation logic:
- **Tripod Group A**: Legs `0` (LF), `4` (RM), `2` (LB) — `theta_leg = theta`
- **Tripod Group B**: Legs `1` (LM), `3` (RF), `5` (RB) — `theta_leg = theta + pi`

### 3.1 Femur Lift Kinematics Under Crouch (-45°)
- Neutral baseline crouch position: `-45°` offset (servo angle `45°`).
- Swing phase (`math.sin(theta_leg) > 0`): Leg lifts upward by `lift` (up to `+30°`).
  - Left Femur (`femur_dir = +1`): `femur_angle = 90 - 45 + int(lift * 1) = 45 + lift` (angle increases towards `75°`).
  - Right Femur (`femur_dir = -1`): `femur_angle = 90 - 45 + int(lift * -1) = 45 - lift` (angle decreases towards `15°`).
- Stance phase (`math.sin(theta_leg) <= 0`): `lift = 0`.
  - Left & Right Femurs: `femur_angle = 45°` (offset `-45°`). Leg rests on ground at crouch height.

### 3.2 Coxa Sweep Kinematics
- Coxas sweep sinusoidally: `sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier`.
- Center reference: `90°` servo angle (`0°` offset).
- Sweep bounds: `-gait_sweep` to `+gait_sweep` (default `30°`, max `45°`).
- Coxas maintain exact same zero reference (`90°`) and sweep range regardless of crouch mode.

---

## 4. Crouch Posture & Gait State Interaction Analysis

### 4.1 Transition Analysis Matrix
| Current State | Command Received | Target Stance | Required Action in Server |
|---|---|---|---|
| Standing (`crouch_active=False`) | `set_gait` (active=True) | Standing Walk | `run_gait()` with `femur_baseline = 0` |
| Standing (`crouch_active=False`) | `set_gait` (active=False) | Standing Neutral | `center_all()` (all servos to 0°) |
| Crouched (`crouch_active=True`) | `set_gait` (active=True) | Crouch Walk | `run_gait()` with `femur_baseline = -45` |
| Crouched (`crouch_active=True`) | `set_gait` (active=False) | Crouched Neutral | Animate targets `{coxa: 0, femur: -45}` (or active crouch offset) |
| Walking (Standing/Crouched) | `set_crouch` (active=True/False) | Crouch / Stand | Update `self.crouch_active`, stop gait if needed or transition baseline dynamically |

---

## 5. Detailed Implementation Recommendations (Milestone 1)

### Recommendation 1: Add State Attributes to `SpooderServer.__init__`
In `server.py` `SpooderServer.__init__()` (around line 140):
```python
self.crouch_active = False
self.crouch_offset = 0
```

### Recommendation 2: Update `set_crouch` Handler
In `server.py` `handler()` (`cmd == "set_crouch"`, around line 491):
```python
elif cmd == "set_crouch":
    self.stop_all_motions()
    active = data.get("active", False)
    offset = int(data.get("offset", -45 if active else 0))
    self.crouch_active = active
    self.crouch_offset = offset
    if active:
        targets = {ch: offset for ch in range(12)}
        asyncio.create_task(self.animate_motion_targets(targets))
    else:
        coxa_targets = {LEG_COXA_CHANNELS[leg]: 0 for leg in range(6)}
        femur_targets = {LEG_FEMUR_CHANNELS[leg]: 0 for leg in range(6)}
        async def _exit_crouch():
            await self.animate_motion_targets(coxa_targets)
            await asyncio.sleep(0.05)
            await self.animate_motion_targets(femur_targets)
        asyncio.create_task(_exit_crouch())
```

### Recommendation 3: Update `run_gait()` Loop Baseline Calculation
In `server.py` `run_gait()` (around line 320):
```python
async def run_gait(self):
    t = 0.0
    last_time = time.time()
    while self.gait_active:
        try:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            omega = 2.0 * math.pi * self.gait_speed
            t += dt
            theta = (omega * t) % (2.0 * math.pi)
            
            # Determine neutral femur baseline (-45° when crouched, 0° when standing)
            femur_baseline = -45 if self.crouch_active else 0
            
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
                
            await self.broadcast_state()
        except Exception as e:
            print(f"[Gait Loop Exception] Recovered from error: {e}")
        await asyncio.sleep(0.03)
```

### Recommendation 4: Update `set_gait` Stop Gait Branch
In `server.py` `handler()` (`cmd == "set_gait"`, around line 447):
```python
if self.gait_active:
    asyncio.create_task(self.run_gait())
else:
    if self.crouch_active:
        # Return to crouched neutral stance (-45° femurs, 0° coxas)
        targets = {LEG_COXA_CHANNELS[leg]: 0 for leg in range(6)}
        targets.update({LEG_FEMUR_CHANNELS[leg]: self.crouch_offset if self.crouch_offset != 0 else -45 for leg in range(6)})
        asyncio.create_task(self.animate_motion_targets(targets))
    else:
        self.center_all()
        await self.broadcast_state()
```

---

## 6. Verification and Acceptance Checklist

- [x] **Continuous Tripod Gait Centered at -45°**: Verified mathematically and logic-traced. Femur angles oscillate between 45° and 75° (left) / 15° (right).
- [x] **Coxa Sweep Range & Reference**: Coxas remain centered at 90° (0° offset), sweeping between -30° and +30° (or configured sweep angle).
- [x] **All 6 Gait Directions**: Forward, Backward, Turn Left, Turn Right, Spin CW, Spin CCW correctly calculate leg multipliers and maintain crouch baseline.
- [x] **State Persistence**: `self.crouch_active` prevents posture snapping when starting and stopping gait.
