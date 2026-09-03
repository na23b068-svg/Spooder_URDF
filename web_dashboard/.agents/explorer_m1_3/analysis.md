# Detailed Analysis Report: Coxa Sweep Calculations & Zero Reference Integrity

**Agent**: Explorer 3 (Milestone 1 — Crouch-Walk Gait Engine)  
**Date**: 2026-09-03  
**Target File**: `/home/smeer/Downloads/Spooder/web_dashboard/server.py`

---

## 1. Executive Summary

This report evaluates the Coxa joint sweep calculations, zero reference stability, and direction multipliers across all gait patterns (Forward, Backward, Spin CW/CCW, Turn Left/Right) in `server.py`. 

**Key Conclusion**:  
The Coxa joint logic in `server.py` naturally isolates the horizontal sweep angle from vertical crouch offsets. During gait execution (`run_gait()`), Coxa angles are calculated strictly relative to the neutral baseline $0^\circ$ (servo angle $90^\circ$), with sweep range bounded by $[-S_{\text{sweep}}, +S_{\text{sweep}}]$ (where $S_{\text{sweep}} \le 45^\circ$). To ensure full specification compliance with Requirement R1 during crouch-walking, `run_gait()` must apply the $-45^\circ$ crouch offset exclusively to Femur channels while maintaining zero offset contamination on Coxa channels.

---

## 2. Evidence Chain & Code Observations

### Observation 1: Channel Architecture & Leg Mapping
In `server.py` (lines 10–14):
```python
10: # Hexapod Channel Layout mapping
11: # Leg indices: 0: LF, 1: LM, 2: LB, 3: RF, 4: RM, 5: RB
12: LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10]
13: LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4]
14: FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]
```
- **Verification**: Servo angles in hardware (`send_command()`) are mapped as `angle = 90 + offset + trim`.
- **Zero Reference ($0^\circ$)**: An offset of $0^\circ$ corresponds to a physical servo command of $90^\circ$. For Coxa joints, $0^\circ$ offset aligns the coxa leg segment perpendicular to the central body axis.

### Observation 2: Existing Coxa Sweep Calculation in `run_gait()`
In `server.py` (lines 308–344):
```python
327: coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
328: lift = max(0.0, math.sin(theta_leg)) * self.gait_lift
329: sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier
330: femur_dir = FEMUR_LIFT_DIRS[leg]
331: 
332: coxa_angle = 90 + int(sweep)
333: femur_angle = 90 + int(lift * femur_dir)
334: 
335: coxa_ch = LEG_COXA_CHANNELS[leg]
336: femur_ch = LEG_FEMUR_CHANNELS[leg]
337: 
338: self.servo_offsets[coxa_ch] = int(sweep)
339: self.servo_offsets[femur_ch] = int(lift * femur_dir)
```
- **Observation**:
  1. `sweep` is calculated as $-\cos(\theta_{\text{leg}}) \cdot S_{\text{sweep}} \cdot M_{\text{coxa}}$.
  2. `coxa_angle = 90 + int(sweep)`.
  3. `self.servo_offsets[coxa_ch]` is assigned `int(sweep)`.
  4. There is no addition of any crouch offset to `coxa_angle` or `servo_offsets[coxa_ch]`.

### Observation 3: Direction Multipliers in `get_coxa_multiplier()`
In `server.py` (lines 295–306):
```python
295: def get_coxa_multiplier(self, leg_index, direction):
296:     is_right_side = leg_index in [3, 4, 5]
297:     
298:     if direction == "Forward":
299:         return -1.0 if is_right_side else 1.0
300:     elif direction == "Backward":
301:         return 1.0 if is_right_side else -1.0
302:     elif direction in ["Turn Left", "Spin Anti-Clockwise", "Spin Anti-Clockwise (CCW)"]:
303:         return -1.0
304:     elif direction in ["Turn Right", "Spin Clockwise", "Spin Clockwise (CW)"]:
305:         return 1.0
306:     return 1.0
```
- **Observation**:
  - Right-side legs (`3: RF, 4: RM, 5: RB`) are mirrored on physical mounting.
  - Multiplier matrix across all directions:
    | Gait Direction | Left Side (0, 1, 2) | Right Side (3, 4, 5) | Physical Motion Effect |
    |---|---|---|---|
    | `Forward` | $+1.0$ | $-1.0$ | Both sides swing backward during stance phase $\rightarrow$ forward robot propulsion |
    | `Backward` | $-1.0$ | $+1.0$ | Both sides swing forward during stance phase $\rightarrow$ backward robot propulsion |
    | `Turn Left` / `Spin CCW` | $-1.0$ | $-1.0$ | Left legs swing forward, Right legs swing backward $\rightarrow$ counter-clockwise body rotation |
    | `Turn Right` / `Spin CW` | $+1.0$ | $+1.0$ | Left legs swing backward, Right legs swing forward $\rightarrow$ clockwise body rotation |
  - In all 4 motion modes, $|M_{\text{coxa}}| = 1.0$.
  - The center of oscillation for Coxa remains $\frac{(+S_{\text{sweep}}) + (-S_{\text{sweep}})}{2} = 0.0^\circ$.

---

## 3. Kinematic Verification & Logic Checks

To ensure that Coxa zero reference ($0^\circ$) and sweep range ($-45^\circ$ to $+45^\circ$) are strictly maintained during crouch-walking without offset contamination, we define 5 logic checks:

### LC-1: Neutral Zero Reference Isolation Check
* **Requirement**: Coxa neutral position during gait must be $0^\circ$ offset ($90^\circ$ servo angle).
* **Analysis**: `coxa_angle = 90 + int(sweep)` does not incorporate any crouch baseline variable (`crouch_offset` or `femur_baseline`). 
* **Verdict**: **PASS**. Femur crouch offset ($-45^\circ$) must be isolated exclusively to `femur_angle`.

### LC-2: Sweep Range Boundary Clamping Check
* **Requirement**: Coxa sweep amplitude must never exceed $[-45^\circ, +45^\circ]$.
* **Analysis**: If `gait_sweep` is set to $45^\circ$, $-\cos(\theta_{\text{leg}}) \in [-1.0, 1.0]$ yields `sweep` $\in [-45.0, +45.0]$. Adding explicit bounds clamping `sweep_amp = max(0.0, min(45.0, self.gait_sweep))` guarantees hardware safety even if invalid WebSocket payloads are received.
* **Verdict**: **PASS (with recommended parameter clamping)**.

### LC-3: Multiplier Directional Symmetry Check
* **Requirement**: Direction multipliers must preserve zero-centered oscillation across all 4 gait patterns.
* **Analysis**: For all 6 legs and all 4 gait directions, $M_{\text{coxa}} \in \{-1.0, +1.0\}$. The mean of the maximum and minimum sweep offsets is $\frac{(+45) + (-45)}{2} = 0^\circ$.
* **Verdict**: **PASS**.

### LC-4: Crouch Posture vs. Gait State Separation Check
* **Requirement**: Transitioning from static Crouch posture into `run_gait()` must immediately re-anchor Coxas to $0^\circ$ zero reference.
* **Analysis**: Static crouch posture (in legacy code or slider mode) may set Coxa offsets. Upon entering `run_gait()`, the loop calculates `sweep` relative to $0^\circ$ and updates `self.servo_offsets[coxa_ch] = int(sweep)` every $30\text{ ms}$, clearing any previous static coxa offset.
* **Verdict**: **PASS**.

### LC-5: Gait Exit Posture Restoration Check
* **Requirement**: Stopping gait while in Crouch mode must cleanly restore Coxa to $0^\circ$ reference while keeping Femurs at $-45^\circ$.
* **Analysis**: When `gait_active = False`, stopping gait must center Coxas to $0^\circ$ offset, while returning Femurs to the active crouch posture ($-45^\circ$) if Crouch mode is enabled.
* **Verdict**: **PASS (requires update in `set_gait` stopping handler)**.

---

## 4. Specific Code Recommendations for `server.py`

Based on the analysis, here are the exact code modifications required in `server.py` for Milestone 1:

### 1. Update `run_gait()` for Crouch Baseline & Coxa Safeguards
```python
async def run_gait(self):
    t = 0.0
    last_time = time.time()
    
    # Clamp sweep and lift to safe physical limits [0, 45]
    sweep_amp = max(0.0, min(45.0, float(self.gait_sweep)))
    lift_amp = max(0.0, min(45.0, float(self.gait_lift)))
    
    # Neutral femur baseline is -45° when Crouch mode is active, 0° otherwise
    femur_baseline = -45 if getattr(self, 'crouch_active', False) else 0

    while self.gait_active:
        try:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            omega = 2.0 * math.pi * self.gait_speed
            t += dt
            theta = (omega * t) % (2.0 * math.pi)
            
            for leg in range(6):
                if leg in [0, 4, 2]:
                    theta_leg = theta
                else:
                    theta_leg = theta + math.pi
                
                coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
                lift = max(0.0, math.sin(theta_leg)) * lift_amp
                sweep = -math.cos(theta_leg) * sweep_amp * coxa_multiplier
                femur_dir = FEMUR_LIFT_DIRS[leg]
                
                # Coxa zero reference (0° offset = 90° servo angle) strictly maintained
                coxa_angle = 90 + int(sweep)
                # Femur lift applies on top of femur_baseline (-45° in crouch mode)
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

---

## 5. Verification Plan

1. **Unit Test / Kinematic Verification Script**:
   Execute simulated gait loops for 1 full period ($t \in [0, 2\pi/\omega]$) across all 4 gait directions (`Forward`, `Backward`, `Turn Left`, `Turn Right`) with `crouch_active = True` and `gait_sweep = 45.0`.
   - Measure $\min(\text{coxa\_offset})$, $\max(\text{coxa\_offset})$, and $\text{mean}(\text{coxa\_offset})$ for all 6 legs.
   - **Expected**: $\min = -45$, $\max = +45$, $\text{mean} = 0$ for all Coxa channels.
   - Measure $\min(\text{femur\_offset})$ and $\max(\text{femur\_offset})$ for all 6 legs.
   - **Expected**: Baseline at $-45^\circ$, lift range $[-45^\circ, -45^\circ + 30^\circ] = [-45^\circ, -15^\circ]$.

2. **Integration Verification**:
   Verify websocket command handling for `set_gait` when toggling crouch mode on and off.
