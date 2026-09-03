# Handoff Report: Crouch-Walk Gait Engine (Milestone 1)

## 1. Observation
- `server.py` line 139-156: `SpooderServer.__init__` initializes gait state variables (`gait_active`, `gait_speed`, `gait_sweep`, `gait_lift`, `gait_direction`), but lacks `self.crouch_active` and `self.crouch_offset`.
- `server.py` line 491-508: `set_crouch` command handler executes position animations when `active` is `True` or `False`, but does not save `crouch_active` on `self`.
- `server.py` line 308-348: `run_gait()` calculates femur angles using:
  ```python
  femur_angle = 90 + int(lift * femur_dir)
  self.servo_offsets[femur_ch] = int(lift * femur_dir)
  ```
  which assumes a hardcoded neutral baseline offset of `0°` (raw angle `90°`).
- `server.py` line 332: Coxa calculation in `run_gait()` uses:
  ```python
  coxa_angle = 90 + int(sweep)
  self.servo_offsets[coxa_ch] = int(sweep)
  ```
  where `sweep = -math.cos(theta_leg) * self.gait_sweep * coxa_multiplier`. Zero reference is centered at `90°` (0° offset) and sweep range is `[-gait_sweep, +gait_sweep]` (up to `[-45°, +45°]`).

## 2. Logic Chain
1. During gait execution (`run_gait()`), each leg undergoes stance (on ground, `lift = 0`) and swing (lifting up, `lift > 0`).
2. When Crouch mode is inactive, `femur_baseline = 0°`, yielding stance femur angle `90°` and swing femur angle `90 + int(lift * femur_dir)`.
3. When Crouch mode is active, requirement R1 mandates a neutral femur baseline of `-45°` (raw angle `45°`).
4. Applying `femur_baseline = -45°` yields the formula `femur_angle = 90 - 45 + int(lift * femur_dir)` and `servo_offset = -45 + int(lift * femur_dir)`.
5. For coxas, keeping `coxa_angle = 90 + int(sweep)` preserves the exact `0°` zero reference and `[-45°, +45°]` sweep range centered at `0°`.
6. To enable `run_gait()` to detect whether Crouch mode is active, `self.crouch_active` and `self.crouch_offset` must be tracked in `SpooderServer.__init__` and updated in `set_crouch`.
7. When gait stops (`set_gait` with `active: false`), if `self.crouch_active` is True, returning target positions to `-45°` maintains crouch posture instead of un-crouching the robot.

## 3. Caveats
- This investigation was strictly read-only per agent identity constraints; no code changes were applied to `server.py`.
- Hardware physical testing on PCA9685/I2C/Arduino hardware was not performed; analysis is verified mathematically against raw servo PWM tick formulas (`pulse_us = 500 + (angle / 180.0) * 2000`).
- Linear Crouch Slider (Milestone 2) will build on this baseline by allowing variable crouch offsets (`-45` to `+45`).

## 4. Conclusion
The proposed modifications to `server.py` in `/home/smeer/Downloads/Spooder/web_dashboard/.agents/explorer_m1_1/analysis.md` completely fulfill Requirement R1 for Milestone 1 (Crouch-Walk Gait Engine). The changes ensure all gait directions (Forward, Backward, Spin CW/CCW, Turn Left/Right) execute around a `-45°` neutral femur baseline when crouched, while coxas remain centered at `0°`.

## 5. Verification Method
- **Analysis Inspection**: Verify `analysis.md` for exact line numbers, code snippets, and mathematical truth tables.
- **Python Syntax & Integration Check**:
  Run python compilation test on `server.py`:
  `python3 -m py_compile server.py`
- **Logic Verification Criteria**:
  1. `crouch_active=True`: Femur stance angle must equal `45°` (offset `-45`). Peak swing angle for left legs (`femur_dir=+1`, `lift=30`) must equal `75°` (offset `-15`). Peak swing angle for right legs (`femur_dir=-1`, `lift=30`) must equal `15°` (offset `-75`).
  2. Coxa angle during gait must remain centered at `90°` (offset `0`) with sweep `int(sweep)`.
