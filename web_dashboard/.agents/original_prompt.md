## 2026-09-03T05:23:34Z

# Teamwork Project Prompt — Spooder Crouch-Walk & Linear Crouch Slider

Working directory: /home/smeer/Downloads/Spooder/web_dashboard
Integrity mode: development

## Requirements

### R1. Crouch-Walk Gait Engine (Agent 1)
- Modify `run_gait()` in `server.py` so that when Crouch mode is active (or Crouch Slider is set), all gait patterns (Forward, Backward, Spin CW/CCW, Turn Left/Right) execute using a neutral femur baseline of `-45°` instead of `0°`.
- Femur lift calculations apply on top of the `-45°` crouch offset: `femur_angle = 90 - 45 + int(lift * femur_dir)`.
- Coxas must maintain the exact same sweep range (-45° to +45°) and zero reference.

### R2. Linear Crouch Slider & Dynamic Twist (Agent 2)
- Add a slider (`#slider-crouch`) under the Crouch button in `index.html` ranging from `-45` to `+45` (default `0`).
- Update `crouch-toggle` in `app.js` and `server.py` to sync with the Crouch slider (Crouch ON snaps slider to `-45`, Crouch OFF snaps to `0`).
- Negative range (0 to -45): All 12 joint offsets (6 coxas, 6 femurs) adjust linearly from 0° down to -45°.
- Positive range (0 to +45): Coxas spin positive linearly from 0° to +45° while femurs still move toward -45°.
- All pose transitions use the active Motion Profile smoothing (Trapezoidal, S-Curve, Sinusoidal).

## Acceptance Criteria

### Crouch-Walk Functionality
- [ ] Starting any gait while crouched executes continuous tripod gait centered at -45° femur baseline.
- [ ] Coxa sweep range remains centered at 0° (-45° to +45°).

### Linear Crouch Slider
- [ ] Slider under crouch button controls live joint posture from -45 to +45.
- [ ] Moving slider in negative range (0 -> -45) smoothly lowers all 12 joints.
- [ ] Moving slider in positive range (0 -> +45) spins coxas positive (0 -> +45) while driving femurs to -45.
- [ ] Slider syncs dynamically with the Crouch ON/OFF toggle switch.
