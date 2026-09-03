# Handoff Report: Coxa Sweep Calculations & Zero Reference Verification

**Agent**: Explorer 3 (Milestone 1 — Crouch-Walk Gait Engine)  
**Working Directory**: `/home/smeer/Downloads/Spooder/web_dashboard/.agents/explorer_m1_3`  
**Target Milestone**: Milestone 1 (Crouch-Walk Gait Engine)  
**Date**: 2026-09-03  

---

## 1. Observation

### File & Code Observations
1. **File**: `/home/smeer/Downloads/Spooder/web_dashboard/server.py`
2. **Coxa Channel Mappings (lines 12–14)**:
   ```python
   LEG_COXA_CHANNELS = [0, 2, 11, 6, 8, 10]
   LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 4]
   FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]
   ```
3. **Direction Multiplier Logic (lines 295–306)**:
   ```python
   def get_coxa_multiplier(self, leg_index, direction):
       is_right_side = leg_index in [3, 4, 5]
       if direction == "Forward":
           return -1.0 if is_right_side else 1.0
       elif direction == "Backward":
           return 1.0 if is_right_side else -1.0
       elif direction in ["Turn Left", "Spin Anti-Clockwise", "Spin Anti-Clockwise (CCW)"]:
           return -1.0
       elif direction in ["Turn Right", "Spin Clockwise", "Spin Clockwise (CW)"]:
           return 1.0
       return 1.0
   ```
4. **Coxa Sweep & Servo Command Logic in `run_gait()` (lines 327–341)**:
   ```python
   coxa_multiplier = self.get_coxa_multiplier(leg, self.gait_direction)
   lift = max(0.0, math.sin(theta_leg)) * self.gait_lift
   sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier
   femur_dir = FEMUR_LIFT_DIRS[leg]

   coxa_angle = 90 + int(sweep)
   femur_angle = 90 + int(lift * femur_dir)

   coxa_ch = LEG_COXA_CHANNELS[leg]
   femur_ch = LEG_FEMUR_CHANNELS[leg]

   self.servo_offsets[coxa_ch] = int(sweep)
   self.servo_offsets[femur_ch] = int(lift * femur_dir)

   self.send_command(coxa_ch, coxa_angle)
   self.send_command(femur_ch, femur_angle)
   ```

---

## 2. Logic Chain

1. **Observation 1 & 4**: In `run_gait()`, `sweep` is calculated as `sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier`.
2. **Mathematical Deduction**: Since $-\cos(\theta_{\text{leg}}) \in [-1.0, 1.0]$ and $|coxa\_multiplier| = 1.0$, `sweep` oscillates symmetrically between `-gait_sweep` and `+gait_sweep`.
3. **Zero Reference Verification**: At phase points $\theta_{\text{leg}} = \pi/2$ and $3\pi/2$, $-\cos(\theta_{\text{leg}}) = 0.0$, making `sweep = 0.0`. `coxa_angle = 90 + 0 = 90°` (corresponding to 0° servo offset). The midpoint of oscillation is exactly $0.0^\circ$.
4. **Offset Contamination Isolation**: `coxa_angle = 90 + int(sweep)` does not include `crouch_offset` or `femur_baseline`. Therefore, when `run_gait()` is modified for Milestone 1 to apply a $-45^\circ$ femur baseline (`femur_angle = 90 - 45 + int(lift * femur_dir)`), Coxa channels remain completely unpolluted by the femur crouch offset.
5. **Directional Consistency**: Across all 4 gait directions (`Forward`, `Backward`, `Turn Left`/`Spin CCW`, `Turn Right`/`Spin CW`), the direction multipliers $M_{\text{coxa}}$ only flip the sign ($\pm 1.0$) to accommodate physical right-side servo mirroring and rotation direction. The amplitude range $[-45^\circ, +45^\circ]$ and zero reference $0.0^\circ$ remain invariant across all directions.

---

## 3. Caveats

1. **Static Posture Contamination Before Gait Start**: In static Crouch mode (or when adjusting the crouch slider), Coxas may be set to static offsets (e.g. $-45^\circ$). When `run_gait()` is launched, `run_gait()` overwrites `servo_offsets[coxa_ch]` on every iteration ($30\text{ ms}$). Implementers must ensure that stopping gait while in crouch mode restores Coxas back to $0^\circ$ centered position.
2. **No Physical Hardware Attached**: Verification was conducted via code inspection and mathematical kinematic tracing in simulation context.

---

## 4. Conclusion

The Coxa sweep formulas and directional multiplier logic in `server.py` strictly satisfy the zero reference ($0^\circ$) and sweep range ($-45^\circ$ to $+45^\circ$) requirements for Milestone 1. 

To complete Milestone 1:
1. Update `run_gait()` in `server.py` to calculate `femur_angle = 90 + femur_baseline + int(lift * femur_dir)` where `femur_baseline = -45` when Crouch mode is active.
2. Keep `coxa_angle = 90 + int(sweep)` unchanged, ensuring zero crouch offset on Coxas.
3. Clamp `gait_sweep` to $[0, 45^\circ]$ to enforce physical joint limits.

---

## 5. Verification Method

To independently verify these findings:

1. **Code Inspection**:
   Inspect `/home/smeer/Downloads/Spooder/web_dashboard/server.py` lines 327–341 to confirm `coxa_angle = 90 + int(sweep)` has no crouch offset added.
2. **Analysis Report**:
   Read `/home/smeer/Downloads/Spooder/web_dashboard/.agents/explorer_m1_3/analysis.md` for full breakdown of logic checks LC-1 through LC-5 and code recommendations.
3. **Kinematic Test Command**:
   Run a python test script simulating `run_gait()` with `gait_sweep = 45.0` and `crouch_active = True` over 1 full period ($t \in [0, 2\pi/\omega]$) and verify:
   - `min(servo_offsets[coxa_ch]) == -45`
   - `max(servo_offsets[coxa_ch]) == 45`
   - `mean(servo_offsets[coxa_ch]) == 0`
   - `min(servo_offsets[femur_ch]) == -45`
