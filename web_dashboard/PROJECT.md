# Project: Spooder Crouch-Walk & Linear Crouch Slider

## Architecture
- Backend (`server.py`): Python Flask/HTTP/Socket server controlling Spooder hexapod robot joints, gaits, motion profiles, and crouch state.
- Frontend (`public/index.html`, `public/app.js`, `public/style.css`): Web dashboard UI providing controls for robot posture, gait execution, sliders, and buttons.
- Interfaces / API:
  - Crouch posture API endpoint / socket command: slider value `-45` to `+45`
  - Gait engine in `server.py`: `run_gait()` modified for crouch baseline of `-45°` femur offset.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Independent requirement-driven test suite | None | DONE |
| M1 | Crouch-Walk Gait Engine | `server.py` `run_gait()` neutral femur baseline -45° | None | DONE |
| M2 | Linear Crouch Slider & Dynamic Twist | `index.html`, `app.js`, `server.py` crouch slider -45 to +45 & sync | M1 | IN_PROGRESS |
| M3 | Final E2E Test & Coverage Hardening | Pass 100% E2E tests + Tier 5 adversarial testing | E2E, M1, M2 | PLANNED |

## Interface Contracts
### Frontend ↔ Backend (Crouch Slider / Posture)
- UI element: `#slider-crouch` under Crouch button, range `-45` to `+45`, default `0`.
- Crouch ON/OFF toggle:
  - Crouch ON sets slider to `-45` and sends pose update to backend.
  - Crouch OFF sets slider to `0` and sends pose update to backend.
- Slider input event: sends active crouch angle (`-45` to `+45`) to backend.
- Motion Smoothing: All posture adjustments apply active motion profile smoothing (Trapezoidal, S-Curve, Sinusoidal).

### Backend Gait Engine (`server.py`)
- `run_gait()`:
  - When Crouch mode is active / Crouch offset is set:
    - Femur neutral baseline is `-45°` instead of `0°`.
    - Femur angle formula during gait lift: `femur_angle = 90 - 45 + int(lift * femur_dir)`.
    - Coxas maintain exact sweep range `-45°` to `+45°` and zero reference.

### Linear Crouch & Dynamic Twist Mechanics
- Negative range (`0` to `-45`):
  - Coxas: 0° linearly down to -45°
  - Femurs: 0° linearly down to -45°
- Positive range (`0` to `+45`):
  - Coxas: spin positive linearly 0° up to +45°
  - Femurs: move toward -45° (linearly from 0° down to -45°)

## Code Layout
- `server.py` - Backend server, gait calculations, pose generation, web routes
- `public/index.html` - Dashboard HTML markup
- `public/app.js` - Dashboard JavaScript logic
- `public/style.css` - UI styling
